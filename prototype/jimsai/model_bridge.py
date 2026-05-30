from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .models import VerifiedCognitiveObject


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqBridge:
    """Bounded Groq adapter for PDF T1/T2/Canvas/Invention interfaces.

    The bridge is deliberately not a reasoning engine. It can interpret messy input
    into candidate JSON or render an already verified cognitive object. The
    deterministic runtime remains authoritative when Groq is unavailable or returns
    invalid structure.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")
        default_small = os.getenv("GROQ_GENERATOR_MODEL", "openai/gpt-oss-20b")
        default_large = os.getenv("GROQ_REASONING_MODEL", "openai/gpt-oss-120b")
        self.intent_model = os.getenv("GROQ_INTENT_MODEL", default_small)
        self.render_model = os.getenv("GROQ_RENDER_MODEL", default_small)
        self.canvas_model = os.getenv("GROQ_CANVAS_MODEL", default_large)
        self.invention_model = os.getenv("GROQ_INVENTION_MODEL", default_large)
        self.ingest_model = os.getenv("GROQ_INGEST_MODEL", default_large)
        self.enabled_t1 = os.getenv("JIMS_ENABLE_GROQ_T1", "false").lower() == "true"
        self.enabled_t2 = os.getenv("JIMS_ENABLE_GROQ_T2", "false").lower() == "true"
        self.enabled_canvas = os.getenv("JIMS_ENABLE_GROQ_CANVAS", "false").lower() == "true"
        self.enabled_invention = os.getenv("JIMS_ENABLE_GROQ_INVENTION", "false").lower() == "true"
        self.enabled_ingest = os.getenv("JIMS_ENABLE_GROQ_INGEST", "true").lower() in {"1", "true", "yes", "on"}
        self.adaptive_thinning = os.getenv("JIMS_ADAPTIVE_TRANSFORMER_THINNING", "true").lower() in {"1", "true", "yes", "on"}
        self.t1_skip_confidence = float(os.getenv("JIMS_T1_SKIP_CONFIDENCE", "0.68") or "0.68")
        self.t2_skip_confidence = float(os.getenv("JIMS_T2_SKIP_CONFIDENCE", "0.82") or "0.82")
        self.last_t1_skip_reason = ""
        self.last_t2_skip_reason = ""

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def _chat_json(self, model: str, system: str, user: str, max_tokens: int = 800) -> dict[str, Any] | None:
        if not self.available:
            return None
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 1e-8,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(GROQ_CHAT_COMPLETIONS_URL, headers=headers, json=payload)
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return None

    async def infer_intent(self, raw_input: str, deterministic_ir: dict[str, Any]) -> dict[str, Any] | None:
        self.last_t1_skip_reason = ""
        if not self.enabled_t1:
            self.last_t1_skip_reason = "disabled"
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
        return await self._chat_json(self.intent_model, system, user, max_tokens=400)

    async def canvas_synthesis(self, content: str) -> dict[str, Any] | None:
        if not self.enabled_canvas:
            return None
        system = (
            "You are the bounded Active Canvas interface for JIMS-AI. "
            "Return JSON with patterns only. Do not answer the user."
        )
        return await self._chat_json(self.canvas_model, system, content[:12000], max_tokens=1000)

    async def invention_candidates(self, goal: str, context: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled_invention:
            return None
        system = (
            "You are a bounded invention candidate generator for JIMS-AI. "
            "Return JSON candidates constrained by provided memory/context. "
            "Do not make factual claims beyond the supplied context."
        )
        return await self._chat_json(self.invention_model, system, json.dumps({"goal": goal, "context": context}), max_tokens=1000)

    async def extract_ingestion_memory(self, content: str, context: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled_ingest:
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
                    "relations": [{"subject": "string", "predicate": "string", "object": "string", "confidence": "number"}],
                    "causal_links": [{"cause": "string", "effect": "string", "confidence": "number"}],
                    "facts": [{"subject": "string", "predicate": "string", "object": "string", "confidence": "number"}],
                    "tags": ["string"],
                    "confidence": "number",
                },
            },
            sort_keys=True,
        )
        return await self._chat_json(self.ingest_model, system, user, max_tokens=1400)

    async def render(self, obj: VerifiedCognitiveObject, deterministic_render: str) -> str | None:
        self.last_t2_skip_reason = ""
        if not self.enabled_t2:
            self.last_t2_skip_reason = "disabled"
            return None
        if self._should_skip_t2(obj):
            self.last_t2_skip_reason = f"verified_confidence_{obj.confidence:.2f}"
            return None
        system = (
            "You are the bounded T2 render interface for JIMS-AI. "
            "Render the verified cognitive object fluently. "
            "Do not add claims, facts, sources, code, or conclusions not present in the object. "
            "If a gap is present, preserve it explicitly."
        )
        user = json.dumps(
            {
                "verified_cognitive_object": obj.model_dump(mode="json"),
                "deterministic_render": deterministic_render,
            },
            sort_keys=True,
        )
        data = await self._chat_json(self.render_model, system, user, max_tokens=1200)
        if not data:
            return None
        rendered = data.get("response")
        return rendered if isinstance(rendered, str) and rendered.strip() else None

    def _should_skip_t1(self, deterministic_ir: dict[str, Any]) -> bool:
        if not self.adaptive_thinning:
            return False
        try:
            confidence = float(deterministic_ir.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        target = str(deterministic_ir.get("target_ir") or "").upper()
        if target in {"OP_ESCAPE_TO_SANDBOX", "RUN_CANVAS", "RUN_INVENTION"}:
            return False
        if target in {"CODE_GENERATE", "GENERAL_FACT", "EMOTIONAL_CATCH"}:
            return False
        return confidence >= self.t1_skip_confidence

    def _should_skip_t2(self, obj: VerifiedCognitiveObject) -> bool:
        if not self.adaptive_thinning:
            return False
        if obj.knowledge_gaps:
            return False
        if obj.generation_mode != "FACT":
            return False
        if not obj.sources:
            return False
        return obj.confidence >= self.t2_skip_confidence
