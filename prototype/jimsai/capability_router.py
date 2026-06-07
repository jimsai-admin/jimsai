from __future__ import annotations

import os
import re
from typing import Any

import httpx

from .models import (
    ActivationDecision,
    CapabilityExecutionResult,
    CapabilityKind,
    CapabilityPlan,
    LayerResult,
    PipelineRequest,
    SemanticIR,
)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_+\-.#]+", value.lower()))


CAPABILITY_PROTOTYPES: dict[CapabilityKind, str] = {
    CapabilityKind.MEMORY_CHAT: "remember retrieve explain answer stored project memory user profile prior sources context provenance",
    CapabilityKind.WORLD_KNOWLEDGE: "latest current news web internet public facts weather prices schedules changing external source citation",
    CapabilityKind.CODING: "code debug stack trace error package api function class test sandbox repository deploy implementation",
    CapabilityKind.MATH_SCIENCE: "calculate compute evaluate solve equation arithmetic formula quantitative proof derive validate numeric scientific",
    CapabilityKind.CREATIVE_TEXT: "write rewrite draft story poem script tone email proposal copy style creative wording",
    CapabilityKind.IMAGE_GENERATION: "generate create edit image picture photo logo poster illustration visual asset",
    CapabilityKind.AUDIO_GENERATION: "generate create voice speech audio sound music tts narration",
    CapabilityKind.VIDEO_GENERATION: "generate create video animation clip movie storyboard motion",
    CapabilityKind.AGENTIC_TASK: "agent automate browser click book send schedule deploy rollback task execute external action approval",
}

