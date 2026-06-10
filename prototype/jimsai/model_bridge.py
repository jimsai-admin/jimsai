from __future__ import annotations

import json
import os
import re
from typing import Any

from .env_config import get_env
from .models import VerifiedCognitiveObject

import httpx


class QwenBridge:
    """Bounded local Qwen adapter for T1/T2/Canvas/Invention/Ingest interfaces.

    All LLM calls route to Modal-hosted AI services:
      - Intent_Service (qwen-1.7b): T1 intent/routing via JIMS_INTENT_SERVICE_URL
      - Renderer_Service (qwen-4b): T2 render/canvas/invention via JIMS_RENDERER_SERVICE_URL
      - Reasoning_Service (qwen-8b): deep reasoning via JIMS_REASONING_SERVICE_URL

    The bridge is deliberately not a reasoning engine. It interprets messy input
    into candidate JSON, or renders an already-verified cognitive object into natural
    language. The deterministic runtime remains authoritative; the bridge only
    activates when the local Qwen service is available and reachable.

    ── Modal service env vars ────────────────────────────────────────────────

    T1 intent path → JIMS_INTENT_SERVICE_URL     (Modal Intent_Service)
    T2 render path → JIMS_RENDERER_SERVICE_URL   (Modal Renderer_Service)
    Auth key       → JIMS_MODAL_API_KEY           (shared Bearer token)

    ── Model env vars ────────────────────────────────────────────────────────

    T1 model (intent/routing/math extraction — Qwen3-1.7B):
      JIMS_LOCAL_INFERENCE_MODEL / JIMS_QWEN_MODEL — model name tag
      JIMS_QWEN_CONTEXT      — context window    (default 4096)

    T2 model (render/canvas/invention — Qwen3-4B):
      JIMS_LOCAL_RENDER_MODEL / JIMS_RENDER_MODEL_NAME — model name tag
      JIMS_RENDER_CONTEXT    — context window    (default 8192)

    ────────────────────────────────────────────────────────────────────────────
    """

