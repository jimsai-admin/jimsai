from __future__ import annotations

import os
import re

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


class CapabilityRouter:
    """V9 capability router.

    This layer classifies broad task capability without executing tools or answering.
    It preserves v8 separation: routing is structured, adapters are explicit, and
    final claims still pass through retrieval, verification, and CSSE.
    """

    def route(self, request: PipelineRequest, ir: SemanticIR, activation: ActivationDecision) -> tuple[CapabilityPlan, LayerResult]:
        query = request.query.lower()
        tokens = _tokens(request.query)
        kind = CapabilityKind.MEMORY_CHAT
        reason = "Default memory-first chat path."
        confidence = 0.58

        if self._matches(tokens, {"image", "picture", "photo", "logo", "poster", "illustration", "draw"}) and self._has_generate(query):
            kind, reason, confidence = CapabilityKind.IMAGE_GENERATION, "Request asks to generate or edit an image.", 0.82
        elif self._matches(tokens, {"video", "animation", "clip", "movie"}) and self._has_generate(query):
            kind, reason, confidence = CapabilityKind.VIDEO_GENERATION, "Request asks to generate video.", 0.82
        elif self._matches(tokens, {"audio", "voice", "speech", "tts", "sound", "music"}) and self._has_generate(query):
            kind, reason, confidence = CapabilityKind.AUDIO_GENERATION, "Request asks to generate audio or speech.", 0.8
        elif self._matches(tokens, {"code", "bug", "error", "library", "package", "api", "sdk", "typescript", "python", "react", "fastapi", "test", "refactor"}):
            kind, reason, confidence = CapabilityKind.CODING, "Request likely needs code, docs, tests, or sandbox execution.", 0.74
        elif self._matches(tokens, {"calculate", "solve", "equation", "proof", "theorem", "physics", "chemistry", "biology", "math", "derive"}):
            kind, reason, confidence = CapabilityKind.MATH_SCIENCE, "Request needs solver-backed math or science verification.", 0.72
        elif self._matches(tokens, {"latest", "current", "today", "news", "web", "internet", "search", "browse", "president", "price", "weather"}):
            kind, reason, confidence = CapabilityKind.WORLD_KNOWLEDGE, "Request depends on changing or public-world knowledge.", 0.78
        elif self._matches(tokens, {"write", "story", "poem", "script", "rewrite", "tone", "creative", "email", "proposal"}):
            kind, reason, confidence = CapabilityKind.CREATIVE_TEXT, "Request is primarily creative or style-oriented text generation.", 0.64
        elif self._matches(tokens, {"deploy", "book", "send", "click", "browser", "schedule", "automate", "agent", "task"}):
            kind, reason, confidence = CapabilityKind.AGENTIC_TASK, "Request asks for multi-step tool execution.", 0.7
        elif activation.route in {"invention", "canvas"}:
            kind, reason, confidence = CapabilityKind.CREATIVE_TEXT, "Sparse activation selected synthesis/invention path.", 0.62

        plan = self._plan_for(kind, confidence, reason)
        return plan, LayerResult(
            layer="V9_capability_router",
            activated=True,
            deterministic=True,
            summary=f"Selected v9 capability route: {plan.kind.value}.",
            data=plan.model_dump(mode="json"),
        )

    def _plan_for(self, kind: CapabilityKind, confidence: float, reason: str) -> CapabilityPlan:
        common_verify = ["source_trace", "confidence_score", "gap_reporting", "csse_no_extra_claims"]
        plans: dict[CapabilityKind, CapabilityPlan] = {
            CapabilityKind.MEMORY_CHAT: CapabilityPlan(
                kind=kind,
                route="memory_first",
                confidence=confidence,
                reason=reason,
                verification_requirements=[*common_verify, "workspace_scope"],
                energy_profile="low",
                context_strategy="persistent_memory",
            ),
            CapabilityKind.WORLD_KNOWLEDGE: CapabilityPlan(
                kind=kind,
                route="web_augmented_retrieval",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["web_search", "source_fetch"],
                verification_requirements=[*common_verify, "freshness_check", "source_citation"],
                energy_profile="medium",
                context_strategy="tool_augmented",
            ),
            CapabilityKind.CODING: CapabilityPlan(
                kind=kind,
                route="code_docs_sandbox",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["code_docs", "test_runner", "package_metadata"],
                verification_requirements=[*common_verify, "test_or_static_check", "version_awareness"],
                energy_profile="medium",
                context_strategy="tool_augmented",
            ),
            CapabilityKind.MATH_SCIENCE: CapabilityPlan(
                kind=kind,
                route="solver_verified",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["calculator", "symbolic_solver", "paper_retrieval"],
                verification_requirements=[*common_verify, "calculation_trace"],
                energy_profile="medium",
                context_strategy="tool_augmented",
            ),
            CapabilityKind.CREATIVE_TEXT: CapabilityPlan(
                kind=kind,
                route="csse_style_memory",
                confidence=confidence,
                reason=reason,
                allowed_adapters=["t2_render", "style_memory"],
                verification_requirements=["style_constraints", "user_intent_preservation"],
                energy_profile="low",
                context_strategy="bounded_retrieval",
            ),
            CapabilityKind.IMAGE_GENERATION: CapabilityPlan(
                kind=kind,
                route="image_generation_provider",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["image_generation"],
                verification_requirements=["prompt_safety", "asset_provenance", "human_review_optional"],
                energy_profile="high",
                context_strategy="generation_provider",
            ),
            CapabilityKind.AUDIO_GENERATION: CapabilityPlan(
                kind=kind,
                route="audio_generation_provider",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["tts_audio_generation"],
                verification_requirements=["voice_rights", "prompt_safety", "asset_provenance"],
                energy_profile="high",
                context_strategy="generation_provider",
            ),
            CapabilityKind.VIDEO_GENERATION: CapabilityPlan(
                kind=kind,
                route="video_generation_provider",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["video_generation"],
                verification_requirements=["prompt_safety", "asset_provenance", "human_review_required"],
                energy_profile="high",
                context_strategy="generation_provider",
                human_approval_required=True,
            ),
            CapabilityKind.AGENTIC_TASK: CapabilityPlan(
                kind=kind,
                route="approved_tool_execution",
                confidence=confidence,
                reason=reason,
                requires_external_adapter=True,
                allowed_adapters=["tool_registry", "browser", "api_executor", "job_queue"],
                verification_requirements=["permission_check", "dry_run", "rollback_plan", "audit_log"],
                energy_profile="medium",
                context_strategy="tool_augmented",
                human_approval_required=True,
            ),
        }
        return plans[kind]

    def _matches(self, tokens: set[str], keywords: set[str]) -> bool:
        return bool(tokens & keywords)

    def _has_generate(self, query: str) -> bool:
        return any(word in query for word in ("generate", "create", "make", "draw", "produce", "edit"))


class CapabilityAdapterRegistry:
    """Structured provider registry for v9 capabilities.

    Existing memory/chat runs do not need a tool result. Provider-backed capabilities
    return availability signals until their concrete adapters are configured.
    """

    def readiness(self) -> dict[str, bool | str]:
        return {
            "web_search_available": bool(os.getenv("JIMS_WEB_SEARCH_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("SERPAPI_API_KEY")),
            "code_docs_available": bool(os.getenv("JIMS_CODE_DOCS_PROVIDER")),
            "math_solver_available": bool(os.getenv("JIMS_MATH_SOLVER_URL") or os.getenv("WOLFRAM_APP_ID")),
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