class CapabilityRouter:
    """V9 capability router.

    The router is an intention classifier, not an answer generator. It combines
    structural evidence, capability prototype similarity, and an optional bounded
    LLM overlay for ambiguous cases. Execution remains in verified adapters.
    """

    def __init__(self, bridge: Any | None = None) -> None:
        self.bridge = bridge
        self.semantic_enabled = os.getenv("JIMS_ENABLE_SEMANTIC_CAPABILITY_ROUTER", "true").lower() in {"1", "true", "yes", "on"}
        self.embedding_url = (
            os.getenv("JIMS_CAPABILITY_EMBEDDING_SERVICE_URL", "")
            or os.getenv("JIMS_EMBEDDING_SERVICE_URL", "")
        ).strip().rstrip("/")
        self.embedding_token = (
            os.getenv("JIMS_CAPABILITY_EMBEDDING_SERVICE_TOKEN", "")
            or os.getenv("JIMS_EMBEDDING_SERVICE_TOKEN", "")
            or os.getenv("JIMS_MODAL_API_KEY", "")
        ).strip()
        self.embedding_timeout = float(os.getenv("JIMS_CAPABILITY_EMBEDDING_TIMEOUT", "8") or "8")
        self.classifier_enabled = os.getenv("JIMS_ENABLE_ZERO_SHOT_CAPABILITY_ROUTER", "true").lower() in {"1", "true", "yes", "on"}
        self.classifier_url = (
            os.getenv("JIMS_CLASSIFICATION_SERVICE_URL", "")
            or self.embedding_url
        ).strip().rstrip("/")
        self.classifier_token = (
            os.getenv("JIMS_CAPABILITY_CLASSIFIER_TOKEN", "")
            or self.embedding_token
        ).strip()
        self.classifier_timeout = float(os.getenv("JIMS_CAPABILITY_CLASSIFIER_TIMEOUT", "20") or "20")

    async def route(self, request: PipelineRequest, ir: SemanticIR, activation: ActivationDecision) -> tuple[CapabilityPlan, LayerResult]:
        query = request.query.lower()
        tokens = _tokens(request.query)
        scores, signals = self._score_capabilities(query, tokens, activation)
        signals["language_hint"] = self._language_hint(request.query)
        structural_signals = signals.get("structural") if isinstance(signals.get("structural"), dict) else {}
        strong_structural = bool(structural_signals) and max(float(value) for value in structural_signals.values()) >= 0.7
        semantic_scores = {} if strong_structural else await self._semantic_embedding_scores(request.query)
        if semantic_scores:
            signals["semantic_embedding"] = {key.value: round(value, 4) for key, value in semantic_scores.items()}
            for kind, value in semantic_scores.items():
                scores[kind] = min(1.0, scores.get(kind, 0.0) + value * 1.1)
        classifier_scores = {} if strong_structural else await self._zero_shot_classifier_scores(request.query)
        if classifier_scores:
            signals["zero_shot_classifier"] = {key.value: round(value, 4) for key, value in classifier_scores.items()}
            structural_signals = signals.get("structural") if isinstance(signals.get("structural"), dict) else {}
            accepted_classifier_scores: dict[CapabilityKind, float] = {}
            for kind, value in classifier_scores.items():
                if value < 0.55:
                    continue
                semantic_agrees = semantic_scores.get(kind, 0.0) >= 0.05
                structural_agrees = bool(structural_signals.get(kind.value))
                if semantic_agrees or structural_agrees:
                    accepted_classifier_scores[kind] = value
            if accepted_classifier_scores:
                signals["zero_shot_classifier_accepted"] = {
                    key.value: round(value, 4) for key, value in accepted_classifier_scores.items()
                }
            for kind, value in accepted_classifier_scores.items():
                scores[kind] = min(1.0, scores.get(kind, 0.0) + value * 0.88)
        structural_signals = signals.get("structural") if isinstance(signals.get("structural"), dict) else {}
        if structural_signals.get(CapabilityKind.CREATIVE_TEXT.value, 0.0) >= 0.6:
            scores[CapabilityKind.MEMORY_CHAT] = min(scores[CapabilityKind.MEMORY_CHAT], max(scores[CapabilityKind.CREATIVE_TEXT] - 0.08, 0.0))
        if not any(value > 0.16 for value in scores.values()):
            if semantic_scores:
                semantic_kind, semantic_value = max(semantic_scores.items(), key=lambda item: item[1])
                scores[semantic_kind] = max(scores.get(semantic_kind, 0.0), min(0.24, 0.12 + semantic_value))
                signals["fallback"] = f"low_confidence_semantic_{semantic_kind.value}"
            else:
                scores[CapabilityKind.MEMORY_CHAT] = 0.28
                signals["fallback"] = "memory_chat"
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
        kind = ranked[0][0] if ranked else CapabilityKind.MEMORY_CHAT
        top_score = ranked[0][1] if ranked else 0.0
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        # IR override: when the semantic compiler has high confidence that the
        # request is code generation (CODE_GENERATE), trust that signal over the
        # capability router's score — it has more query context. This prevents
        # "Write a Python async task queue" from landing on agentic_task when
        # the IR correctly identified it as CODE_GENERATE.
        if ir.target_ir == "CODE_GENERATE" and kind != CapabilityKind.CODING:
            kind = CapabilityKind.CODING
            top_score = max(top_score, scores.get(CapabilityKind.CODING, 0.35))

        confidence = self._confidence(top_score, second_score)
        reason = self._reason_for(kind, signals)
        secondary = [candidate for candidate, score in ranked[1:4] if score >= 0.44 and top_score - score <= 0.28]

        if self._should_adjudicate_with_llm(confidence, top_score, second_score, signals):
            overlay = await self._llm_overlay(request.query, ir, scores, signals)
            if overlay:
                overlay_kind = overlay.get("kind")
                overlay_confidence = overlay.get("confidence", 0.0)
                if isinstance(overlay_kind, CapabilityKind) and overlay_confidence >= max(confidence, 0.58):
                    kind = overlay_kind
                    confidence = min(0.92, max(confidence, float(overlay_confidence)))
                    reason = str(overlay.get("reason") or reason)
                    overlay_secondary = overlay.get("secondary") or []
                    secondary = [item for item in overlay_secondary if isinstance(item, CapabilityKind) and item != kind][:3]
                    signals["llm_overlay"] = {
                        "kind": kind.value,
                        "confidence": round(confidence, 4),
                        "secondary": [item.value for item in secondary],
                        "reason": reason,
                    }

        plan = self._plan_for(
            kind,
            confidence,
            reason,
            secondary_intents=secondary,
            routing_signals={"scores": {key.value: round(value, 4) for key, value in scores.items()}, **signals},
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
        scores = {kind: 0.0 for kind in CapabilityKind}
        signals: dict[str, Any] = {}
        for kind, prototype in CAPABILITY_PROTOTYPES.items():
            scores[kind] += self._prototype_similarity(tokens, _tokens(prototype)) * 0.24
        structural = self._structural_scores(query, tokens, activation)
        signals["structural"] = {key.value: round(value, 4) for key, value in structural.items() if value > 0}
        for kind, value in structural.items():
            scores[kind] += value
        if structural.get(CapabilityKind.CREATIVE_TEXT, 0.0) >= 0.6:
            scores[CapabilityKind.MEMORY_CHAT] *= 0.35
        return {kind: min(value, 1.0) for kind, value in scores.items()}, signals

    def _prototype_similarity(self, query_tokens: set[str], prototype_tokens: set[str]) -> float:
        if not query_tokens or not prototype_tokens:
            return 0.0
        overlap = len(query_tokens & prototype_tokens) / max(len(query_tokens), 1)
        query_joined = " ".join(sorted(query_tokens))
        proto_joined = " ".join(sorted(prototype_tokens))
        qgrams = self._char_grams(query_joined)
        pgrams = self._char_grams(proto_joined)
        gram_overlap = len(qgrams & pgrams) / max(len(qgrams), 1) if qgrams else 0.0
        return min(1.0, overlap * 0.72 + gram_overlap * 0.28)

    def _char_grams(self, value: str, width: int = 4) -> set[str]:
        compact = re.sub(r"\s+", " ", value.lower()).strip()
        return {compact[index : index + width] for index in range(max(len(compact) - width + 1, 0))}

    def _structural_scores(self, query: str, tokens: set[str], activation: ActivationDecision) -> dict[CapabilityKind, float]:
        scores = {kind: 0.0 for kind in CapabilityKind}
        generation = self._has_generate(query)
        if self._looks_like_numeric_math(query):
            scores[CapabilityKind.MATH_SCIENCE] += 0.82
        if re.search(r"```|traceback|^\s*(import|from|def|class)\s+", query, re.MULTILINE):
            scores[CapabilityKind.CODING] += 0.78
        if re.search(r"\b[a-z0-9_.-]+\.(py|js|ts|tsx|jsx|sql|md|json|yaml|yml|toml)\b", query):
            scores[CapabilityKind.CODING] += 0.45
        if self._matches(tokens, {"sql", "migration", "schema", "index", "indexes", "database", "table", "function", "api", "component"}):
            scores[CapabilityKind.CODING] += 0.68
        if generation and self._matches(tokens, {"image", "picture", "photo", "logo", "poster", "illustration", "visual"}):
            scores[CapabilityKind.IMAGE_GENERATION] += 0.82
        if generation and self._matches(tokens, {"audio", "voice", "speech", "tts", "sound", "music"}):
            scores[CapabilityKind.AUDIO_GENERATION] += 0.8
        if generation and self._matches(tokens, {"video", "animation", "clip", "movie", "storyboard"}):
            scores[CapabilityKind.VIDEO_GENERATION] += 0.8
        if self._matches(tokens, {"latest", "today", "news", "web", "internet", "search", "browse", "president", "price", "weather"}):
            scores[CapabilityKind.WORLD_KNOWLEDGE] += 0.72
        if self._matches(tokens, {"book", "send", "click", "schedule", "automate", "deploy", "rollback"}) and self._matches(
            tokens, {"agent", "task", "browser", "email", "site", "production", "calendar"}
        ):
            # Guard: don't score agentic when strong code signals are present.
            # "Write a Python async task queue" matches "task" but is clearly coding.
            strong_code = (
                self._matches(tokens, {"python", "javascript", "typescript", "async", "asyncio", "function", "method", "class", "queue"})
                or re.search(r"```|def\s+\w+|class\s+\w+|import\s+\w+", query)
                or self._matches(tokens, {"code", "write", "implement", "build"}) and self._matches(tokens, {"function", "class", "queue", "api", "test", "tests"})
            )
            if not strong_code:
                scores[CapabilityKind.AGENTIC_TASK] += 0.72
        if generation and self._matches(tokens, {"story", "poem", "script", "email", "proposal", "copy", "tone", "rewrite"}):
            scores[CapabilityKind.CREATIVE_TEXT] += 0.82
        if activation.route in {"invention", "canvas"}:
            scores[CapabilityKind.CREATIVE_TEXT] += 0.32
        if self._matches(tokens, {"remember", "memory", "trained", "learned", "source", "sources", "project", "profile", "what"}) and not any(
            value >= 0.7 for value in scores.values()
        ):
            scores[CapabilityKind.MEMORY_CHAT] += 0.4
        return scores

    def _matches(self, tokens: set[str], keywords: set[str]) -> bool:
        return bool(tokens & keywords)

    def _has_generate(self, query: str) -> bool:
        return any(word in query for word in ("generate", "create", "make", "draw", "produce", "edit", "write", "rewrite", "draft"))

    def _looks_like_numeric_math(self, query: str) -> bool:
        numeric_count = len(re.findall(r"\d+(?:\.\d+)?", query))
        has_symbolic_op = bool(re.search(r"[+\-*/=]", query))
        word_ops = (
            r"\b(multiplied\s+by|times|divided\s+by|over|plus|added\s+to|minus|"
            r"subtracted\s+from|to\s+the\s+power\s+of|squared|cubed)\b"
        )
        has_word_op = bool(re.search(word_ops, query, re.IGNORECASE))
        return numeric_count >= 1 and (has_symbolic_op or has_word_op)

    def _confidence(self, top_score: float, second_score: float) -> float:
        if top_score <= 0:
            return 0.5
        margin = max(top_score - second_score, 0.0)
        return round(min(0.94, max(0.5, 0.48 + top_score * 0.45 + margin * 0.35)), 4)

    def _reason_for(self, kind: CapabilityKind, signals: dict[str, Any]) -> str:
        structural = signals.get("structural") if isinstance(signals.get("structural"), dict) else {}
        if structural.get(kind.value):
            return f"Structural and semantic routing selected {kind.value}."
        return f"Semantic capability prototype routing selected {kind.value}."

    def _should_adjudicate_with_llm(self, confidence: float, top_score: float, second_score: float, signals: dict[str, Any]) -> bool:
        if not self.bridge:
            return False
        structural = signals.get("structural") if isinstance(signals.get("structural"), dict) else {}
        multilingual_without_structure = signals.get("language_hint") != "unknown_or_english" and not structural and top_score < 0.75
        ambiguous = confidence < 0.62 or top_score - second_score < 0.16
        return multilingual_without_structure or ambiguous

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
                "query_language_hint": self._language_hint(query),
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
                    f"{self.embedding_url}/v1/embed",
                    headers=headers,
                    json={"texts": [query], "purpose": "query"},
                )
                query_response.raise_for_status()
                prototype_response = await client.post(
                    f"{self.embedding_url}/v1/embed",
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
        if re.search(r"[\u0600-\u06ff]", query):
            return "arabic"
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", query):
            return "cjk"
        if re.search(r"[¿¡ñáéíóúü]", query.lower()):
            return "spanish_or_latin"
        return "unknown_or_english"


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
            "image_generation_available": bool(os.getenv("JIMS_IMAGE_GENERATION_URL") or os.getenv("OPENAI_API_KEY") or os.getenv("REPLICATE_API_TOKEN")),
            "audio_generation_available": bool(os.getenv("JIMS_AUDIO_GENERATION_URL") or os.getenv("OPENAI_API_KEY")),
            "video_generation_available": bool(os.getenv("JIMS_VIDEO_GENERATION_URL") or os.getenv("RUNWAY_API_KEY") or os.getenv("REPLICATE_API_TOKEN")),
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