class QwenBridge:
    """Bounded Modal AI bridge for T1/T2/Canvas/Invention/Ingest interfaces.

    All LLM calls route to Modal-hosted services exclusively:
      - Intent_Service  (Qwen3-1.7B): T1 intent/routing via JIMS_INTENT_SERVICE_URL
      - Renderer_Service (Qwen3-4B):  T2 render/canvas/invention via JIMS_RENDERER_SERVICE_URL
      - Reasoning_Service (Qwen3-8B): deep reasoning via JIMS_REASONING_SERVICE_URL

    Auth: JIMS_MODAL_API_KEY — shared Bearer token for all Modal services.
    """

    def __init__(self) -> None:
        # ── Modal service URLs ────────────────────────────────────────────────
        self.local_url = get_env("JIMS_INTENT_SERVICE_URL").rstrip("/")
        self.render_url = get_env("JIMS_RENDERER_SERVICE_URL").rstrip("/")
        self.local_api_key = get_env("JIMS_MODAL_API_KEY")

        # Model name tags (used in request payloads)
        self.local_model = get_env("JIMS_LOCAL_INFERENCE_MODEL", "qwen3-1.7b-instruct")
        self.local_render_model = get_env("JIMS_LOCAL_RENDER_MODEL", "qwen3-4b-instruct")

        # Endpoint paths on the Modal services
        self.local_chat_path = get_env("JIMS_LOCAL_INFERENCE_CHAT_PATH", "/generate") or "/generate"
        self.local_render_path = get_env("JIMS_LOCAL_RENDER_CHAT_PATH", "/generate") or "/generate"

        # LLM thinning — skip T1/T2 overlay when deterministic confidence is high
        self.adaptive_thinning = get_env("JIMS_ADAPTIVE_TRANSFORMER_THINNING", "true").lower() in {"1", "true", "yes", "on"}
        self.t1_skip_confidence = float(get_env("JIMS_T1_SKIP_CONFIDENCE", "0.60") or "0.60")
        self.t2_skip_confidence = float(get_env("JIMS_T2_SKIP_CONFIDENCE", "0.95") or "0.95")
        self.last_t1_skip_reason = ""
        self.last_t2_skip_reason = ""

    # ── Availability ──────────────────────────────────────────────────────────

    @property
    def qwen_enabled(self) -> bool:
        """True when Modal services are configured (both Intent and Renderer URLs set)."""
        return bool(self.local_url and self.render_url and self.local_api_key)

    @property
    def available(self) -> bool:
        """Alias for qwen_enabled — kept for backward compatibility."""
        return self.qwen_enabled

    def describe(self) -> dict[str, str]:
        """Return current model configuration for dashboard / observability."""
        return {
            "backend": "modal" if self.qwen_enabled else "none",
            "t1_model": self.local_model,
            "t2_model": self.local_render_model,
            "t1_endpoint": f"{self.local_url}{self.local_chat_path}",
            "t2_endpoint": f"{self.render_url}{self.local_render_path}",
            "qwen_enabled": str(self.qwen_enabled),
        }

    async def rewrite_for_clarity(self, raw_input: str) -> str | None:
        """Enhanced rewrite for clarity that handles multilingual and chaotic inputs better.

        Rewrite a chaotic/typo-heavy query into clear form without changing meaning.
        This enhanced version better handles multilingual inputs and chaotic prompts.

        Used by SemanticCompilerRuntime when embedding confidence is low (0.20–0.49)
        and JIMS_TYPO_CORRECTION_ENABLED=true. Only activates when qwen_enabled.

        Returns: cleaned query string, or None if Qwen is unavailable or no change needed.
        """
        if not self.qwen_enabled:
            return None
        system = (
            "You are an advanced text normalizer for JimsAI. "
            "Fix spelling mistakes, typos, and normalize input for better processing while preserving the original meaning. "
            "Handle multilingual inputs appropriately - preserve the original language but fix structural issues. "
            "Return JSON only: {\"clean\": \"corrected text here\"}"
        )
        data = await self._chat_json(self.local_model, system, raw_input[:512], max_tokens=120)
        if not data:
            return None
        clean = str(data.get("clean") or "").strip()
        return clean if clean and clean.lower() != raw_input.strip().lower() else None

    # ── Low-level HTTP ────────────────────────────────────────────────────────

    async def _chat_json(
        self, _model_hint: str, system: str, user: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        """Route to T1 Modal Intent_Service."""
        if not self.qwen_enabled:
            return None
        return await self._local_chat_json(system, user, max_tokens=max_tokens)

    async def _render_chat_json(
        self, system: str, user: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        """Route to T2 Modal Renderer_Service.

        Modal returns: {"response": "<model output>", "model": ..., "usage": ..., "finish_reason": ...}
        The model output may be:
          - A JSON string:  '{"response": "markdown text"}'  → parse → {"response": "markdown text"}
          - A JSON string:  '{"candidate_steps": [...]}'     → parse → {"candidate_steps": [...]}
          - Plain markdown: 'Here is your answer...'         → wrap  → {"response": "Here is your answer..."}
        """
        if not self.qwen_enabled:
            return None
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.local_api_key}"}
        payload = {
            "model": self.local_render_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            timeout = float(os.getenv("JIMS_GENERATION_TIMEOUT", "120") or "120")
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.render_url}{self.local_render_path}",
                    headers=headers,
                    json=payload,
                    follow_redirects=True,
                )
                response.raise_for_status()
            data = response.json()
            # Modal returns {"response": "<model output>", ...}
            raw_content = data.get("response") or data.get("content") or ""
            if not raw_content and "choices" in data:
                # Tolerate OpenAI-compatible wrapper
                raw_content = data["choices"][0]["message"]["content"]
            if not raw_content:
                import logging as _log
                _log.getLogger(__name__).warning("_render_chat_json: empty response field from Modal renderer")
                return None
            # Strip Qwen3 <think>...</think> blocks
            raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            if not raw_content:
                return None
            # Try to parse as JSON object
            start, end = raw_content.find("{"), raw_content.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(raw_content[start:end + 1])
                except json.JSONDecodeError:
                    pass
            # Model returned plain text instead of JSON — wrap it as {"response": ...}
            # This handles cases where the model ignores the JSON instruction but
            # still gives a useful answer (common with T2 long renders)
            return {"response": raw_content}
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("_render_chat_json failed: %s", repr(exc))
            return None

    async def _local_chat_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        path: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        """Route to T1 Modal Intent_Service.

        Modal returns: {"response": "<model output>", "model": ..., "usage": ..., "finish_reason": ...}
        The model output must be a JSON object (T1 is always structured). If parsing
        fails, return None so the deterministic path takes over gracefully.
        """
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
        }
        try:
            request_timeout = timeout if timeout is not None else float(
                os.getenv("JIMS_GENERATION_TIMEOUT",
                          os.getenv("JIMS_LOCAL_INFERENCE_TIMEOUT", "120")) or "120"
            )
            async with httpx.AsyncClient(timeout=request_timeout, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.local_url}{path or self.local_chat_path}",
                    headers=headers,
                    json=payload,
                    follow_redirects=True,
                )
                response.raise_for_status()
            data = response.json()
            # Modal Intent_Service returns {"response": "<model output>", ...}
            raw_content = data.get("response") or data.get("content") or ""
            if not raw_content and "choices" in data:
                raw_content = data["choices"][0]["message"]["content"]
            if not raw_content:
                return None
            # Strip Qwen3 thinking blocks (various formats)
            # Qwen3 outputs: "think...done" or "thinking...done" or "think...done" blocks
            raw_content = re.sub(r"(?i)think.*?done", "", raw_content, flags=re.DOTALL).strip()
            raw_content = re.sub(r"(?i)think.*?done", "", raw_content, flags=re.DOTALL).strip()
            raw_content = re.sub(r"(?i)\[think\].*?\[/think\]", "", raw_content, flags=re.DOTALL).strip()
            # Also strip any leading "think" or "Thinking" blocks without "done"
            raw_content = re.sub(r"(?i)^think\s*\n", "", raw_content).strip()
            raw_content = re.sub(r"(?i)^thinking\s*\n", "", raw_content).strip()
            # Strip Qwen3 thinking blocks (various formats)
            # Qwen3 outputs: "think...done" or "thinking...done" or "think...done" blocks
            raw_content = re.sub(r"(?i)think.*?done", "", raw_content, flags=re.DOTALL).strip()
            raw_content = re.sub(r"(?i)think.*?done", "", raw_content, flags=re.DOTALL).strip()
            raw_content = re.sub(r"(?i)\[think\].*?\[/think\]", "", raw_content, flags=re.DOTALL).strip()
            # Also strip any leading "think" or "Thinking" blocks without "done"
            raw_content = re.sub(r"(?i)^think\s*\n", "", raw_content).strip()
            raw_content = re.sub(r"(?i)^thinking\s*\n", "", raw_content).strip()
            # If still starts with reasoning, strip everything before first JSON object
            if raw_content and not raw_content.startswith("{"):
                # Find first { that looks like JSON start
                first_brace = raw_content.find("{")
                if first_brace > 0:
                    # Check if it's a valid JSON start
                    potential_json = raw_content[first_brace:]
                    try:
                        import json
                        json.loads(potential_json[:potential_json.rfind("}")+1])
                        raw_content = potential_json
                    except:
                        pass
                # Also try: if content starts with "think" or "Thinking" (case insensitive)
                # strip everything before the first {
                if raw_content.lstrip().lower().startswith("think"):
                    first_brace = raw_content.find("{")
                    if first_brace > 0:
                        raw_content = raw_content[first_brace:]
            # AGGRESSIVE: If still not starting with {, find first { and use that
            if raw_content and not raw_content.startswith("{"):
                first_brace = raw_content.find("{")
                import logging as _log
                _log.getLogger(__name__).debug("_local_chat_json: before aggressive extract - first_brace=%d, content_start=%s", first_brace, raw_content[:100])
                if first_brace > 0:
                    raw_content = raw_content[first_brace:]
                    _log.getLogger(__name__).debug("_local_chat_json: after aggressive extract - new content: %s", raw_content[:100])
            import logging as _log
            _log.getLogger(__name__).debug("_local_chat_json: after strip (len=%d): %s", len(raw_content), raw_content[:500])
            if not raw_content:
                return None
            # Extract and parse JSON object
            start, end = raw_content.find("{"), raw_content.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(raw_content[start:end + 1])
                except json.JSONDecodeError:
                    pass
            # T1 must be JSON — if we can't parse it, fall back to deterministic path
            import logging as _log
            _log.getLogger(__name__).debug(
                "_local_chat_json: model returned non-JSON T1 response (len=%d): %s",
                len(raw_content), raw_content[:500]
            )
            return None
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("_local_chat_json failed: %s", repr(exc))
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
            "You are an intent classifier. Return only JSON with target_ir and confidence. "
            "Allowed targets: WORKSPACE_QUERY, FETCH_DOCUMENT, SYSTEM_DIAGNOSTIC, CODE_GENERATE, "
            "RUN_CANVAS, RUN_INVENTION, GENERAL_FACT, EMOTIONAL_CATCH, META_INQUIRY. "
            "Do not reason or explain. Output only the JSON object."
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
        """Generate runnable code candidates for any programming language or design task.

        The system prompt deliberately avoids hardcoding any language name — the
        model infers language from the goal/context and produces actual implementation
        code.  This covers all programming languages, query languages, markup, config
        formats, and system-design tasks without any per-language special-casing.
        """
        if not self.qwen_enabled:
            return None

        # Determine what kind of generation is needed from the context.
        # 'failed_code' in context means a sandbox error occurred — we need a fix.
        # 'context' (deeper stage) means we need to expand an existing solution.
        # Default: produce a complete working implementation for the goal.
        stage = str(context.get("stage") or "initial")
        failed_code = str(context.get("failed_code") or "").strip()
        error_msg = str(context.get("error") or "").strip()

        if failed_code and error_msg:
            # Correction pass: fix the broken code
            system = (
                "You are a code correction engine. "
                "The user tried to run code but it failed. "
                "Fix the code so it runs correctly. "
                "Return JSON with key 'candidate_steps' containing a list with one element: "
                "the complete corrected code as a single string. "
                "The code must be complete and runnable. "
                "Do not add explanations outside the JSON."
            )
            user_content = json.dumps({
                "goal": goal,
                "broken_code": failed_code,
                "error": error_msg,
            }, sort_keys=True)
        elif stage == "deeper":
            # Expansion pass: improve or extend an existing solution
            system = (
                "You are a code improvement engine. "
                "You are given an existing implementation and must improve, extend, or complete it. "
                "Return JSON with key 'candidate_steps' containing a list with one element: "
                "the complete improved code as a single string. "
                "The code must be complete and runnable. "
                "Do not add explanations outside the JSON."
            )
            user_content = json.dumps({
                "goal": goal,
                "existing_code": str(context.get("context") or ""),
            }, sort_keys=True)
        else:
            # Initial generation: produce a full working implementation
            # The language and framework are inferred entirely from the goal —
            # no language is hardcoded here, so Python, JavaScript, TypeScript,
            # Rust, SQL, Go, Bash, YAML, Terraform, etc. all work the same way.
            system = (
                "You are a code generation engine that supports all programming languages. "
                "Given a coding goal, write a complete, working implementation. "
                "Infer the programming language from the goal. "
                "Include all necessary imports, type hints where idiomatic, "
                "docstrings, and error handling. "
                "Return JSON with key 'candidate_steps' containing a list with one element: "
                "the complete implementation as a single string. "
                "The code must be self-contained and runnable. "
                "Do not add explanations outside the JSON."
            )
            user_content = json.dumps({
                "goal": goal,
                "context": {k: v for k, v in context.items() if k not in ("stage",)},
            }, sort_keys=True)

        return await self._render_chat_json(
            system,
            user_content,
            max_tokens=2000,
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
            "If a gap is present, preserve it explicitly. "
            "IMPORTANT — Code generation rules: "
            "If any reasoning_chain step has relation='CODE_GENERATION', treat its claim as "
            "the complete implementation. Present it in a fenced code block with the correct "
            "language tag inferred from the code content (python, javascript, typescript, sql, "
            "rust, go, bash, yaml, etc.). Add a brief one-sentence description before the block "
            "and a short note after if there are gaps or caveats. Never rewrite or truncate the code. "
            "Return JSON only with key response."
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
        data = await self._render_chat_json(system, user, max_tokens=2400)
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
        scope = deterministic_ir.get("scope_constraints") if isinstance(deterministic_ir, dict) else {}
        capability_hint = str((scope or {}).get("v9_capability_hint") or "").lower() if isinstance(scope, dict) else ""
        if capability_hint in {"math_science", "coding"} and confidence >= self.t1_skip_confidence:
            return True
        # Always run T1 for ambiguous or complex routes
        if target in {"OP_ESCAPE_TO_SANDBOX", "RUN_CANVAS", "RUN_INVENTION"}:
            return False
        if target in {"CODE_GENERATE", "GENERAL_FACT", "EMOTIONAL_CATCH"}:
            return False
        return confidence >= self.t1_skip_confidence

    def _should_skip_t2(self, obj: VerifiedCognitiveObject) -> bool:
        """Skip T2 Qwen render only for near-perfect verified results.

        We want Qwen3-4B to run in almost all cases — it makes responses
        dramatically more natural. Only skip when the symbolic solver has
        produced a 100%-certain result (e.g. a verified math calculation)
        and there are no gaps to explain.
        """
        if not self.adaptive_thinning:
            return False
        # Never skip when there are knowledge gaps — they need natural explanation
        if obj.knowledge_gaps:
            return False
        # Never skip for non-FACT modes (creative, code, etc need natural language)
        if obj.generation_mode != "FACT":
            return False
        # Never skip when no sources — nothing verified to render tersely
        if not obj.sources:
            return False
        style = obj.style_signature or {}
        # Always run T2 for non-default language or format requests
        if str(style.get("language_hint") or "default") != "default":
            return False
        if str(style.get("format_hint") or "default") != "default":
            return False

        # Preserve T2 for conversational / low-resource / multilingual prompts
        raw_prompt = str(style.get("user_prompt") or "").lower()
        words = set(raw_prompt.split())
        conversational_signals = {
            "hello", "hi", "howdy", "please", "stressed", "help",
            "thanks", "thank you", "nibo", "bawo", "kedu", "sannu", "lafiya", "nagode",
        }
        if words & conversational_signals:
            return False

        # Preserve T2 when mixed digit/letter typos are present
        if any(re.search(r"[A-Za-z]\d|\d[A-Za-z]", word) for word in words):
            return False

        # Only skip T2 at very high confidence threshold (default 0.95, was 0.82)
        # This means T2 renders all but the most certain symbolic solver outputs
        return obj.confidence >= self.t2_skip_confidence


