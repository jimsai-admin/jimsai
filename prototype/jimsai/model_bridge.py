from __future__ import annotations

import json
import os
import re
from typing import Any

from .models import VerifiedCognitiveObject

import httpx


class QwenBridge:
    """Bounded local Qwen adapter for T1/T2/Canvas/Invention/Ingest interfaces.

    All LLM calls route to the Hugging Face Space running Qwen3-1.7B (intent/routing)
    and Qwen3-4B (render/canvas/invention/ingest) via the configured HF Space endpoints.

    The bridge is deliberately not a reasoning engine. It interprets messy input
    into candidate JSON, or renders an already-verified cognitive object into natural
    language. The deterministic runtime remains authoritative; the bridge only
    activates when the local Qwen service is available and reachable.
    """

    def __init__(self) -> None:
        self.local_first = (
            os.getenv("JIMS_LLM_PROVIDER", "").strip().lower() in {"local", "qwen", "qwen3", "huggingface"}
            or os.getenv("JIMS_ENABLE_LOCAL_QWEN", "false").lower() in {"1", "true", "yes", "on"}
        )
        self.local_url = (
            os.getenv("JIMS_LOCAL_INFERENCE_URL", "")
            or os.getenv("JIMS_QWEN_SERVICE_URL", "")
            or (os.getenv("JIMS_EMBEDDING_SERVICE_URL", "") if self.local_first else "")
        ).strip().rstrip("/")
        self.local_api_key = (
            os.getenv("JIMS_LOCAL_INFERENCE_API_KEY", "")
            or os.getenv("JIMS_QWEN_SERVICE_TOKEN", "")
            or os.getenv("JIMS_EMBEDDING_SERVICE_TOKEN", "")
            or os.getenv("JIMS_RENDER_AGENT_TOKEN", "")
        )
        # T1 model: Qwen3-1.7B for intent/routing/math extraction (fast, small JSON output)
        self.local_model = os.getenv(
            "JIMS_LOCAL_INFERENCE_MODEL",
            os.getenv("JIMS_QWEN_MODEL", "qwen3-1.7b-instruct"),
        )
        # T2 model: Qwen3-4B for render/canvas/invention/ingest (larger, richer output)
        self.local_render_model = os.getenv(
            "JIMS_LOCAL_RENDER_MODEL",
            os.getenv("JIMS_RENDER_MODEL_NAME", "qwen3-4b-instruct"),
        )
        self.local_chat_path = (
            os.getenv("JIMS_LOCAL_INFERENCE_CHAT_PATH", "/v1/chat/completions").strip()
            or "/v1/chat/completions"
        )
        self.local_render_path = (
            os.getenv("JIMS_LOCAL_RENDER_CHAT_PATH", "/v1/chat/render").strip()
            or "/v1/chat/render"
        )

        # Single unified availability flag: Qwen is available iff local_first + local_url
        # (replaces the old per-feature enabled_t1/t2/canvas/invention/ingest flags)
        self.adaptive_thinning = os.getenv(
            "JIMS_ADAPTIVE_TRANSFORMER_THINNING", "true"
        ).lower() in {"1", "true", "yes", "on"}
        self.t1_skip_confidence = float(os.getenv("JIMS_T1_SKIP_CONFIDENCE", "0.68") or "0.68")
        self.t2_skip_confidence = float(os.getenv("JIMS_T2_SKIP_CONFIDENCE", "0.82") or "0.82")
        self.last_t1_skip_reason = ""
        self.last_t2_skip_reason = ""

    # ── Availability ──────────────────────────────────────────────────────────

    @property
    def qwen_enabled(self) -> bool:
        """True when the Qwen HF Space endpoint is configured and local-first mode is on."""
        return bool(self.local_first and self.local_url)

    @property
    def available(self) -> bool:
        """Alias for qwen_enabled — kept for backward compatibility."""
        return self.qwen_enabled

    # ── Low-level HTTP ────────────────────────────────────────────────────────

    async def _chat_json(
        self, _model_hint: str, system: str, user: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        """Route to T1 Qwen (intent model) via /v1/chat/completions."""
        if not self.qwen_enabled:
            return None
        return await self._local_chat_json(system, user, max_tokens=max_tokens)

    async def _render_chat_json(
        self, system: str, user: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        """Route to T2 Qwen (render model) via /v1/chat/render."""
        if not self.qwen_enabled:
            return None
        return await self._local_chat_json(
            system,
            user,
            max_tokens=max_tokens,
            path=self.local_render_path,
            model=self.local_render_model,
            timeout=float(
                os.getenv(
                    "JIMS_LOCAL_RENDER_TIMEOUT",
                    os.getenv("JIMS_LOCAL_INFERENCE_TIMEOUT", "90"),
                )
                or "90"
            ),
        )

    async def _local_chat_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        path: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        headers = {"Content-Type": "application/json"}
        if self.local_api_key:
            headers["Authorization"] = f"Bearer {self.local_api_key}"
        payload = {
            "model": model or self.local_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            request_timeout = timeout if timeout is not None else float(
                os.getenv("JIMS_LOCAL_INFERENCE_TIMEOUT", "45") or "45"
            )
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.post(
                    f"{self.local_url}{path or self.local_chat_path}",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None

    # ── T1: Intent / routing / math ───────────────────────────────────────────

    async def infer_intent(
        self, raw_input: str, deterministic_ir: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Bounded T1 intent overlay — only refines, never overrides a high-confidence IR."""
        self.last_t1_skip_reason = ""
        if not self.qwen_enabled:
            self.last_t1_skip_reason = "qwen_unavailable"
            return None
        if self._should_skip_t1(deterministic_ir):
            confidence = float(deterministic_ir.get("confidence") or 0.0)
            self.last_t1_skip_reason = f"deterministic_confidence_{confidence:.2f}"
            return None
        system = (
            "You are the bounded T1 intent interface for JIMS-AI. "
            "Return only JSON. You may classify ambiguity, tone, and intent. "
            "You must not execute, retrieve, reason, plan, or invent."
        )
        user = json.dumps(
            {
                "raw_input": raw_input,
                "deterministic_ir": deterministic_ir,
                "allowed_targets": [
                    "WORKSPACE_QUERY",
                    "FETCH_DOCUMENT",
                    "SYSTEM_DIAGNOSTIC",
                    "CODE_GENERATE",
                    "RUN_CANVAS",
                    "RUN_INVENTION",
                    "GENERAL_FACT",
                    "EMOTIONAL_CATCH",
                    "META_INQUIRY",
                ],
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=400)

    async def classify_capability(
        self, raw_input: str, deterministic_context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Bounded capability router — supplements the zero-shot classifier."""
        enabled = os.getenv("JIMS_ENABLE_LLM_CAPABILITY_ROUTER", "").lower()
        if enabled not in {"1", "true", "yes", "on"} and not (
            self.qwen_enabled and enabled != "false"
        ):
            return None
        system = (
            "You are the bounded v9 capability router for JIMS-AI. Return only JSON. "
            "Classify what capability or capabilities are needed; do not answer the user, "
            "execute tools, or invent facts. Use primary_kind and optional secondary_kinds "
            "from the allowed list only."
        )
        user = json.dumps(
            {
                "raw_input": raw_input,
                "deterministic_context": deterministic_context,
                "allowed_kinds": [
                    "memory_chat",
                    "world_knowledge",
                    "coding",
                    "math_science",
                    "creative_text",
                    "image_generation",
                    "audio_generation",
                    "video_generation",
                    "agentic_task",
                ],
                "schema": {
                    "primary_kind": "string",
                    "secondary_kinds": ["string"],
                    "confidence": "number between 0 and 1",
                    "reason": "short string",
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=180)

    async def extract_math_expression(
        self, raw_input: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Extract a safe arithmetic/equation expression from freeform text."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are a bounded math-expression normalizer for JIMS-AI. Return only JSON. "
            "Extract a safe arithmetic or simple equation expression from the user text in any language. "
            "Do not solve it. Do not add assumptions. "
            "If no bounded expression exists, return expression as an empty string."
        )
        user = json.dumps(
            {
                "raw_input": raw_input,
                "context": context or {},
                "schema": {
                    "expression": "string using only digits, variables, +, -, *, /, parentheses, decimal points, and optional =",
                    "solve_for": "single variable string or null",
                    "confidence": "number between 0 and 1",
                    "reason": "short string",
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=160)

    # ── T2: Render / Canvas / Invention / Ingest ──────────────────────────────

    async def canvas_synthesis(self, content: str) -> dict[str, Any] | None:
        """Bounded Active Canvas synthesis — returns JSON patterns only."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are the bounded Active Canvas interface for JIMS-AI. "
            "Return JSON with patterns only. Do not answer the user."
        )
        return await self._render_chat_json(system, content[:12000], max_tokens=1000)

    async def invention_candidates(
        self, goal: str, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Generate bounded invention candidate steps, constrained by supplied context."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are a bounded invention candidate generator for JIMS-AI. "
            "Return JSON candidates constrained by provided memory/context. "
            "Do not make factual claims beyond the supplied context."
        )
        return await self._render_chat_json(
            system,
            json.dumps({"goal": goal, "context": context}),
            max_tokens=1000,
        )

    async def extract_ingestion_memory(
        self, content: str, context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Structured extraction of memory objects from ingested content."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are the bounded ingestion intelligence layer for JIMS-AI. "
            "Return only JSON. Interpret the input into memory objects, but do not answer the user. "
            "Vectors are retrieval hints, not truth. Prefer provenance-backed facts, entities, relations, "
            "document metadata, uncertainty, and correction-ready structure. Use only the supplied input."
        )
        user = json.dumps(
            {
                "content": content[:16000],
                "context": context,
                "schema": {
                    "document_type": "string|null",
                    "title": "string|null",
                    "summary": "string|null",
                    "entities": [{"name": "string", "type": "string", "confidence": "number"}],
                    "relations": [
                        {"subject": "string", "predicate": "string", "object": "string", "confidence": "number"}
                    ],
                    "causal_links": [{"cause": "string", "effect": "string", "confidence": "number"}],
                    "facts": [
                        {"subject": "string", "predicate": "string", "object": "string", "confidence": "number"}
                    ],
                    "tags": ["string"],
                    "confidence": "number",
                },
            },
            sort_keys=True,
        )
        return await self._render_chat_json(system, user, max_tokens=1400)

    async def render(
        self, obj: VerifiedCognitiveObject, deterministic_render: str
    ) -> str | None:
        """Bounded T2 render — rephrase the CSSE output into natural Markdown."""
        self.last_t2_skip_reason = ""
        if not self.qwen_enabled:
            self.last_t2_skip_reason = "qwen_unavailable"
            return None
        if self._should_skip_t2(obj):
            self.last_t2_skip_reason = f"verified_confidence_{obj.confidence:.2f}"
            return None
        system = (
            "You are the bounded T2 render interface for JIMS-AI. "
            "Render the verified cognitive object as a natural, helpful, Markdown-friendly answer for the user. "
            "Use concise paragraphs, short lists only when useful, and a warm professional tone. "
            "Do not expose internal layer names, raw trace IDs, or robotic phrases like "
            "'Here's what I can verify from memory' unless the user asks for internals. "
            "Do not add claims, facts, sources, code, or conclusions not present in the object. "
            "If a gap is present, preserve it explicitly. Return JSON only with key response."
        )
        user = json.dumps(
            {
                "verified_cognitive_object": obj.model_dump(mode="json"),
                "deterministic_render": deterministic_render,
                "style_signature": obj.style_signature,
                "response_requirements": [
                    "Markdown-compatible",
                    "natural fluent language",
                    "follow explicit language and format requests from style_signature.user_prompt",
                    "no unsupported facts",
                    "include the verified result directly when present",
                    "include confidence/source note only when it helps the user",
                ],
            },
            sort_keys=True,
        )
        data = await self._render_chat_json(system, user, max_tokens=1200)
        if not data:
            return None
        rendered = data.get("response")
        return rendered if isinstance(rendered, str) and rendered.strip() else None

    # ── MCTS node evaluation ──────────────────────────────────────────────────

    async def evaluate_candidate_node(
        self, goal: str, parent_context: str, candidate_node: str
    ) -> float:
        """Score a candidate invention step for logical consistency (0.0–1.0)."""
        if not self.qwen_enabled:
            return 0.5
        system = (
            "You are a bounded logical consistency evaluator for JIMS-AI. Return only JSON. "
            "Evaluate the consistency and score of the candidate child node relative to the goal "
            "and parent context. Return a consistency score between 0.0 (completely logically "
            "inconsistent or incorrect) and 1.0 (perfectly consistent)."
        )
        user = json.dumps(
            {
                "goal": goal,
                "parent_context": parent_context,
                "candidate_node": candidate_node,
                "schema": {
                    "score": "number between 0.0 and 1.0 representing logical consistency",
                    "reason": "short string explaining the score",
                },
            },
            sort_keys=True,
        )
        res = await self._chat_json(self.local_model, system, user, max_tokens=150)
        if res and "score" in res:
            try:
                return float(res["score"])
            except (TypeError, ValueError):
                pass
        return 0.5

    # ── Thinning helpers ──────────────────────────────────────────────────────

    def _should_skip_t1(self, deterministic_ir: dict[str, Any]) -> bool:
        """Skip T1 overlay when the deterministic compiler is already high-confidence."""
        if not self.adaptive_thinning:
            return False
        try:
            confidence = float(deterministic_ir.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        target = str(deterministic_ir.get("target_ir") or "").upper()
        # Always run T1 for ambiguous or complex routes
        if target in {"OP_ESCAPE_TO_SANDBOX", "RUN_CANVAS", "RUN_INVENTION"}:
            return False
        if target in {"CODE_GENERATE", "GENERAL_FACT", "EMOTIONAL_CATCH"}:
            return False
        return confidence >= self.t1_skip_confidence

    def _should_skip_t2(self, obj: VerifiedCognitiveObject) -> bool:
        """Skip T2 render when the deterministic CSSE output is already high-quality."""
        if not self.adaptive_thinning:
            return False
        if obj.knowledge_gaps:
            return False
        if obj.generation_mode != "FACT":
            return False
        if not obj.sources:
            return False
        style = obj.style_signature or {}
        if str(style.get("language_hint") or "default") != "default":
            return False
        if str(style.get("format_hint") or "default") != "default":
            return False

        raw_prompt = str(style.get("user_prompt") or "").lower()
        words = set(raw_prompt.split())

        # Preserve T2 for conversational / low-resource / multilingual prompts
        conversational_signals = {
            "hello", "hi", "howdy", "please", "stressed", "help",
            "thanks", "thank you", "nibo", "bawo", "kedu", "sannu", "lafiya", "nagode",
        }
        if words & conversational_signals:
            return False

        # Preserve T2 when mixed digit/letter typos are present (OCR / casual input)
        if any(re.search(r"[A-Za-z]\d|\d[A-Za-z]", word) for word in words):
            return False

        return obj.confidence >= self.t2_skip_confidence


# ---------------------------------------------------------------------------
# Backward-compatibility alias — remove once all callers are updated
# ---------------------------------------------------------------------------
GroqBridge = QwenBridge
