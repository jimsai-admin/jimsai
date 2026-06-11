from __future__ import annotations

import os
import re
from typing import Any

import httpx

from .env_config import get_env
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
        "answer from what has already been learned or shared."
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
        "expressions, or answer scientific and quantitative questions."
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
        self.embedding_timeout = float(get_env("JIMS_CAPABILITY_EMBEDDING_TIMEOUT", "8") or "8")
        self.classifier_enabled = get_env("JIMS_ENABLE_ZERO_SHOT_CAPABILITY_ROUTER", "true").lower() in {"1", "true", "yes", "on"}
        # Always use the Modal Classification Service
        self.classifier_url = get_env("JIMS_CLASSIFICATION_SERVICE_URL").rstrip("/")
        self.classifier_token = (
            get_env("JIMS_MODAL_API_KEY")
            or get_env("JIMS_CAPABILITY_CLASSIFIER_TOKEN")
        )
        self.classifier_timeout = float(get_env("JIMS_CAPABILITY_CLASSIFIER_TIMEOUT", "20") or "20")

    async def route(self, request: PipelineRequest, ir: SemanticIR, activation: ActivationDecision) -> tuple[CapabilityPlan, LayerResult]:
        # Start with zero scores — no hardcoded structural keyword scoring.
        # All scoring comes from: (1) embedding similarity, (2) zero-shot classifier, (3) LLM overlay.
        scores: dict[CapabilityKind, float] = {kind: 0.0 for kind in CapabilityKind}
        signals: dict[str, Any] = {}

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

        semantic_scores = {} if strong_structural else await self._semantic_embedding_scores(request.query)
        if semantic_scores:
            signals["semantic_embedding"] = {k.value: round(v, 4) for k, v in semantic_scores.items()}
            for kind, value in semantic_scores.items():
                scores[kind] = min(1.0, scores.get(kind, 0.0) + value * 1.1)

        classifier_scores = {} if strong_structural else await self._zero_shot_classifier_scores(request.query)
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

        if not any(value > 0.16 for value in scores.values()):
            if semantic_scores:
                top_kind, top_val = max(semantic_scores.items(), key=lambda x: x[1])
                scores[top_kind] = max(scores.get(top_kind, 0.0), min(0.24, 0.12 + top_val))
                signals["fallback"] = f"low_confidence_semantic_{top_kind.value}"
            else:
                scores[CapabilityKind.MEMORY_CHAT] = 0.28
                signals["fallback"] = "memory_chat"

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

        if self._should_adjudicate_with_llm(confidence, top_score, second_score, signals):
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

    def _reason_for(self, kind: CapabilityKind, signals: dict[str, Any]) -> str:
        if signals.get("structural", {}).get(kind.value):
            return f"Structural signal selected {kind.value}."
        if signals.get("llm_overlay"):
            return f"LLM overlay selected {kind.value}."
        return f"Embedding/classifier routing selected {kind.value}."

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
        return {"kind": primary, "secondary": secondary, "confidence": confidence, "reason": data.get("reason") or "LLM capability overlay"}

    async def _semantic_embedding_scores(self, query: str) -> dict[CapabilityKind, float]:
        if not self.semantic_enabled or not self.embedding_url or not query.strip():
            return {}
        kinds = list(CAPABILITY_PROTOTYPES)
        headers = {"Content-Type": "application/json"}
        if self.embedding_token:
            headers["Authorization"] = f"Bearer {self.embedding_token}"
        try:
            async with httpx.AsyncClient(timeout=self.embedding_timeout) as client:
                query_response = await client.post(
                    f"{self.embedding_url}/embed",
                    headers=headers,
                    json={"texts": [query], "purpose": "query"},
                )
                query_response.raise_for_status()
                prototype_response = await client.post(
                    f"{self.embedding_url}/embed",
                    headers=headers,
                    json={"texts": [CAPABILITY_PROTOTYPES[kind] for kind in kinds], "purpose": "document"},
                )
                prototype_response.raise_for_status()
            query_vectors = query_response.json().get("vectors") or query_response.json().get("embeddings") or []
            prototype_vectors = prototype_response.json().get("vectors") or prototype_response.json().get("embeddings") or []
            if not isinstance(query_vectors, list) or not isinstance(prototype_vectors, list) or len(prototype_vectors) < len(kinds):
                return {}
            query_vector = self._float_vector(query_vectors[0] if query_vectors else [])
            if not query_vector:
                return {}
            raw_scores = {
                kind: max(0.0, self._cosine(query_vector, self._float_vector(prototype_vectors[index])))
                for index, kind in enumerate(kinds)
            }
            return self._relative_semantic_scores(raw_scores)
        except Exception:
            return {}

    async def _zero_shot_classifier_scores(self, query: str) -> dict[CapabilityKind, float]:
        if not self.classifier_enabled or not self.classifier_url or not query.strip():
            return {}
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
            return scores
        except Exception:
            return {}

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
