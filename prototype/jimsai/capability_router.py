from __future__ import annotations

import os
import re
import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .env_config import get_env
from .errors import CriticalServiceUnavailable
from .models import (
    ActivationDecision,
    CapabilityExecutionResult,
    CapabilityKind,
    CapabilityPlan,
    LayerResult,
    PipelineRequest,
    SemanticIR,
)


# CAPABILITY_PROTOTYPES — semantic concept descriptions used as embedding targets.
# These describe what each capability *means*, not what words trigger it.
# The embedding model translates queries in any language into the same vector space.
CAPABILITY_PROTOTYPES: dict[CapabilityKind, str] = {
    CapabilityKind.MEMORY_CHAT: (
        "Retrieve stored information, recall prior conversations, access personal memory, "
        "answer from what has already been learned or shared. Also includes storing new "
        "personal facts: the user is sharing their name, preferences, tasks, or anything "
        "they want JimsAI to remember for future conversations."
    ),
    CapabilityKind.WORLD_KNOWLEDGE: (
        "Look up current facts, recent events, live data, or information from the public internet "
        "that JimsAI has not been directly told."
    ),
    CapabilityKind.CODING: (
        "Write, generate, debug, refactor, or explain source code, algorithms, queries, "
        "or technical implementations in any programming language or data format."
    ),
    CapabilityKind.MATH_SCIENCE: (
        "Perform calculations, solve equations, derive formulas, evaluate numeric or symbolic "
        "expressions, transform formulas, or compute quantitative results. Conceptual science "
        "explanations without executable math should use memory or world knowledge instead."
    ),
    CapabilityKind.CREATIVE_TEXT: (
        "Write creative content: stories, poems, essays, marketing copy, scripts, emails, "
        "or any original text in a particular tone or style."
    ),
    CapabilityKind.IMAGE_GENERATION: (
        "Generate, create, or edit visual content: images, illustrations, photos, logos, "
        "diagrams, or other visual assets."
    ),
    CapabilityKind.AUDIO_GENERATION: (
        "Generate speech, voice narration, sound effects, or music."
    ),
    CapabilityKind.VIDEO_GENERATION: (
        "Generate or edit video content, animations, or motion graphics."
    ),
    CapabilityKind.AGENTIC_TASK: (
        "Execute a multi-step autonomous task: browse the web, send messages, book appointments, "
        "deploy software, or perform actions in external systems."
    ),
}


@dataclass
class RoutingOutcomeStats:
    observations: int = 0
    success_ema: float = 0.5
    unavailable_ema: float = 0.0

    def update(self, success: bool, unavailable: bool = False, weight: float = 1.0) -> None:
        weight = max(0.05, min(1.0, weight))
        alpha = 0.18 * weight
        self.observations += 1
        self.success_ema = (1.0 - alpha) * self.success_ema + alpha * (1.0 if success else 0.0)
        self.unavailable_ema = (1.0 - alpha) * self.unavailable_ema + alpha * (1.0 if unavailable else 0.0)


