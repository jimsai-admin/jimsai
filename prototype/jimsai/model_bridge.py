from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from .errors import CriticalServiceUnavailable
from .env_config import get_env
from .models import VerifiedCognitiveObject

import httpx


_INVALID_CAUSAL_TRIGGERS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "being",
    "means",
    "equals",
    "equal",
    "times",
    "multiplied by",
    "depends on",
    "depends_on",
    "works on",
    "work on",
    "building",
    "using",
}

_EXPLICIT_CAUSAL_TRIGGER_PATTERNS = (
    r"\bcauses?\b",
    r"\bcaused\s+by\b",
    r"\bbecause\b",
    r"\bdue\s+to\b",
    r"\bleads?\s+to\b",
    r"\bresults?\s+in\b",
    r"\btriggers?\b",
    r"\bproduces?\b",
    r"\bdrives?\b",
    r"\bgives?\s+rise\s+to\b",
)


class QwenBridge:
    """Bounded Modal AI bridge for T1/T2/Canvas/Invention/Ingest interfaces.

    All LLM calls route to Modal-hosted services exclusively:
      - Intent_Service  (Qwen3-1.7B): T1 intent/routing via JIMS_INTENT_SERVICE_URL
      - Renderer_Service (Qwen3-4B):  T2 render/canvas/invention via JIMS_RENDERER_SERVICE_URL
      - Reasoning_Service (Qwen3-8B): deep reasoning via JIMS_REASONING_SERVICE_URL

    Auth: JIMS_MODAL_API_KEY â€” shared Bearer token for all Modal services.
    """

    def __init__(self) -> None:
        # â”€â”€ Modal service URLs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        self.local_url = get_env("JIMS_INTENT_SERVICE_URL").rstrip("/")
        self.render_url = get_env("JIMS_RENDERER_SERVICE_URL").rstrip("/")
        self.local_api_key = get_env("JIMS_MODAL_API_KEY")

        # Model name tags (used in request payloads)
        self.local_model = get_env("JIMS_LOCAL_INFERENCE_MODEL", "qwen3-1.7b-instruct")
        self.local_render_model = get_env("JIMS_LOCAL_RENDER_MODEL", "qwen3-4b-instruct")

        # Endpoint paths on the Modal services
        self.local_chat_path = get_env("JIMS_LOCAL_INFERENCE_CHAT_PATH", "/generate") or "/generate"
        self.local_render_path = get_env("JIMS_LOCAL_RENDER_CHAT_PATH", "/generate") or "/generate"

        # LLM thinning â€” skip T1/T2 overlay when deterministic confidence is high
        self.adaptive_thinning = get_env("JIMS_ADAPTIVE_TRANSFORMER_THINNING", "true").lower() in {"1", "true", "yes", "on"}
        self.t1_skip_confidence = float(get_env("JIMS_T1_SKIP_CONFIDENCE", "0.60") or "0.60")
        self.last_t1_skip_reason = ""
        self.last_t2_skip_reason = ""

        # â”€â”€ Configurable LLM provider â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # The default backend is the Modal-hosted Qwen services (T1 Intent / T2
        # Renderer). Setting JIMS_LLM_PROVIDER â€” or simply supplying NVIDIA_API_KEY â€”
        # routes the same bounded T1/T2/Canvas/Invention/Ingest calls to an
        # OpenAI-compatible endpoint instead (e.g. NVIDIA NIM serving Llama 3.3 70B).
        # The cognitive flow above this bridge is unchanged; only the HTTP backend
        # and request/response shape differ.
        provider = get_env("JIMS_LLM_PROVIDER", "modal").lower() or "modal"
        self.provider = provider

        self.t1_provider = get_env(
            "JIMS_T1_PROVIDER",
            provider,
        ).lower()
        self.t2_provider = get_env("JIMS_T2_PROVIDER", provider).lower()
        self.t1_openai_compatible = self.t1_provider in {"nvidia", "openai", "openai_compatible"}
        self.t2_openai_compatible = self.t2_provider in {"nvidia", "openai", "openai_compatible"}
        self.openai_compatible = self.t2_openai_compatible
        if self.t1_openai_compatible or self.t2_openai_compatible:
            if provider == "nvidia":
                self.openai_base_url = get_env(
                    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
                ).rstrip("/")
                self.openai_api_key = get_env("NVIDIA_API_KEY")
                self.openai_model = get_env("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
            else:
                self.openai_base_url = get_env(
                    "JIMS_OPENAI_BASE_URL", "https://api.openai.com/v1"
                ).rstrip("/")
                self.openai_api_key = get_env("JIMS_OPENAI_API_KEY")
                self.openai_model = get_env("JIMS_OPENAI_MODEL", "gpt-4o-mini")
            self.openai_t1_model = (
                get_env("JIMS_T1_OPENAI_MODEL", "")
                or get_env("NVIDIA_T1_MODEL", "")
                or self.openai_model
            )
            self.openai_t2_model = (
                get_env("JIMS_T2_OPENAI_MODEL", "")
                or get_env("NVIDIA_T2_MODEL", "")
                or self.openai_model
            )
            self.openai_chat_path = get_env("JIMS_OPENAI_CHAT_PATH", "/chat/completions") or "/chat/completions"
            # Many OpenAI-compatible servers support strict JSON mode, but not all
            # models do. Default off and rely on the prompt plus JSON extraction;
            # opt in with JIMS_OPENAI_JSON_MODE=true.
            self.openai_json_mode = get_env("JIMS_OPENAI_JSON_MODE", "false").lower() in {"1", "true", "yes", "on"}
        else:
            self.openai_base_url = ""
            self.openai_api_key = ""
            self.openai_model = ""
            self.openai_t1_model = ""
            self.openai_t2_model = ""
            self.openai_chat_path = "/chat/completions"
            self.openai_json_mode = False

    # â”€â”€ Availability â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @property
    def t1_enabled(self) -> bool:
        if self.t1_openai_compatible:
            return bool(self.openai_base_url and self.openai_api_key and self.openai_model)
        return bool(self.local_url and self.local_api_key)

    @property
    def t2_enabled(self) -> bool:
        if self.t2_openai_compatible:
            return bool(self.openai_base_url and self.openai_api_key and self.openai_model)
        return bool(self.render_url and self.local_api_key)

    @property
    def qwen_enabled(self) -> bool:
        """True when the active LLM backend is configured.

        Modal backend: requires both Intent and Renderer URLs plus the shared key.
        OpenAI-compatible backend (e.g. NVIDIA NIM): requires base URL, API key,
        and model name. The name is kept for backward compatibility â€” every
        existing call site checks ``qwen_enabled`` to decide whether the bounded
        transformer overlay can run, regardless of which backend serves it.
        """
        return self.t1_enabled or self.t2_enabled

    @property
    def available(self) -> bool:
        """Alias for qwen_enabled â€” kept for backward compatibility."""
        return self.qwen_enabled

    def describe(self) -> dict[str, str]:
        """Return current model configuration for dashboard / observability."""
        if self.t1_openai_compatible or self.t2_openai_compatible:
            endpoint = f"{self.openai_base_url}{self.openai_chat_path}"
            return {
                "backend": self.provider,
                "t1_backend": self.t1_provider,
                "t2_backend": self.t2_provider,
                "t1_model": self.openai_t1_model if self.t1_openai_compatible else self.local_model,
                "t2_model": self.openai_t2_model if self.t2_openai_compatible else self.local_render_model,
                "t1_endpoint": endpoint if self.t1_openai_compatible else f"{self.local_url}{self.local_chat_path}",
                "t2_endpoint": endpoint if self.t2_openai_compatible else f"{self.render_url}{self.local_render_path}",
                "qwen_enabled": str(self.qwen_enabled),
            }
        return {
            "backend": "modal" if self.qwen_enabled else "none",
            "t1_backend": self.t1_provider,
            "t2_backend": self.t2_provider,
            "t1_model": self.local_model,
            "t2_model": self.local_render_model,
            "t1_endpoint": f"{self.local_url}{self.local_chat_path}",
            "t2_endpoint": f"{self.render_url}{self.local_render_path}",
            "qwen_enabled": str(self.qwen_enabled),
        }

    # â”€â”€ Low-level HTTP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _chat_json(
        self, _model_hint: str, system: str, user: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        """Route to T1 Modal Intent_Service."""
        if not self.t1_enabled:
            return None
        return await self._local_chat_json(system, user, max_tokens=max_tokens)

    def _timeout_seconds(self, primary_env: str, default: str) -> float:
        configured = float(os.getenv(primary_env, default) or default)
        cap_raw = os.getenv("JIMS_INTERACTIVE_SERVICE_TIMEOUT_CAP")
        if cap_raw is None:
            return configured
        try:
            cap = float(cap_raw)
        except ValueError:
            return configured
        return min(configured, cap) if cap > 0 else configured

    def _http_timeout(self, total_seconds: float) -> httpx.Timeout:
        total = max(float(total_seconds), 0.25)
        connect = min(total, float(os.getenv("JIMS_CONNECT_TIMEOUT", "4.0") or "4.0"))
        write = min(total, float(os.getenv("JIMS_WRITE_TIMEOUT", "2.0") or "2.0"))
        pool = min(total, float(os.getenv("JIMS_POOL_TIMEOUT", "1.0") or "1.0"))
        return httpx.Timeout(timeout=total, connect=connect, read=total, write=write, pool=pool)

    async def _bounded_post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._http_timeout(timeout_seconds), follow_redirects=True) as client:
            return await asyncio.wait_for(
                client.post(url, headers=headers, json=payload, follow_redirects=True),
                timeout=max(timeout_seconds, 0.25),
            )

    async def _openai_chat(
        self,
        system: str,
        user: str,
        max_tokens: int,
        wrap_text: bool,
        timeout_seconds: float | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        """Call an OpenAI-compatible chat endpoint (e.g. NVIDIA NIM / Llama 3.3 70B).

        Shared by the T1 (structured) and T2 (render) paths when an
        OpenAI-compatible provider is configured. T1 passes wrap_text=False so a
        non-JSON reply falls through to the deterministic path; T2 passes
        wrap_text=True so a plain-text answer is wrapped as {"response": ...},
        matching the Modal renderer's contract.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}",
        }
        payload: dict[str, Any] = {
            "model": model or self.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if self.openai_json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            timeout = timeout_seconds if timeout_seconds is not None else self._timeout_seconds("JIMS_T1_TIMEOUT", "5")
            response = await self._bounded_post_json(
                url=f"{self.openai_base_url}{self.openai_chat_path}",
                headers=headers,
                payload=payload,
                timeout_seconds=timeout,
            )
            response.raise_for_status()
            data = response.json()
            raw_content = ""
            choices = data.get("choices")
            if choices:
                raw_content = (choices[0].get("message") or {}).get("content") or ""
            if not raw_content:
                raw_content = data.get("response") or data.get("content") or ""
            if not raw_content:
                return None
            # Strip any reasoning/think blocks reasoning models may emit
            raw_content = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
            raw_content = re.sub(r"(?i)think.*?done", "", raw_content, flags=re.DOTALL).strip()
            if not raw_content:
                return None
            start, end = raw_content.find("{"), raw_content.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(raw_content[start:end + 1])
                except json.JSONDecodeError:
                    pass
            # Plain text is valid only for T2. T1 must remain strict JSON.
            if wrap_text:
                return {"response": raw_content}
            return None
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("_openai_chat failed: %s", repr(exc))
            return None

    async def _render_chat_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        """Route to T2 Renderer.

        For the Modal backend the renderer returns:
        {"response": "<model output>", "model": ..., "usage": ..., "finish_reason": ...}
        The model output may be:
          - A JSON string:  '{"response": "markdown text"}'  â†’ parse â†’ {"response": "markdown text"}
          - A JSON string:  '{"candidate_steps": [...]}'     â†’ parse â†’ {"candidate_steps": [...]}
          - Plain markdown: 'Here is your answer...'         â†’ wrap  â†’ {"response": "Here is your answer..."}
        When an OpenAI-compatible provider is configured, the call is delegated to
        _openai_chat with the same wrap-as-{"response": ...} contract.
        """
        if not self.t2_enabled:
            return None
        if self.t2_openai_compatible:
            return await self._openai_chat(
                system,
                user,
                max_tokens,
                wrap_text=True,
                timeout_seconds=timeout_seconds or self._timeout_seconds("JIMS_T2_TIMEOUT", "10"),
                model=self.openai_t2_model,
            )
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.local_api_key}"}
        payload = {
            "model": self.local_render_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            timeout = timeout_seconds if timeout_seconds is not None else self._timeout_seconds("JIMS_T2_TIMEOUT", "10")
            response = await self._bounded_post_json(
                url=f"{self.render_url}{self.local_render_path}",
                headers=headers,
                payload=payload,
                timeout_seconds=timeout,
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
            # Model returned plain text instead of JSON â€” wrap it as {"response": ...}
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
        """Route to T1 Intent service.

        Modal returns: {"response": "<model output>", "model": ..., "usage": ..., "finish_reason": ...}
        The model output must be a JSON object (T1 is always structured). If parsing
        fails, return None so the deterministic path takes over gracefully.
        When an OpenAI-compatible provider is configured, the call is delegated to
        _openai_chat (strict: a non-JSON reply yields None, not wrapped text).
        """
        if self.t1_openai_compatible:
            return await self._openai_chat(
                system,
                user,
                max_tokens,
                wrap_text=False,
                timeout_seconds=timeout if timeout is not None else self._timeout_seconds("JIMS_T1_TIMEOUT", "5"),
                model=self.openai_t1_model,
            )
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
                os.getenv(
                    "JIMS_T1_TIMEOUT",
                    os.getenv("JIMS_LOCAL_INFERENCE_TIMEOUT", "5"),
                )
                or "5"
            )
            response = await self._bounded_post_json(
                url=f"{self.local_url}{path or self.local_chat_path}",
                headers=headers,
                payload=payload,
                timeout_seconds=request_timeout,
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
            # T1 must be JSON â€” if we can't parse it, fall back to deterministic path
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

    # â”€â”€ T1: Intent / routing / math â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def infer_intent(
        self, raw_input: str, deterministic_ir: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Bounded T1 intent overlay â€” only refines, never overrides a high-confidence IR."""
        self.last_t1_skip_reason = ""
        if not self.qwen_enabled:
            self.last_t1_skip_reason = "qwen_unavailable"
            return None
        if self._should_skip_t1(deterministic_ir, raw_input):
            confidence = float(deterministic_ir.get("confidence") or 0.0)
            self.last_t1_skip_reason = f"deterministic_confidence_{confidence:.2f}"
            return None
        system = (
            "You are an intent classifier. Return only JSON with target_ir, confidence, and optional scope_constraints. "
            "Allowed targets: WORKSPACE_QUERY, FETCH_DOCUMENT, SYSTEM_DIAGNOSTIC, CODE_GENERATE, "
            "RUN_CANVAS, RUN_INVENTION, GENERAL_FACT, EMOTIONAL_CATCH, META_INQUIRY. "
            "For causal questions in any language, set scope_constraints.question_intent to "
            "{\"relation\":\"causes\",\"direction\":\"incoming\"} when the user asks what causes X, "
            "or {\"relation\":\"causes\",\"direction\":\"outgoing\"} when the user asks what X causes; "
            "set scope_constraints.entities to the queried concept phrase(s). "
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
                "scope_constraints_schema": {
                    "question_intent": {"relation": "causes", "direction": "incoming|outgoing"},
                    "entities": ["canonical queried concept phrases"],
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=220)

    async def classify_capability(
        self, raw_input: str, deterministic_context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Bounded capability router â€” supplements the zero-shot classifier."""
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
        return await self._chat_json(self.local_model, system, user, max_tokens=140)

    async def extract_math_expression(
        self, raw_input: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Extract executable mathematical expressions from freeform text."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are a mathematical expression extractor for JimsAI. Return only JSON. "
            "Extract a mathematical expression only when the user asks for an executable calculation, "
            "equation solution, symbolic transformation, derivation, or quantitative result. "
            "Support arithmetic, algebra, calculus, linear algebra, differential equations, "
            "statistics, geometry, number theory, and physics calculations. "
            "Return the expression in Python/sympy syntax so it can be evaluated directly. "
            "For conceptual science, causal explanation, definition, or qualitative reasoning questions, "
            "return expression as empty. "
            "Examples:\n"
            "  'derivative of x^3' -> expression: 'diff(x**3, x)', solve_for: null\n"
            "  'integral of sin(x)' -> expression: 'integrate(sin(x), x)', solve_for: null\n"
            "  'solve 2x + 6 = 20' -> expression: '2*x + 6 = 20', solve_for: 'x'\n"
            "  '27 * 19' -> expression: '27*19', solve_for: null\n"
            "If no executable mathematical content exists, return expression as empty string."
        )
        user = json.dumps(
            {
                "raw_input": raw_input,
                "context": context or {},
                "schema": {
                    "expression": "sympy-compatible string (use diff(), integrate(), Eq() as needed)",
                    "solve_for": "single variable string or null",
                    "math_domain": "one of: arithmetic, algebra, calculus, linear_algebra, statistics, other",
                    "confidence": "number between 0 and 1",
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=160)

    async def extract_structured_relations(
        self, text: str, modality: str = "text"
    ) -> dict[str, Any] | None:
        """Extract entities, relations, and causal links from text in any language."""
        if not self.qwen_enabled:
            return None
        system = (
            "You are a structured-extraction engine for JimsAI. Return only JSON. "
            "Read text in any language, including misspelled or grammatically incorrect text, "
            "and normalize intent rather than surface form. Extract: "
            "(1) entities: named things such as services, people, chemicals, concepts, code symbols, "
            "organisms, locations, or physical quantities. Use canonical names as they appear in text. "
            "(2) relations: subject-predicate-object triples. Use snake_case predicates such as "
            "depends_on, is_a, has_field, means, or uses. "
            "(3) causal: only explicit cause-effect pairs where one stated thing directly causes "
            "another stated thing. Cause and effect must be complete, meaningful phrases from the text. "
            "Do not extract causal pairs from fragments, partial matches, or single tokens. If a "
            "sentence has no clear causal claim, emit no causal item for it. "
            "confidence: 0.0-1.0 per item.\n\n"
            "Output schema is strict: "
            "{\"entities\":[{\"name\":\"...\",\"type\":\"...\",\"evidence\":\"exact source span\"}],"
            "\"relations\":[{\"subject\":\"...\",\"predicate\":\"...\",\"object\":\"...\",\"confidence\":0.0,\"evidence\":\"exact source span\"}],"
            "\"causal\":[{\"cause\":\"...\",\"effect\":\"...\",\"causal_trigger\":\"exact source phrase that states causation\",\"confidence\":0.0,\"evidence\":\"exact source span\"}]}. "
            "Never echo input keys such as text or modality. "
            "For identity/name facts, object must be the normalized value only, not the full sentence. "
            "For causal items, causal_trigger must be present in evidence and must explicitly state causation; working on, building, using, depending on, equaling, or describing a thing is not causation. "
            "Examples:\n"
            "  'Loose wiring causes intermittent power loss.' -> "
            "causal: [{cause: 'loose wiring', effect: 'intermittent power loss', confidence: 0.92}]\n"
            "  'Expired credentials cause authentication failures.' -> "
            "causal: [{cause: 'expired credentials', effect: 'authentication failures', confidence: 0.94}]\n"
            "  'High latency causes request timeouts.' -> "
            "causal: [{cause: 'high latency', effect: 'request timeouts', confidence: 0.91}]\n"
            "  'The output voltage is current times resistance.' -> causal: [] "
            "(no causal claim; this is a definition, not a cause-effect statement)\n"
            "Return JSON with keys: entities, relations, causal."
        )
        user = (
            f"Modality: {modality}\n"
            "Source text between delimiters:\n"
            "<<<SOURCE_TEXT\n"
            f"{text[:2000]}\n"
            "SOURCE_TEXT>>>\n"
            "Extract only facts grounded in the source text into the required JSON schema."
        )
        source_text = text[:2000]
        data = await self._chat_json(self.local_model, system, user, max_tokens=260)
        normalized = self._normalize_structured_extraction(data, source_text=source_text)
        if normalized is None:
            normalized = {"entities": [], "relations": [], "causal": []}
        if self._needs_focused_causal_pass(source_text, normalized.get("causal", [])):
            causal_data = await self._extract_causal_links(source_text)
            causal_normalized = self._normalize_structured_extraction(causal_data, source_text=source_text)
            if causal_normalized is not None:
                normalized["causal"] = self._merge_causal_links(
                    normalized.get("causal", []),
                    causal_normalized.get("causal", []),
                )
        return normalized

    async def _extract_causal_links(self, text: str) -> dict[str, Any] | None:
        system = (
            "Return one compact JSON object with key causal. "
            "Each causal item has keys cause, effect, causal_trigger, evidence, confidence. "
            "Copy actual source spans only; never copy schema descriptions or placeholder text. "
            "Extract causal only when the source explicitly states that one thing causes another. "
            "causal_trigger must be copied from the source sentence and must mean causes, caused by, leads to, results in, because, due to, or triggers. "
            "Working on, building, using, depending on, equaling, describing, or naming a thing is not causation. "
            "If no explicit causal statement exists, return {\"causal\":[]}. "
            "Example: source 'Expired credentials cause authentication failures.' returns "
            "{\"causal\":[{\"cause\":\"Expired credentials\",\"effect\":\"authentication failures\","
            "\"causal_trigger\":\"cause\",\"evidence\":\"Expired credentials cause authentication failures.\",\"confidence\":0.94}]}."
        )
        user = f"Source: {text}"
        return await self._chat_json(self.local_model, system, user, max_tokens=220)

    def _normalize_structured_extraction(self, data: dict[str, Any] | None, source_text: str = "") -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        if not any(key in data for key in ("entities", "relations", "causal")):
            return None
        source_lower = source_text.lower()

        entities_raw = data.get("entities") or []
        entities: list[Any] = []
        if isinstance(entities_raw, list):
            for item in entities_raw:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("entity") or item.get("value") or "").strip()
                    evidence = str(item.get("evidence") or item.get("source_span") or item.get("span") or item.get("quote") or "").strip()
                    if name and self._entity_grounded(name, evidence, source_lower):
                        entities.append({"name": name, "type": str(item.get("type") or "concept")})
                elif isinstance(item, str) and item.strip() and self._entity_grounded(item.strip(), "", source_lower):
                    entities.append({"name": item.strip(), "type": "concept"})
        elif isinstance(entities_raw, dict):
            entities = [
                {"name": str(value), "type": str(key)}
                for key, value in entities_raw.items()
                if str(value).strip() and self._entity_grounded(str(value), "", source_lower)
            ]
        elif isinstance(entities_raw, str) and entities_raw.strip() and self._entity_grounded(entities_raw.strip(), "", source_lower):
            entities = [{"name": entities_raw.strip(), "type": "concept"}]

        relations_raw = data.get("relations") or []
        relations: list[Any] = []
        if isinstance(relations_raw, list):
            for item in relations_raw:
                normalized = self._normalize_relation_item(item, source_lower)
                if normalized:
                    relations.append(normalized)
        elif isinstance(relations_raw, dict):
            source = self._primary_entity_name(entities)
            for key, value in relations_raw.items():
                normalized = self._normalize_relation_item(
                    {"subject": source, "predicate": str(key), "object": str(value), "confidence": 0.72},
                    source_lower,
                )
                if normalized:
                    relations.append(normalized)

        causal_raw = data.get("causal") or []
        causal: list[Any] = []
        if isinstance(causal_raw, list):
            for item in causal_raw:
                normalized = self._normalize_causal_item(item, source_lower)
                if normalized:
                    causal.append(normalized)
        elif isinstance(causal_raw, dict):
            normalized = self._normalize_causal_item(causal_raw, source_lower)
            if normalized:
                causal.append(normalized)

        return {"entities": entities, "relations": relations, "causal": causal}

    def _normalize_relation_item(self, item: Any, source_lower: str) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        subject = str(item.get("subject") or item.get("source") or item.get("head") or "").strip()
        predicate = str(item.get("predicate") or item.get("type") or item.get("relation") or "").strip().lower().replace(" ", "_")
        obj = str(item.get("object") or item.get("target") or item.get("value") or "").strip()
        if not subject or not predicate or not obj:
            return None
        evidence = str(item.get("evidence") or item.get("source_span") or item.get("span") or item.get("quote") or "").strip()
        if evidence and evidence.lower() not in source_lower:
            return None
        if self._malformed_identity_relation(subject, predicate, obj, source_lower):
            return None
        try:
            confidence = float(item.get("confidence", 0.72))
        except (TypeError, ValueError):
            confidence = 0.72
        if confidence <= 0.0 and evidence:
            confidence = 0.72
        return {
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _normalize_causal_item(self, item: Any, source_lower: str) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        cause = str(item.get("cause") or "").strip()
        effect = str(item.get("effect") or "").strip()
        trigger = str(item.get("causal_trigger") or item.get("trigger") or item.get("connector") or "").strip()
        evidence = str(item.get("evidence") or item.get("source_span") or item.get("span") or item.get("quote") or "").strip()
        if not cause or not effect or not evidence:
            return None
        evidence_lower = evidence.lower()
        if evidence_lower not in source_lower:
            return None
        if cause.lower() not in evidence_lower or effect.lower() not in evidence_lower:
            return None
        if not self._causal_trigger_grounded(trigger, evidence_lower):
            return None
        try:
            confidence = float(item.get("confidence", 0.72))
        except (TypeError, ValueError):
            confidence = 0.72
        if confidence <= 0.0 and evidence:
            confidence = 0.72
        return {
            "cause": cause,
            "effect": effect,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _entity_grounded(self, name: str, evidence: str, source_lower: str) -> bool:
        name_lower = name.lower().strip()
        if not name_lower:
            return False
        if evidence and evidence.lower() not in source_lower:
            return False
        return name_lower in source_lower

    def _causal_trigger_grounded(self, trigger: str, evidence_lower: str) -> bool:
        trigger_lower = trigger.lower().strip()
        if trigger_lower:
            if trigger_lower not in evidence_lower:
                return False
            return trigger_lower not in _INVALID_CAUSAL_TRIGGERS
        return self._explicit_causal_statement_count(evidence_lower) > 0

    def _needs_focused_causal_pass(self, source_text: str, normalized_causal: list[Any]) -> bool:
        expected_statements = self._explicit_causal_statement_count(source_text.lower())
        return expected_statements > len(normalized_causal)

    def _merge_causal_links(self, existing: list[Any], focused: list[Any]) -> list[Any]:
        merged: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for item in [*existing, *focused]:
            if not isinstance(item, dict):
                continue
            cause = str(item.get("cause") or "").strip()
            effect = str(item.get("effect") or "").strip()
            if not cause or not effect:
                continue
            key = (cause.lower(), effect.lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def _explicit_causal_statement_count(self, source_lower: str) -> int:
        if not source_lower.strip():
            return 0
        return sum(len(re.findall(pattern, source_lower)) for pattern in _EXPLICIT_CAUSAL_TRIGGER_PATTERNS)

    def _malformed_identity_relation(self, subject: str, predicate: str, obj: str, source_lower: str) -> bool:
        if predicate not in {"is", "is_a", "equals", "has_name"}:
            return False
        object_lower = obj.lower()
        subject_lower = subject.lower()
        if object_lower == source_lower.strip():
            return True
        return subject_lower in object_lower and len(object_lower) > len(subject_lower) + 8

    def _primary_entity_name(self, entities: list[Any]) -> str:
        for item in entities:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                return str(item["name"]).strip()
            if isinstance(item, str) and item.strip():
                return item.strip()
        return "source"

    async def extract_user_facts(
        self, raw_input: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Extract subject-predicate-object facts the user stated about themselves.

        Works for any language and phrasing â€” e.g. "My name is Celestine",
        "Je m'appelle Kofi", "Ø§Ø³Ù…ÙŠ Ø¹Ù…Ø±", "I'm a backend developer", "I'm building
        a podcast app". Returns relations in the same shape the deterministic
        regex extractor produces (subject="user", predicate snake_case, object,
        confidence), so callers can merge results from either source uniformly.

        Returns None if Qwen is unavailable or no JSON could be parsed; returns
        {"relations": []} if the LLM ran but found no self-referential facts.
        """
        if not self.qwen_enabled:
            return None
        system = (
            "You are a user-fact extractor for JimsAI. Return only JSON. "
            "Read the user's message in ANY language and extract facts the user "
            "stated ABOUT THEMSELVES â€” name, role/occupation, preferences, projects "
            "they are building, locations, or similar personal facts. "
            "Do NOT extract facts about other people, the world, or general knowledge. "
            "Always set subject to the literal string 'user'. "
            "predicate must be snake_case and start with 'has_' or 'is_' "
            "(e.g. has_name, has_role, has_preference, is_building, has_location). "
            "object is the fact value, written in its original language/script â€” "
            "do not translate names. "
            "confidence is 0.0-1.0 reflecting how explicitly the user stated this. "
            "If the message contains no self-referential facts, return an empty "
            "relations list. "
            "Examples:\n"
            "  'My name is Celestine.' â†’ relations: [{subject: 'user', predicate: "
            "'has_name', object: 'Celestine', confidence: 0.96}]\n"
            "  \"Je m'appelle Kofi.\" â†’ relations: [{subject: 'user', predicate: "
            "'has_name', object: 'Kofi', confidence: 0.96}]\n"
            "  'Ø§Ø³Ù…ÙŠ Ø¹Ù…Ø±.' â†’ relations: [{subject: 'user', predicate: 'has_name', "
            "object: 'Ø¹Ù…Ø±', confidence: 0.96}]\n"
            "  'I am a backend developer.' â†’ relations: [{subject: 'user', "
            "predicate: 'has_role', object: 'backend developer', confidence: 0.9}]\n"
            "  'What is my name?' â†’ relations: []"
        )
        user = json.dumps(
            {
                "raw_input": raw_input,
                "context": context or {},
                "schema": {
                    "relations": [
                        {
                            "subject": "always 'user'",
                            "predicate": "snake_case, has_* or is_*",
                            "object": "fact value, original language/script",
                            "confidence": "number between 0 and 1",
                        }
                    ],
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.local_model, system, user, max_tokens=180)

    async def canvas_synthesis(self, content: str) -> dict[str, Any] | None:
        """Bounded Active Canvas synthesis â€” returns JSON patterns only."""
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

        The system prompt deliberately avoids hardcoding any language name â€” the
        model infers language from the goal/context and produces actual implementation
        code.  This covers all programming languages, query languages, markup, config
        formats, and system-design tasks without any per-language special-casing.
        """
        if not self.qwen_enabled:
            return None

        # Determine what kind of generation is needed from the context.
        # 'failed_code' in context means a sandbox error occurred â€” we need a fix.
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
            # The language and framework are inferred entirely from the goal â€”
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
            "document metadata, uncertainty, and correction-ready structure. Use only the supplied input. "
            "When the source explicitly defines a relation as single-valued, unique, canonical, or otherwise "
            "function-like for a subject, set relation_cardinality[predicate] to 'one'. For relations that can "
            "validly have many objects, set 'many' or omit the predicate. Do not infer uniqueness without source support."
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
                    "relation_cardinality": {"predicate_name": "one|many|unknown"},
                    "tags": ["string"],
                    "confidence": "number",
                },
            },
            sort_keys=True,
        )
        return await self._render_chat_json(
            system,
            user,
            max_tokens=1400,
            timeout_seconds=self._timeout_seconds("JIMS_INGESTION_OVERLAY_TIMEOUT", "5"),
        )

    async def render(
        self, obj: VerifiedCognitiveObject, deterministic_render: str
    ) -> str:
        """Bounded T2 render â€” rephrase the CSSE output into natural Markdown."""
        self.last_t2_skip_reason = ""
        if not self.t2_enabled:
            self.last_t2_skip_reason = "qwen_unavailable"
            raise CriticalServiceUnavailable("T2 renderer service unavailable")
        system = (
            "You are the bounded T2 render interface for JIMS-AI. "
            "Render the verified cognitive object as a natural, helpful, Markdown-friendly answer for the user. "
            "Use concise paragraphs, short lists only when useful, and a warm professional tone. "
            "Do not expose internal layer names, raw trace IDs, or robotic phrases like "
            "'Here's what I can verify from memory' unless the user asks for internals. "
            "Do not add claims, facts, sources, code, or conclusions not present in the object. "
            "If a gap is present, preserve it explicitly. "
            "IMPORTANT â€” Failed or unexecuted capability results: "
            "If any reasoning_chain step or capability result has status='failed', "
            "executed=false, or solver_status!='solved', you MUST NOT invent, complete, "
            "approximate, or partially render a numeric, symbolic, or code result for it. "
            "State plainly that the calculation/operation could not be completed, and if "
            "an error message is present in the data, summarise it briefly in plain language. "
            "Never output bare formula fragments (e.g. '{d}{dx}', partial LaTeX, dangling "
            "expressions) as if they were an answer. "
            "IMPORTANT â€” Code generation rules: "
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
            raise CriticalServiceUnavailable("T2 renderer returned no usable response")
        rendered = data.get("response")
        if not isinstance(rendered, str) or not rendered.strip():
            raise CriticalServiceUnavailable("T2 renderer response missing text")
        return rendered

    async def stream_render(
        self, obj: VerifiedCognitiveObject, deterministic_render: str
    ):
        """Stream the bounded T2 render token-by-token for low first-token latency.

        Yields plain-text Markdown deltas as the model generates them. The render
        contract is identical to ``render`` â€” never add claims, preserve gaps,
        never fabricate a failed/unexecuted result â€” but the model is asked for
        Markdown directly (no JSON wrapper) so each delta is immediately
        displayable. If true streaming is unavailable for a configured backend,
        this yields one bounded single-shot T2 render. Missing or failed renderer
        services raise CriticalServiceUnavailable instead of falling back.
        """
        if not self.t2_enabled:
            self.last_t2_skip_reason = "qwen_unavailable"
            raise CriticalServiceUnavailable("T2 renderer service unavailable")
        if not self.t2_openai_compatible:
            rendered = await self.render(obj, deterministic_render)
            yield rendered
            return

        self.last_t2_skip_reason = ""
        system = (
            "You are the bounded T2 render interface for JIMS-AI. "
            "Render the verified cognitive object as a natural, helpful answer for the user. "
            "Return the answer as Markdown text ONLY â€” do not wrap it in JSON or quotes. "
            "Use concise paragraphs, short lists only when useful, and a warm professional tone. "
            "Do not expose internal layer names, raw trace IDs, or robotic phrases. "
            "Do not add claims, facts, sources, code, or conclusions not present in the object. "
            "If a gap is present, preserve it explicitly. "
            "If any reasoning_chain step or capability result has status='failed', executed=false, "
            "or solver_status!='solved', you MUST NOT invent, complete, or approximate a numeric, "
            "symbolic, or code result for it â€” state plainly it could not be completed. "
            "If any reasoning_chain step has relation='CODE_GENERATION', present its claim verbatim in a "
            "fenced code block with the correct language tag; never rewrite or truncate the code."
        )
        user = json.dumps(
            {
                "verified_cognitive_object": obj.model_dump(mode="json"),
                "deterministic_render": deterministic_render,
                "style_signature": obj.style_signature,
                "response_requirements": [
                    "Markdown text only (no JSON wrapper)",
                    "natural fluent language",
                    "follow explicit language and format requests from style_signature.user_prompt",
                    "no unsupported facts",
                    "include the verified result directly when present",
                ],
            },
            sort_keys=True,
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}",
        }
        payload = {
            "model": self.openai_t2_model or self.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 2400,
            "stream": True,
        }
        emitted_any = False
        try:
            timeout = self._timeout_seconds(
                "JIMS_STREAM_RENDER_TIMEOUT",
                os.getenv("JIMS_T2_TIMEOUT", "10") or "10",
            )
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream(
                    "POST",
                    f"{self.openai_base_url}{self.openai_chat_path}",
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            emitted_any = True
                            yield delta
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning("stream_render failed: %s", repr(exc))
            raise CriticalServiceUnavailable("T2 streaming renderer failed") from exc
        if not emitted_any:
            raise CriticalServiceUnavailable("T2 streaming renderer emitted no text")

    # â”€â”€ MCTS node evaluation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def evaluate_candidate_node(
        self, goal: str, parent_context: str, candidate_node: str
    ) -> float:
        """Score a candidate invention step for logical consistency (0.0â€“1.0)."""
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

    # â”€â”€ Thinning helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _should_skip_t1(self, deterministic_ir: dict[str, Any], raw_input: str = "") -> bool:
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
        if (
            isinstance(scope, dict)
            and target in {"WORKSPACE_QUERY", "GENERAL_FACT"}
            and "?" in raw_input
            and not scope.get("question_intent")
            and not scope.get("entities")
        ):
            return False
        if capability_hint in {"math_science", "coding"} and confidence >= self.t1_skip_confidence:
            return True
        # Always run T1 for ambiguous or complex routes
        if target in {"OP_ESCAPE_TO_SANDBOX", "RUN_CANVAS", "RUN_INVENTION"}:
            return False
        if target in {"CODE_GENERATE", "GENERAL_FACT", "EMOTIONAL_CATCH"}:
            return False
        return confidence >= self.t1_skip_confidence

