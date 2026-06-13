"""Adaptive hybrid encoder — Modal-only version.

No local model loading. No sentence-transformers, transformers, or torch imports.
All ML runs on Modal embedding service.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class SymbolicAugmenter:
    """Symbolic processing delegated to T1 (QwenBridge)."""

    async def augment(self, text: str, bridge=None) -> dict[str, Any]:
        return {
            "math_normalized": await self.normalize_math(text, bridge),
            "code_snippets": await self.extract_code(text, bridge),
        }

    async def normalize_math(self, text: str, bridge=None) -> str:
        """Delegate math normalization to T1 bridge.

        Calls bridge.extract_math_expression(text, {}) and returns the
        normalized sympy expression string, or "" if bridge unavailable.
        """
        if bridge is None or not getattr(bridge, "qwen_enabled", False):
            return ""
        try:
            data = await bridge.extract_math_expression(text, {})
            if not data:
                return ""
            expression = str(data.get("expression") or "").strip()
            return expression
        except Exception as exc:
            logger.warning("normalize_math bridge call failed: %s", repr(exc))
            return ""

    async def extract_code(self, text: str, bridge=None) -> list[str]:
        """Delegate code extraction to T1 bridge.

        Calls T1 with a short system prompt to extract code blocks in any
        language. Falls back to [] if bridge unavailable.
        """
        if bridge is None or not getattr(bridge, "qwen_enabled", False):
            return []
        try:
            system_prompt = (
                "Extract all code blocks from the following text. "
                "Return a JSON object with key 'code_blocks' containing a list of strings. "
                "If no code is present, return {\"code_blocks\": []}."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:8000]},
            ]
            result = await bridge._call_t1(messages, max_tokens=400)
            if not result:
                return []
            if isinstance(result, dict):
                blocks = result.get("code_blocks", [])
                if isinstance(blocks, list):
                    return [str(b) for b in blocks if str(b).strip()]
            return []
        except Exception as exc:
            logger.warning("extract_code bridge call failed: %s", repr(exc))
            return []


class AdaptiveHybridEncoder:
    """Modal-only adaptive encoder.

    No local model loading. Calls Modal embedding service for all embeddings.
    """

    def __init__(
        self,
        bridge=None,
        embedding_url: Optional[str] = None,
        embedding_token: Optional[str] = None,
    ) -> None:
        self.bridge = bridge
        self.embedding_url = (
            embedding_url
            or os.environ.get("JIMS_EMBEDDING_SERVICE_URL", "")
        ).rstrip("/")
        self.embedding_token = (
            embedding_token
            or os.environ.get("JIMS_MODAL_API_KEY", "")
            or os.environ.get("JIMS_EMBEDDING_SERVICE_TOKEN", "")
        )
        self.symbolic = SymbolicAugmenter()
        self.current_version = "v2.0-modal"

    async def encode(
        self,
        raw_text: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if metadata is None:
            metadata = {}

        # Symbolic augmentation via T1
        symbolic = await self.symbolic.augment(raw_text, self.bridge)

        # Choose model based on content type
        is_code_heavy = bool(symbolic.get("code_snippets"))
        model = "codebert" if is_code_heavy else "multilingual-e5-small"

        # Embed via Modal
        vector = await self._call_modal_embed(raw_text, model)

        # Structured extraction via T1
        structured = await self._extract_structured(raw_text, metadata, symbolic)

        # ID
        signature_id = hashlib.sha256(
            f"{raw_text}:{str(structured)}".encode()
        ).hexdigest()[:32]

        return {
            "id": signature_id,
            "latent_embedding": vector,
            "structured": structured,
            "abstraction_tags": self._generate_tags(structured, symbolic),
            "encoder_version": self.current_version,
            "source_trust": metadata.get("source_trust", 0.75),
            "provenance": {
                "ingestion_time": (
                    metadata.get("timestamp") or datetime.utcnow().isoformat()
                ),
                "batch_id": metadata.get("batch_id"),
            },
        }

    async def _call_modal_embed(self, text: str, model: str) -> list[float]:
        """POST to {embedding_url}/embed and return vector. Returns [] on failure."""
        if not self.embedding_url:
            return []
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.embedding_token:
            headers["Authorization"] = f"Bearer {self.embedding_token}"
        timeout = float(os.environ.get("JIMS_MULTIMODAL_ENCODER_TIMEOUT", "30"))
        payload = {
            "texts": [text[:16000]],
            "model": model,
            "purpose": "document",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(
                    f"{self.embedding_url}/embed",
                    headers=headers,
                    json=payload,
                )
            r.raise_for_status()
            data = r.json()
            # Modal returns {"vectors": [[...]], ...}
            vec = None
            if isinstance(data.get("vectors"), list) and data["vectors"]:
                first = data["vectors"][0]
                vec = first if isinstance(first, list) else None
            if vec is None and isinstance(data.get("embeddings"), list) and data["embeddings"]:
                first = data["embeddings"][0]
                vec = first if isinstance(first, list) else None
            if vec is None and isinstance(data.get("embedding"), list):
                vec = data["embedding"]
            return vec if isinstance(vec, list) else []
        except Exception as exc:
            logger.warning("AdaptiveHybridEncoder._call_modal_embed failed: %s", repr(exc))
            return []

    async def _extract_structured(
        self,
        text: str,
        metadata: dict[str, Any],
        symbolic: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract structured relations via T1 bridge.

        Returns dict with entities, relations, causal_chain, is_mathematical.
        No regex imports from dual_encoder.
        """
        entities: list[dict] = []
        relations: list[dict] = []
        causal_chain: list[dict] = []
        is_mathematical = bool(symbolic.get("math_normalized"))

        if self.bridge is not None and getattr(self.bridge, "qwen_enabled", False):
            try:
                t1_data = await self.bridge.extract_structured_relations(text, "text")
                if t1_data:
                    for ent in t1_data.get("entities", []):
                        if isinstance(ent, dict) and ent.get("name"):
                            entities.append(
                                {"name": str(ent["name"]), "type": ent.get("type", "concept")}
                            )
                        elif isinstance(ent, str) and ent.strip():
                            entities.append({"name": ent.strip(), "type": "concept"})
                    for rel in t1_data.get("relations", []):
                        if isinstance(rel, dict):
                            relations.append(rel)
                    for link in t1_data.get("causal", []):
                        if isinstance(link, dict) and link.get("cause") and link.get("effect"):
                            causal_chain.append(link)
            except Exception as exc:
                logger.warning(
                    "_extract_structured bridge call failed: %s", repr(exc)
                )

        return {
            "entities": entities,
            "relations": relations,
            "causal_chain": causal_chain,
            "is_mathematical": is_mathematical,
        }

    def _generate_tags(
        self,
        structured: dict[str, Any],
        symbolic: dict[str, Any],
    ) -> list[str]:
        tags = ["general"]
        if symbolic.get("math_normalized"):
            tags.append("mathematical")
        if symbolic.get("code_snippets"):
            tags.append("code")
        if structured.get("causal_chain"):
            tags.append("causal")
        return tags