class CapabilityRouter:
    """V9 capability router.

    The router is an intention classifier, not an answer generator. It combines
    structural evidence, capability prototype similarity, and an optional bounded
    LLM overlay for ambiguous cases. Execution remains in verified adapters.
    """

    def __init__(self, bridge: Any | None = None) -> None:
        self.bridge = bridge
        self.semantic_enabled = get_env("JIMS_ENABLE_SEMANTIC_CAPABILITY_ROUTER", "true").lower() in {"1", "true", "yes", "on"}
        # Always use the main Modal Embedding Service for capability scoring
        self.embedding_url = get_env("JIMS_EMBEDDING_SERVICE_URL").rstrip("/")
        self.embedding_token = (
            get_env("JIMS_MODAL_API_KEY")
            or get_env("JIMS_EMBEDDING_SERVICE_TOKEN")
        )
        self.embedding_timeout = self._interactive_timeout("JIMS_CAPABILITY_EMBEDDING_TIMEOUT", "4")
        self.classifier_enabled = get_env("JIMS_ENABLE_ZERO_SHOT_CAPABILITY_ROUTER", "true").lower() in {"1", "true", "yes", "on"}
        # Always use the Modal Classification Service
        self.classifier_url = get_env("JIMS_CLASSIFICATION_SERVICE_URL").rstrip("/")
        self.classifier_token = (
            get_env("JIMS_MODAL_API_KEY")
            or get_env("JIMS_CAPABILITY_CLASSIFIER_TOKEN")
        )
        self.classifier_timeout = self._interactive_timeout("JIMS_CAPABILITY_CLASSIFIER_TIMEOUT", "6")
        self.classifier_mode = get_env("JIMS_CAPABILITY_CLASSIFIER_MODE", "off").strip().lower() or "off"
        self.prototype_cache_ttl = float(get_env("JIMS_CAPABILITY_PROTOTYPE_CACHE_TTL", "3600") or "3600")
        self._prototype_embedding_cache: dict[CapabilityKind, list[float]] = {}
        self._prototype_embedding_cached_at = 0.0
        self._outcome_stats: dict[CapabilityKind, RoutingOutcomeStats] = {}

    def _interactive_timeout(self, env_name: str, default: str) -> float:
        try:
            value = float(get_env(env_name, default) or default)
        except ValueError:
            value = float(default)
        try:
            cap = float(get_env("JIMS_INTERACTIVE_SERVICE_TIMEOUT_CAP", "6") or "6")
        except ValueError:
            cap = 6.0
        return min(value, cap) if cap > 0 else value

    async def route(self, request: PipelineRequest, ir: SemanticIR, activation: ActivationDecision) -> tuple[CapabilityPlan, LayerResult]:
        # Start with zero scores — no hardcoded structural keyword scoring.
        # All scoring comes from: (1) embedding similarity, (2) zero-shot classifier, (3) LLM overlay.
        scores: dict[CapabilityKind, float] = {kind: 0.0 for kind in CapabilityKind}
        signals: dict[str, Any] = {}

        question_intent = ir.scope_constraints.get("question_intent", {}) if isinstance(ir.scope_constraints, dict) else {}
        if isinstance(question_intent, dict) and question_intent.get("relation") == "causes":
            plan = self._plan_for(
                CapabilityKind.MEMORY_CHAT,
                0.88,
                "Causal question routed to memory/world-model recall, not symbolic math.",
                routing_signals={
                    "causal_question_gate": True,
                    "question_intent": question_intent,
                    "entities": ir.scope_constraints.get("entities", []) if isinstance(ir.scope_constraints, dict) else [],
                },
            )
            return plan, LayerResult(
                layer="V9_capability_router",
                activated=True,
                deterministic=True,
                summary="Selected v9 capability route: memory_chat.",
                data=plan.model_dump(mode="json"),
            )

        # Only unambiguous syntax signals are applied before embedding — these are
        # format-based (not vocabulary-based) so they work in any language.
        if self._looks_like_numeric_math(request.query):
            scores[CapabilityKind.MATH_SCIENCE] = 0.82
            signals["structural"] = {CapabilityKind.MATH_SCIENCE.value: 0.82}
        if re.search(r"```|\bdef\s+\w+|\bclass\s+\w+|\bimport\s+\w+|\bfn\s+\w+|\bfunc\s+\w+", request.query, re.MULTILINE):
            scores[CapabilityKind.CODING] = max(scores[CapabilityKind.CODING], 0.78)
            signals.setdefault("structural", {})[CapabilityKind.CODING.value] = 0.78

        strong_structural = bool(signals.get("structural")) and max(
            float(v) for v in signals["structural"].values()
        ) >= 0.7

        # Semantic scoring always runs — even with a strong structural signal.
        # A structural hit (math syntax, code fence) identifies ONE intent in the
        # prompt; only embedding similarity can see the other intents in a
        # multi-intent prompt. The structural score stays dominant for the
        # primary route; semantic scores feed secondary-intent detection.
        classifier_scores: dict[CapabilityKind, float] = {}
        try:
            semantic_scores = await self._semantic_embedding_scores(request.query)
        except CriticalServiceUnavailable:
            # Losing the (optional, external) embedding service must NEVER fail a
            # query — that violates the router's own memory-first principle below.
            # Route on structural + workspace-literal (CLL) evidence and fall
            # through to the memory-first default; retrieval + gap reporting still
            # decide what can be answered. No hard dependency on any remote service.
            signals["semantic_router_unavailable"] = True
            semantic_scores = {}
        if semantic_scores:
            signals["semantic_embedding"] = {k.value: round(v, 4) for k, v in semantic_scores.items()}
            for kind, value in semantic_scores.items():
                scores[kind] = min(1.0, scores.get(kind, 0.0) + value * 1.1)

        # Workspace-literal evidence (CLL concept index): a query that names
        # entities the workspace memory already knows is a memory question,
        # whatever its wording superficially resembles ("codename of the
        # device..." is not a coding request when 'Bevorno' is a taught
        # entity). Data-driven — the evidence exists only because the
        # workspace contains the entity; no vocabulary, no language branches.
        #
        # This runs EVEN with a strong structural signal (math syntax, code
        # fence): a structural hit identifies ONE intent (the math span); a
        # named workspace entity identifies ANOTHER (a recall span). That is
        # the multi-attention-span primitive — "what is 12*8+4? and what db
        # does Aperture use?" carries both a math and a memory intent. When a
        # structural signal is already dominant, the workspace-literal boost
        # surfaces memory as a SECONDARY intent so the pipeline composes both
        # answers instead of dropping the recall.
        if True:
            try:
                from .cll_shadow import get_shadow, index_enabled, shadow_enabled
                if index_enabled() or shadow_enabled():
                    shadow = get_shadow()
                    scope_entities = [str(e) for e in ir.scope_constraints.get("entities", [])]
                    known = max(
                        shadow.known_query_literals(request.query),
                        shadow.known_terms(scope_entities),
                    )
                    if known:
                        # When a structural signal is dominant, cap the boost so
                        # memory becomes a strong SECONDARY (not primary) intent;
                        # otherwise it can be the primary as before.
                        cap = 0.55 if not strong_structural else 0.5
                        boost = min(cap, 0.3 + 0.1 * (known - 1))
                        scores[CapabilityKind.MEMORY_CHAT] = min(
                            1.0, scores.get(CapabilityKind.MEMORY_CHAT, 0.0) + boost)
                        signals["workspace_literal_evidence"] = {
                            "known_literals": known, "boost": round(boost, 4),
                            "with_structural": strong_structural}
            except Exception:
                pass

        if not strong_structural and self._should_query_classifier(semantic_scores, scores):
            try:
                classifier_scores = await self._zero_shot_classifier_scores(request.query)
            except CriticalServiceUnavailable:
                # Same guarantee: the zero-shot classifier is optional evidence, not
                # a hard dependency. Its loss degrades routing to memory-first below.
                signals["zero_shot_router_unavailable"] = True
                classifier_scores = {}

        if classifier_scores:
            signals["zero_shot_classifier"] = {k.value: round(v, 4) for k, v in classifier_scores.items()}
            accepted: dict[CapabilityKind, float] = {
                kind: value
                for kind, value in classifier_scores.items()
                if value >= 0.55 and (
                    semantic_scores.get(kind, 0.0) >= 0.05
                    or signals.get("structural", {}).get(kind.value)
                )
            }
            if accepted:
                signals["zero_shot_classifier_accepted"] = {k.value: round(v, 4) for k, v in accepted.items()}
            for kind, value in accepted.items():
                scores[kind] = min(1.0, scores.get(kind, 0.0) + value * 0.88)

        if not self._has_reliable_route_score(scores):
            overlay = await self._llm_overlay(request.query, ir, scores, signals)
            if overlay:
                overlay_kind = overlay.get("kind")
                try:
                    overlay_confidence = float(overlay.get("confidence", 0.0))
                except (TypeError, ValueError):
                    overlay_confidence = 0.0
                if isinstance(overlay_kind, CapabilityKind) and overlay_confidence >= 0.58:
                    scores[overlay_kind] = max(scores.get(overlay_kind, 0.0), min(1.0, overlay_confidence))
                    signals["llm_overlay"] = {
                        "kind": overlay_kind.value,
                        "confidence": round(min(1.0, overlay_confidence), 4),
                        "secondary": [
                            item.value for item in (overlay.get("secondary") or [])
                            if isinstance(item, CapabilityKind) and item != overlay_kind
                        ][:3],
                        "reason": str(overlay.get("reason") or "LLM capability overlay"),
                    }
                else:
                    signals["memory_first_fallback"] = "no reliable route evidence; defaulting to memory-first"
            else:
                signals["memory_first_fallback"] = "no reliable route evidence; defaulting to memory-first"
            if "llm_overlay" not in signals:
                # Routing uncertainty must never fail the query. Memory-first is
                # the architecture's default: retrieval, constraint validation,
                # and gap reporting still decide what can actually be answered —
                # a wrong low-confidence route degrades ranking, not availability.
                scores[CapabilityKind.MEMORY_CHAT] = max(
                    scores.get(CapabilityKind.MEMORY_CHAT, 0.0), 0.30
                )

        policy_adjustments = self._routing_policy_adjustments()
        applied_policy: dict[CapabilityKind, float] = {}
        for score_kind, adjustment in policy_adjustments.items():
            if scores.get(score_kind, 0.0) <= 0.0:
                continue
            scores[score_kind] = max(0.0, min(1.0, scores[score_kind] + adjustment))
            applied_policy[score_kind] = adjustment
        if applied_policy:
            signals["learned_policy"] = {kind.value: round(value, 4) for kind, value in applied_policy.items()}

        # A known workspace entity as the query's subject — a surface literal, or
        # a discourse-resolved pronoun ("And which city is she based in?", where
        # "she" resolves to a workspace entity via thread focus) — makes this a
        # question about the user's PRIVATE world. WORLD_KNOWLEDGE is about PUBLIC
        # entities, so its premise is false here however much the surface
        # resembles a general-knowledge question. It must not be the PRIMARY
        # intent; capping it just below memory keeps memory primary and lets a
        # genuine "compare to <public thing>" span still survive as a secondary
        # (the >=0.44 secondary gate below decides that). This completes the
        # standing principle — a query naming a known workspace entity is a
        # memory question regardless of wording — which a mere score boost did
        # not enforce when a spurious embedding score let WORLD_KNOWLEDGE win.
        if "workspace_literal_evidence" in signals:
            wk = scores.get(CapabilityKind.WORLD_KNOWLEDGE, 0.0)
            mem = scores.get(CapabilityKind.MEMORY_CHAT, 0.0)
            if wk >= mem:
                scores[CapabilityKind.WORLD_KNOWLEDGE] = mem - 1e-3
                signals["workspace_literal_evidence"]["world_knowledge_capped_from"] = round(wk, 4)

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
        kind = ranked[0][0] if ranked else CapabilityKind.MEMORY_CHAT
        top_score = ranked[0][1] if ranked else 0.0
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        # IR override: trust the semantic compiler's CODE_GENERATE signal
        if ir.target_ir == "CODE_GENERATE" and kind != CapabilityKind.CODING:
            kind = CapabilityKind.CODING
            top_score = max(top_score, scores.get(CapabilityKind.CODING, 0.35))

        confidence = self._confidence(top_score, second_score)
        reason = self._reason_for(kind, signals)
        secondary = [c for c, s in ranked[1:4] if s >= 0.44 and top_score - s <= 0.28]
        if "llm_overlay" in signals:
            overlay_signal = signals["llm_overlay"]
            reason = str(overlay_signal.get("reason") or reason)
            try:
                confidence = max(confidence, min(1.0, float(overlay_signal.get("confidence", confidence))))
            except (TypeError, ValueError):
                pass
            overlay_secondary: list[CapabilityKind] = []
            for item in overlay_signal.get("secondary", []):
                with contextlib.suppress(ValueError):
                    candidate = CapabilityKind(item)
                    if candidate != kind:
                        overlay_secondary.append(candidate)
            if overlay_secondary:
                secondary = overlay_secondary[:3]

        if "llm_overlay" not in signals and self._should_adjudicate_with_llm(confidence, top_score, second_score, signals):
            overlay = await self._llm_overlay(request.query, ir, scores, signals)
            if overlay:
                overlay_kind = overlay.get("kind")
                overlay_confidence = overlay.get("confidence", 0.0)
                if isinstance(overlay_kind, CapabilityKind) and overlay_confidence >= max(confidence, 0.58):
                    kind = overlay_kind
                    confidence = min(0.92, max(confidence, float(overlay_confidence)))
                    reason = str(overlay.get("reason") or reason)
                    secondary = [i for i in (overlay.get("secondary") or []) if isinstance(i, CapabilityKind) and i != kind][:3]
                    signals["llm_overlay"] = {
                        "kind": kind.value,
                        "confidence": round(confidence, 4),
                        "secondary": [i.value for i in secondary],
                        "reason": reason,
                    }

        # Segment-aware multi-intent attention: a whole-prompt embedding blends
        # multiple intents into one vector, so a two-part prompt looks like its
        # dominant part. Per-segment embeddings (one batched call) let each part
        # of the prompt vote its own capability — language-agnostic, no keywords.
        segment_kinds = await self._segment_secondary_kinds(request.query, kind)
        if segment_kinds:
            signals["segment_intents"] = [k.value for k in segment_kinds]
            for seg_kind in segment_kinds:
                if seg_kind not in secondary:
                    secondary.append(seg_kind)
            secondary = secondary[:3]

        # Direct workspace-literal evidence forces a memory SECONDARY intent:
        # the query names a known workspace entity, so a recall span exists
        # even when a structural signal (math/code) is the primary. This is
        # unambiguous evidence, so it bypasses the margin heuristic — the
        # multi-attention-span primitive that makes "compute X; and what does
        # Y use?" answer BOTH parts instead of dropping the recall.
        if ("workspace_literal_evidence" in signals
                and kind != CapabilityKind.MEMORY_CHAT
                and CapabilityKind.MEMORY_CHAT not in secondary):
            secondary = [CapabilityKind.MEMORY_CHAT, *secondary][:3]

        plan = self._plan_for(
            kind, confidence, reason,
            secondary_intents=secondary,
            routing_signals={"scores": {k.value: round(v, 4) for k, v in scores.items()}, **signals},
        )
        return plan, LayerResult(
            layer="V9_capability_router",
            activated=True,
            deterministic="llm_overlay" not in signals,
            summary=f"Selected v9 capability route: {plan.kind.value}.",
            data=plan.model_dump(mode="json"),
        )

    def plan_for_secondary(self, kind: CapabilityKind, primary_plan: CapabilityPlan) -> CapabilityPlan:
        """Build an execution plan for a secondary intent detected alongside the
        primary route, so multi-intent prompts get every part addressed."""
        confidence = round(max(0.40, min(0.85, primary_plan.confidence * 0.85)), 4)
        return self._plan_for(
            kind,
            confidence,
            f"Secondary intent detected alongside {primary_plan.kind.value}.",
            routing_signals={"secondary_of": primary_plan.kind.value},
        )

    def record_outcome(
        self,
        kind: CapabilityKind | str,
        *,
        status: str | None = None,
        success: bool | None = None,
        confidence: float = 1.0,
    ) -> None:
        capability = kind if isinstance(kind, CapabilityKind) else CapabilityKind(str(kind))
        status_value = str(status or "").lower()
        unavailable = status_value in {"unavailable", "blocked", "failed", "error", "timeout"}
        if success is None:
            success = status_value in {"available", "completed", "solved", "not_required", "queued"}
        stats = self._outcome_stats.setdefault(capability, RoutingOutcomeStats())
        stats.update(success=bool(success), unavailable=unavailable, weight=confidence)

    def _routing_policy_adjustments(self) -> dict[CapabilityKind, float]:
        adjustments: dict[CapabilityKind, float] = {}
        for kind, stats in self._outcome_stats.items():
            if stats.observations <= 0:
                continue
            sample_confidence = min(1.0, stats.observations / 20.0)
            reliability = stats.success_ema - 0.5
            availability_penalty = stats.unavailable_ema * 0.12
            adjustment = reliability * 0.18 * sample_confidence - availability_penalty * sample_confidence
            if abs(adjustment) >= 0.005:
                adjustments[kind] = round(adjustment, 4)
        return adjustments

    def _plan_for(
        self,
        kind: CapabilityKind,
        confidence: float,
        reason: str,
        secondary_intents: list[CapabilityKind] | None = None,
        routing_signals: dict[str, Any] | None = None,
    ) -> CapabilityPlan:
        common_verify = ["source_trace", "confidence_score", "gap_reporting", "csse_no_extra_claims"]
        common = {
            "confidence": confidence,
            "reason": reason,
            "secondary_intents": secondary_intents or [],
            "routing_signals": routing_signals or {},
        }
        plans: dict[CapabilityKind, CapabilityPlan] = {
            CapabilityKind.MEMORY_CHAT: CapabilityPlan(
                kind=kind,
                route="memory_first",
                verification_requirements=[*common_verify, "workspace_scope"],
                energy_profile="low",
                context_strategy="persistent_memory",
                **common,
            ),
            CapabilityKind.WORLD_KNOWLEDGE: CapabilityPlan(
                kind=kind,
                route="web_augmented_retrieval",
                requires_external_adapter=True,
                allowed_adapters=["web_search", "source_fetch"],
                verification_requirements=[*common_verify, "freshness_check", "source_citation"],
                energy_profile="medium",
                context_strategy="tool_augmented",
                **common,
            ),
            CapabilityKind.CODING: CapabilityPlan(
                kind=kind,
                route="code_docs_sandbox",
                requires_external_adapter=True,
                allowed_adapters=["code_docs", "test_runner", "package_metadata"],
                verification_requirements=[*common_verify, "test_or_static_check", "version_awareness"],
                energy_profile="medium",
                context_strategy="tool_augmented",
                **common,
            ),
            CapabilityKind.MATH_SCIENCE: CapabilityPlan(
                kind=kind,
                route="solver_verified",
                requires_external_adapter=True,
                allowed_adapters=["calculator", "symbolic_solver", "paper_retrieval"],
                verification_requirements=[*common_verify, "calculation_trace"],
                energy_profile="medium",
                context_strategy="tool_augmented",
                **common,
            ),
            CapabilityKind.CREATIVE_TEXT: CapabilityPlan(
                kind=kind,
                route="csse_style_memory",
                allowed_adapters=["t2_render", "style_memory"],
                verification_requirements=["style_constraints", "user_intent_preservation"],
                energy_profile="low",
                context_strategy="bounded_retrieval",
                **common,
            ),
            CapabilityKind.IMAGE_GENERATION: CapabilityPlan(
                kind=kind,
                route="image_generation_provider",
                requires_external_adapter=True,
                allowed_adapters=["image_generation"],
                verification_requirements=["prompt_safety", "asset_provenance", "human_review_optional"],
                energy_profile="high",
                context_strategy="generation_provider",
                **common,
            ),
            CapabilityKind.AUDIO_GENERATION: CapabilityPlan(
                kind=kind,
                route="audio_generation_provider",
                requires_external_adapter=True,
                allowed_adapters=["tts_audio_generation"],
                verification_requirements=["voice_rights", "prompt_safety", "asset_provenance"],
                energy_profile="high",
                context_strategy="generation_provider",
                **common,
            ),
            CapabilityKind.VIDEO_GENERATION: CapabilityPlan(
                kind=kind,
                route="video_generation_provider",
                requires_external_adapter=True,
                allowed_adapters=["video_generation"],
                verification_requirements=["prompt_safety", "asset_provenance", "human_review_required"],
                energy_profile="high",
                context_strategy="generation_provider",
                human_approval_required=True,
                **common,
            ),
            CapabilityKind.AGENTIC_TASK: CapabilityPlan(
                kind=kind,
                route="approved_tool_execution",
                requires_external_adapter=True,
                allowed_adapters=["tool_registry", "browser", "api_executor", "job_queue"],
                verification_requirements=["permission_check", "dry_run", "rollback_plan", "audit_log"],
                energy_profile="medium",
                context_strategy="tool_augmented",
                human_approval_required=True,
                **common,
            ),
        }
        return plans[kind]

    def _score_capabilities(
        self,
        query: str,
        tokens: set[str],
        activation: ActivationDecision,
    ) -> tuple[dict[CapabilityKind, float], dict[str, Any]]:
        # Kept for backward compatibility — route() no longer calls this.
        # Returns empty scores; all scoring is done inline in route().
        return {kind: 0.0 for kind in CapabilityKind}, {}

    def _looks_like_numeric_math(self, query: str) -> bool:
        """Detect numeric math via structural signals only — digits + operators."""
        return bool(
            re.search(r"\d", query)
            and re.search(r"[+\-*/=]|(?<!\w)(solve|calculate|compute|evaluate)(?!\w)", query, re.IGNORECASE)
        )

    def _confidence(self, top_score: float, second_score: float) -> float:
        if top_score <= 0:
            return 0.5
        margin = max(top_score - second_score, 0.0)
        return round(min(0.94, max(0.5, 0.48 + top_score * 0.45 + margin * 0.35)), 4)

    def _has_reliable_route_score(self, scores: dict[CapabilityKind, float]) -> bool:
        ranked = sorted(scores.values(), reverse=True)
        if not ranked:
            return False
        top_score = ranked[0]
        second_score = ranked[1] if len(ranked) > 1 else 0.0
        try:
            absolute_threshold = float(get_env("JIMS_CAPABILITY_ROUTE_ABSOLUTE_THRESHOLD", "0.16") or "0.16")
            relative_threshold = float(get_env("JIMS_CAPABILITY_ROUTE_RELATIVE_THRESHOLD", "0.12") or "0.12")
            margin_threshold = float(get_env("JIMS_CAPABILITY_ROUTE_MARGIN_THRESHOLD", "0.025") or "0.025")
        except ValueError:
            absolute_threshold = 0.16
            relative_threshold = 0.12
            margin_threshold = 0.025
        return top_score > absolute_threshold or (
            top_score >= relative_threshold and top_score - second_score >= margin_threshold
        )

    def _reason_for(self, kind: CapabilityKind, signals: dict[str, Any]) -> str:
        if signals.get("structural", {}).get(kind.value):
            return f"Structural signal selected {kind.value}."
        if signals.get("llm_overlay"):
            return f"LLM overlay selected {kind.value}."
        if signals.get("zero_shot_classifier"):
            return f"Embedding/classifier routing selected {kind.value}."
        return f"Embedding routing selected {kind.value}."

    def _should_query_classifier(
        self,
        semantic_scores: dict[CapabilityKind, float],
        scores: dict[CapabilityKind, float],
    ) -> bool:
        if not self.classifier_enabled:
            return False
        if self.classifier_mode in {"0", "false", "no", "off", "disabled"}:
            return False
        if self.classifier_mode in {"1", "true", "yes", "on", "always", "hot_path"}:
            return True
        if self.classifier_mode not in {"adjudication", "ambiguous"}:
            return False
        if not semantic_scores:
            return True
        ranked = sorted(scores.values(), reverse=True)
        top_score = ranked[0] if ranked else 0.0
        second_score = ranked[1] if len(ranked) > 1 else 0.0
        try:
            min_score = float(get_env("JIMS_CAPABILITY_CLASSIFIER_ADJUDICATION_MIN_SCORE", "0.22") or "0.22")
            max_margin = float(get_env("JIMS_CAPABILITY_CLASSIFIER_ADJUDICATION_MAX_MARGIN", "0.08") or "0.08")
        except ValueError:
            min_score = 0.22
            max_margin = 0.08
        return top_score < min_score or top_score - second_score < max_margin

    def _should_adjudicate_with_llm(self, confidence: float, top_score: float, second_score: float, signals: dict[str, Any]) -> bool:
        """Use LLM overlay when embedding/classifier confidence is ambiguous.

        No language detection needed — the LLM handles all languages natively.
        """
        if not self.bridge:
            return False
        return confidence < 0.62 or top_score - second_score < 0.16

    async def _llm_overlay(
        self,
        query: str,
        ir: SemanticIR,
        scores: dict[CapabilityKind, float],
        signals: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.bridge:
            return None
        data = await self.bridge.classify_capability(
            query,
            {
                "target_ir": ir.target_ir,
                "intent_domain": ir.intent_domain.value,
                "scores": {key.value: round(value, 4) for key, value in scores.items()},
                "signals": signals,
            },
        )
        if not data:
            return None
        kinds = {kind.value: kind for kind in CapabilityKind}
        primary = kinds.get(str(data.get("primary_kind") or "").strip())
        if not primary:
            return None
        secondary = [kinds[item] for item in data.get("secondary_kinds", []) if item in kinds]
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence <= 0.0:
            confidence = 0.68
        return {"kind": primary, "secondary": secondary, "confidence": confidence, "reason": data.get("reason") or "LLM capability overlay"}

    async def _segment_secondary_kinds(
        self, query: str, primary: CapabilityKind
    ) -> list[CapabilityKind]:
        """Detect additional intents by routing each prompt segment separately.

        Best-effort and additive: any failure returns [] and the primary route
        stands. Splitting uses script-neutral sentence punctuation, not words.
        """
        segments = [
            seg.strip()
            for seg in re.split(r"[?？!！。;；\n]+", query)
            if len(seg.strip()) >= 12
        ]
        if len(segments) < 2:
            return []
        segments = segments[:4]
        detected: list[CapabilityKind] = []
        # Deterministic per-segment structural check (format-based, any language)
        for seg in segments:
            if self._looks_like_numeric_math(seg):
                detected.append(CapabilityKind.MATH_SCIENCE)
        if self.semantic_enabled and self.embedding_url:
            try:
                min_score = float(get_env("JIMS_SEGMENT_INTENT_MIN_SCORE", "0.35") or "0.35")
            except ValueError:
                min_score = 0.35
            try:
                headers = {"Content-Type": "application/json"}
                if self.embedding_token:
                    headers["Authorization"] = f"Bearer {self.embedding_token}"
                prototype_vectors = await self._capability_prototype_vectors(list(CAPABILITY_PROTOTYPES))
                async with httpx.AsyncClient(timeout=self.embedding_timeout) as client:
                    response = await client.post(
                        f"{self.embedding_url}/embed",
                        headers=headers,
                        json={"texts": segments, "purpose": "query"},
                    )
                response.raise_for_status()
                payload = response.json()
                vectors = payload.get("vectors") or payload.get("embeddings") or []
                if not payload.get("fallback") and isinstance(vectors, list):
                    for raw_vector in vectors[: len(segments)]:
                        vector = self._float_vector(raw_vector)
                        if not vector:
                            continue
                        raw_scores = {
                            proto_kind: max(0.0, self._cosine(vector, prototype_vectors[proto_kind]))
                            for proto_kind in prototype_vectors
                        }
                        relative = self._relative_semantic_scores(raw_scores)
                        top_kind, top_value = max(relative.items(), key=lambda item: item[1])
                        if top_value >= min_score:
                            detected.append(top_kind)
            except Exception:
                pass  # segment detection is an enhancement, never a failure path
        ordered: list[CapabilityKind] = []
        for candidate in detected:
            if candidate != primary and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    async def _semantic_embedding_scores(self, query: str) -> dict[CapabilityKind, float]:
        if not self.semantic_enabled or not query.strip():
            return {}
        if not self.embedding_url:
            raise CriticalServiceUnavailable("capability embedding service URL is not configured")
        kinds = list(CAPABILITY_PROTOTYPES)
        headers = {"Content-Type": "application/json"}
        if self.embedding_token:
            headers["Authorization"] = f"Bearer {self.embedding_token}"
        prototype_task: asyncio.Task[dict[CapabilityKind, list[float]]] | None = None
        try:
            prototype_task = asyncio.create_task(self._capability_prototype_vectors(kinds))
            async with httpx.AsyncClient(timeout=self.embedding_timeout) as client:
                query_response = await client.post(
                    f"{self.embedding_url}/embed",
                    headers=headers,
                    json={"texts": [query], "purpose": "query"},
                )
            query_response.raise_for_status()
            query_payload = query_response.json()
            if query_payload.get("fallback"):
                if not prototype_task.done():
                    prototype_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await prototype_task
                raise CriticalServiceUnavailable("capability embedding service returned fallback response")
            query_vectors = query_payload.get("vectors") or query_payload.get("embeddings") or []
            if not isinstance(query_vectors, list):
                if not prototype_task.done():
                    prototype_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await prototype_task
                raise CriticalServiceUnavailable("capability embedding service returned malformed vectors")
            prototype_vectors_by_kind = await prototype_task
            if len(prototype_vectors_by_kind) < len(kinds):
                raise CriticalServiceUnavailable("capability prototype embeddings unavailable")
            query_vector = self._float_vector(query_vectors[0] if query_vectors else [])
            if not query_vector:
                raise CriticalServiceUnavailable("capability query embedding unavailable")
            raw_scores = {
                kind: max(0.0, self._cosine(query_vector, prototype_vectors_by_kind[kind]))
                for kind in kinds
            }
            return self._relative_semantic_scores(raw_scores)
        except CriticalServiceUnavailable:
            raise
        except Exception as exc:
            if prototype_task is not None and not prototype_task.done():
                prototype_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await prototype_task
            raise CriticalServiceUnavailable("capability embedding service unavailable") from exc

    async def _capability_prototype_vectors(self, kinds: list[CapabilityKind]) -> dict[CapabilityKind, list[float]]:
        now = time.monotonic()
        if (
            self._prototype_embedding_cache
            and now - self._prototype_embedding_cached_at < self.prototype_cache_ttl
            and all(kind in self._prototype_embedding_cache for kind in kinds)
        ):
            return self._prototype_embedding_cache
        headers = {"Content-Type": "application/json"}
        if self.embedding_token:
            headers["Authorization"] = f"Bearer {self.embedding_token}"
        try:
            async with httpx.AsyncClient(timeout=self.embedding_timeout) as client:
                response = await client.post(
                    f"{self.embedding_url}/embed",
                    headers=headers,
                    json={"texts": [CAPABILITY_PROTOTYPES[kind] for kind in kinds], "purpose": "document"},
                )
                response.raise_for_status()
            payload = response.json()
            if payload.get("fallback"):
                raise CriticalServiceUnavailable("capability prototype embedding service returned fallback response")
            vectors = payload.get("vectors") or payload.get("embeddings") or []
            if not isinstance(vectors, list) or len(vectors) < len(kinds):
                raise CriticalServiceUnavailable("capability prototype embedding service returned malformed vectors")
            cache: dict[CapabilityKind, list[float]] = {}
            for index, kind in enumerate(kinds):
                vector = self._float_vector(vectors[index])
                if not vector:
                    raise CriticalServiceUnavailable("capability prototype embedding unavailable")
                cache[kind] = vector
            self._prototype_embedding_cache = cache
            self._prototype_embedding_cached_at = now
            return cache
        except CriticalServiceUnavailable:
            raise
        except Exception as exc:
            raise CriticalServiceUnavailable("capability prototype embedding service unavailable") from exc

    async def _zero_shot_classifier_scores(self, query: str) -> dict[CapabilityKind, float]:
        if not self.classifier_enabled or not query.strip():
            return {}
        if not self.classifier_url:
            raise CriticalServiceUnavailable("capability classifier service URL is not configured")
        headers = {"Content-Type": "application/json"}
        if self.classifier_token:
            headers["Authorization"] = f"Bearer {self.classifier_token}"
        try:
            async with httpx.AsyncClient(timeout=self.classifier_timeout) as client:
                response = await client.post(
                    f"{self.classifier_url}/classify",
                    headers=headers,
                    json={"text": query, "candidate_labels": [kind.value for kind in CapabilityKind]},
                )
                response.raise_for_status()
            payload = response.json()
            kinds = {kind.value: kind for kind in CapabilityKind}
            scores: dict[CapabilityKind, float] = {}
            for item in payload.get("scores") or []:
                kind = kinds.get(str(item.get("kind") or ""))
                if not kind:
                    continue
                try:
                    scores[kind] = max(0.0, min(float(item.get("score") or 0.0), 1.0))
                except (TypeError, ValueError):
                    continue
            if not scores:
                raise CriticalServiceUnavailable("capability classifier returned no usable scores")
            return scores
        except CriticalServiceUnavailable:
            raise
        except Exception as exc:
            raise CriticalServiceUnavailable("capability classifier service unavailable") from exc

    def _relative_semantic_scores(self, raw_scores: dict[CapabilityKind, float]) -> dict[CapabilityKind, float]:
        if not raw_scores:
            return {}
        values = list(raw_scores.values())
        mean = sum(values) / len(values)
        ranked = sorted(values, reverse=True)
        spread = (ranked[0] - ranked[1]) if len(ranked) > 1 else ranked[0]
        adjusted: dict[CapabilityKind, float] = {}
        for kind, value in raw_scores.items():
            separation = max(value - mean, 0.0)
            adjusted[kind] = min(1.0, separation * 8.0 + (spread * 3.0 if value == ranked[0] else 0.0))
        return adjusted

    def _float_vector(self, values: Any) -> list[float]:
        if not isinstance(values, list):
            return []
        try:
            return [float(value) for value in values]
        except (TypeError, ValueError):
            return []

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        dot = sum(left[index] * right[index] for index in range(size))
        left_norm = sum(left[index] * left[index] for index in range(size)) ** 0.5
        right_norm = sum(right[index] * right[index] for index in range(size)) ** 0.5
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _language_hint(self, query: str) -> str:
        # Kept for backward compatibility with any callers that log language hints.
        # No longer used for routing decisions.
        return "unknown"


class CapabilityAdapterRegistry:
    """Structured provider registry for v9 capabilities."""

    def readiness(self) -> dict[str, bool | str]:
        return {
            "web_search_available": True,  # DuckDuckGo needs no API key — always available as fallback
            "web_search_provider": "brave" if os.getenv("BRAVE_SEARCH_API_KEY") else ("custom" if os.getenv("JIMS_WEB_SEARCH_API_KEY") else "duckduckgo"),
            "code_docs_available": True,  # Internal sandbox + invention engine always available
            "code_docs_detail": "internal_sandbox" if not os.getenv("JIMS_CODE_DOCS_PROVIDER") else os.getenv("JIMS_CODE_DOCS_PROVIDER"),
            "math_solver_available": True,
            "math_solver_detail": "internal_symbolic_solver",
            "image_generation_available": bool(os.getenv("JIMS_IMAGE_GENERATION_URL")),
            "audio_generation_available": bool(os.getenv("JIMS_AUDIO_GENERATION_URL")),
            "video_generation_available": bool(os.getenv("JIMS_VIDEO_GENERATION_URL")),
            "agent_executor_available": os.getenv("JIMS_AGENT_EXECUTOR_ENABLED", "false").lower() == "true",
            "agent_requires_approval": os.getenv("JIMS_AGENT_REQUIRE_APPROVAL", "true").lower() != "false",
        }

    def prepare(self, plan: CapabilityPlan) -> list[CapabilityExecutionResult]:
        if plan.kind == CapabilityKind.MEMORY_CHAT or not plan.requires_external_adapter:
            return [
                CapabilityExecutionResult(
                    kind=plan.kind,
                    adapter="structured_memory_runtime" if plan.kind == CapabilityKind.MEMORY_CHAT else ",".join(plan.allowed_adapters) or "internal",
                    status="not_required",
                    confidence=plan.confidence,
                    summary=(
                        "Memory-first route uses existing retrieval, graph, simulation, and CSSE layers."
                        if plan.kind == CapabilityKind.MEMORY_CHAT
                        else "Capability can proceed through bounded internal rendering/style constraints."
                    ),
                )
            ]
        if plan.kind == CapabilityKind.MATH_SCIENCE:
            return [
                CapabilityExecutionResult(
                    kind=plan.kind,
                    adapter="internal_symbolic_solver",
                    status="available",
                    confidence=plan.confidence,
                    summary="Arithmetic and supported equations execute through the verified internal solver.",
                    data={"verification_requirements": plan.verification_requirements},
                )
            ]
        if plan.kind == CapabilityKind.CODING:
            # The internal sandbox + invention engine (MCTS) is always available.
            # External code_docs/test_runner adapters are optional enhancements.
            return [
                CapabilityExecutionResult(
                    kind=plan.kind,
                    adapter="internal_sandbox_invention_engine",
                    status="available",
                    confidence=plan.confidence,
                    summary=(
                        "Code generation and verification execute through the internal "
                        "sandbox (DeterministicSandbox) and invention engine (MCTS). "
                        "External code_docs/test_runner adapters are optional enhancements."
                    ),
                    data={"verification_requirements": plan.verification_requirements},
                )
            ]
        readiness = self.readiness()
        available = any(bool(readiness.get(f"{adapter}_available")) for adapter in self._readiness_keys(plan.allowed_adapters))
        if plan.human_approval_required:
            status = "blocked" if not available else "queued"
            summary = "Human approval is required before this capability can execute."
        else:
            status = "available" if available else "unavailable"
            summary = "Provider adapter is configured." if available else "No configured provider adapter for this capability yet."
        return [
            CapabilityExecutionResult(
                kind=plan.kind,
                adapter=",".join(plan.allowed_adapters) or "none",
                status=status,
                confidence=plan.confidence if available else 0.0,
                summary=summary,
                data={"readiness": readiness, "verification_requirements": plan.verification_requirements},
            )
        ]

    def _readiness_keys(self, adapters: list[str]) -> list[str]:
        mapping = {
            "web_search": "web_search",
            "source_fetch": "web_search",
            "code_docs": "code_docs",
            "test_runner": "code_docs",
            "package_metadata": "code_docs",
            "calculator": "math_solver",
            "symbolic_solver": "math_solver",
            "paper_retrieval": "math_solver",
            "image_generation": "image_generation",
            "tts_audio_generation": "audio_generation",
            "video_generation": "video_generation",
            "tool_registry": "agent_executor",
            "browser": "agent_executor",
            "api_executor": "agent_executor",
            "job_queue": "agent_executor",
        }
        return [mapping.get(adapter, adapter) for adapter in adapters]
