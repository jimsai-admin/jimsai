"""Dual-representation encoder â€” T1-backed structured extraction.

Every regex-based "understanding" path has been removed:
  - No CAUSAL_VERBS / DEPENDENCY_VERBS / QUESTION_SUBJECTS / STOP_TAGS lists
  - No extract_sentence_relations / extract_entity_names / infer_entity_type / infer_code_language
  - No synthetic token-projection embeddings; real vectors only

Structured extraction (entities, relations, causal links) routes through T1
(Qwen3-1.7B via QwenBridge.extract_structured_relations), which:
  - Works in any language
  - Handles misspellings and grammatical errors (LLM normalises intent, not surface form)
  - Produces complete cause/effect phrase pairs, not single-token regex captures
  - Never guesses â€” returns None when unavailable; caller surfaces as explicit gap

Code structure extraction (tree-sitter / regex on formal grammar tokens) is kept
because those are parsers of formal grammars, not English heuristics.
JSON/CSV schema extraction is kept for the same reason.

Embeddings are real-vector-only. If the embedding service is unavailable or times out,
the active pipeline raises CriticalServiceUnavailable instead of storing degraded memory.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any

from ..errors import CriticalServiceUnavailable
from ..models import CausalLink, Confidence, Entity, MemorySignature, Modality, Relation, SignatureIntent, StructuredSignature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure utilities â€” no heuristic lists
# ---------------------------------------------------------------------------

def bounded_excerpt(text: str, max_chars: int = 1200) -> str:
    """Keep a retrievable excerpt without cutting mid-word or mid-sentence."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    candidate = cleaned[:max_chars].rstrip()
    sentence_end = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"))
    if sentence_end >= max_chars * 0.55:
        return candidate[: sentence_end + 1].strip()
    word_end = candidate.rfind(" ")
    if word_end >= max_chars * 0.55:
        return candidate[:word_end].rstrip(" ,;:")
    return candidate.rstrip(" ,;:")


def clean_ref(value: str) -> str:
    return value.strip().strip(".,:;!?)]}\"'")


def stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Extraction result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EncoderExtraction:
    entities: list[Entity]
    relations: list[Relation]
    causal: list[CausalLink]
    tags: list[str]
    metadata: dict[str, Any]
    confidence: float


# ---------------------------------------------------------------------------
# Formal-grammar parsers (kept â€” these parse structure, not natural language)
# ---------------------------------------------------------------------------

def extract_code_structure(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, float]], set[str], dict[str, Any]]:
    """Extract entities and relations from source code using structural tokens.

    These are formal-grammar patterns (def/class/import/function keywords),
    not English-language heuristics. Safe to keep.
    """
    entities: list[tuple[str, str]] = []
    relations: list[tuple[str, str, str, float]] = []
    tags = {"code", "call_graph"}
    metadata: dict[str, Any] = {"tree_sitter_available": tree_sitter_available()}

    # Detect language from structural markers only
    if re.search(r"^\s*(?:async\s+)?def\s+", text, flags=re.MULTILINE):
        metadata["language"] = "python"
    elif re.search(r"^\s*(?:export\s+)?(?:async\s+)?function\s+", text, flags=re.MULTILINE):
        metadata["language"] = "javascript"
    elif re.search(r"\b(public|private|protected)\s+class\s+\w+", text):
        metadata["language"] = "java_or_csharp"
    elif re.search(r"#include\s+<", text):
        metadata["language"] = "cpp"
    else:
        metadata["language"] = "unknown"

    for match in re.finditer(r"^\s*class\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "class"))
    for match in re.finditer(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "function"))
    for match in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "function"))
    for match in re.finditer(r"^\s*(?:import|from)\s+(?P<name>[A-Za-z_][\w\.]*)", text, flags=re.MULTILINE):
        module = match.group("name")
        entities.append((module, "module"))
        for fn_name, _ in entities:
            relations.append((fn_name, "imports", module, 0.68))

    metadata["code_entity_count"] = len(entities)
    return dedupe_pairs(entities), dedupe_relation_tuples(relations), tags, metadata


def extract_data_structure(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, float]], set[str], dict[str, Any]]:
    """Extract schema from JSON or CSV. These are formal parsers, not heuristics."""
    entities: list[tuple[str, str]] = []
    relations: list[tuple[str, str, str, float]] = []
    tags = {"data", "schema"}
    metadata: dict[str, Any] = {"data_schema_detected": False}
    stripped = text.strip()
    dataset_name = "dataset"
    try:
        parsed = json.loads(stripped)
        metadata["data_schema_detected"] = True
        metadata["data_format"] = "json"
        keys = sorted(json_keys(parsed))[:32]
        entities.append((dataset_name, "dataset"))
        for key in keys:
            entities.append((key, "field"))
            relations.append((dataset_name, "has_field", key, 0.76))
        return dedupe_pairs(entities), dedupe_relation_tuples(relations), tags, metadata
    except Exception:
        pass
    try:
        sample = StringIO(stripped)
        reader = csv.reader(sample)
        headers = next(reader)
        if len(headers) > 1:
            metadata["data_schema_detected"] = True
            metadata["data_format"] = "csv"
            entities.append((dataset_name, "dataset"))
            for header in headers[:32]:
                cleaned = clean_ref(header)
                if cleaned:
                    entities.append((cleaned, "field"))
                    relations.append((dataset_name, "has_column", cleaned, 0.74))
    except Exception:
        pass
    return dedupe_pairs(entities), dedupe_relation_tuples(relations), tags, metadata


def json_keys(value: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.add(path)
            keys.update(json_keys(item, path))
    elif isinstance(value, list):
        for item in value[:10]:
            keys.update(json_keys(item, prefix))
    return keys


def tree_sitter_available() -> bool:
    try:
        import tree_sitter  # noqa: F401
        return True
    except Exception:
        return False


def dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[tuple[str, str]] = []
    for name, kind in values:
        key = (clean_ref(name), kind)
        if key[0] and key not in seen:
            seen.add(key)
            output.append(key)
    return output


def dedupe_relation_tuples(values: list[tuple[str, str, str, float]]) -> list[tuple[str, str, str, float]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[tuple[str, str, str, float]] = []
    for subject, predicate, obj, confidence in values:
        key = (clean_ref(subject), predicate, clean_ref(obj))
        if key[0] and key[2] and key not in seen:
            seen.add(key)
            output.append((key[0], key[1], key[2], confidence))
    return output


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

class DualRepresentationEncoder:
    """Dual-representation encoder.

    Structured extraction (entities, relations, causal links) is T1-only via
    QwenBridge.extract_structured_relations. No regex-based NLP extraction.

    Embedding is real-vector-only; unavailable vectors are queued for re-embedding.

    Both encode() and encode_text() are async because T1 extraction and
    embedding are async network calls.
    """

    def __init__(
        self,
        multimodal_adapter: object | None = None,
        bridge: object | None = None,
    ) -> None:
        self.multimodal_adapter = multimodal_adapter
        self.bridge = bridge  # QwenBridge â€” required for T1 extraction

    async def encode(
        self,
        content: str,
        modality: Modality = Modality.TEXT,
        intent_type: str = "workspace_query",
        provenance: str = "local_extraction",
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> MemorySignature:
        text = (
            content
            if modality in {Modality.TEXT, Modality.CODE, Modality.DATA}
            else self._surrogate_text(content, modality)
        )
        signature_task = asyncio.create_task(
            self.encode_text(
                text,
                intent_type=intent_type,
                provenance=provenance,
                modality=modality,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        )
        vector_task = asyncio.create_task(self._external_embedding(content, modality))
        signature: MemorySignature | None = None
        vector: list[float] | None = None
        pending: set[asyncio.Task] = {signature_task, vector_task}
        try:
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if task is signature_task:
                        signature = task.result()
                    elif task is vector_task:
                        vector = task.result()
                        if not vector:
                            raise CriticalServiceUnavailable("embedding service unavailable for L1 encoder")
            if signature is None:
                raise CriticalServiceUnavailable("T1 structured extraction unavailable for L1 encoder")
            if not vector:
                raise CriticalServiceUnavailable("embedding service unavailable for L1 encoder")
        except Exception:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            raise
        if modality not in {Modality.TEXT, Modality.CODE, Modality.DATA}:
            signature.raw_excerpt = content[:500]

        signature.latent_embedding = vector
        signature.confidence.source = "dual_encoder_external_latent"
        signature.metadata["latent_encoder"] = self._latent_model_name(modality)
        signature.metadata["latent_embedding_source"] = "external_service"
        signature.metadata["reembedding_required"] = False

        return signature

    async def encode_text(
        self,
        text: str,
        intent_type: str = "workspace_query",
        provenance: str = "local_extraction",
        modality: Modality = Modality.TEXT,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> MemorySignature:
        extraction = await self._extract(text, modality)

        if extraction is None:
            raise CriticalServiceUnavailable("T1 structured extraction unavailable for L1 encoder")

        structured = StructuredSignature(
            entities=extraction.entities,
            relations=extraction.relations,
            causal_chain=extraction.causal,
            intent=SignatureIntent(
                type=intent_type,
                certainty="confirmed" if extraction.confidence >= 0.72 else "candidate",
            ),
        )
        sig_id = stable_id("sig", f"{provenance}:{intent_type}:{modality.value}:{text}")
        return MemorySignature(
            id=sig_id,
            provenance=provenance,
            structured=structured,
            latent_embedding=[],  # set by encode() via _external_embedding
            abstraction_tags=extraction.tags,
            confidence=Confidence(score=extraction.confidence, source="dual_encoder_t1_extracted"),
            modality=modality,
            linked_signatures=[],
            raw_excerpt=bounded_excerpt(text),
            workspace_id=workspace_id,
            user_id=user_id,
            metadata=extraction.metadata,
        )

    async def _extract(self, text: str, modality: Modality) -> EncoderExtraction | None:
        """Extract structured knowledge via T1 (Qwen3-1.7B).

        Returns None if the bridge is unavailable â€” caller surfaces as explicit gap.
        Never falls back to regex.
        """
        entity_names: dict[str, str] = {}
        relations: list[Relation] = []
        causal: list[CausalLink] = []
        tags: set[str] = {modality.value, "dual_representation", "t1_extracted"}
        metadata: dict[str, Any] = {
            "encoder_version": "layer1_v9_t1_extraction",
            "structured_extractors": ["t1_qwen_bridge"],
        }

        def add_entity(name: str, entity_type: str | None = None) -> None:
            cleaned = clean_ref(name)
            if not cleaned:
                return
            entity_names[cleaned] = entity_type or entity_names.get(cleaned) or "concept"

        def add_relation(subject: str, predicate: str, obj: str, confidence: float) -> None:
            subject = clean_ref(subject)
            obj = clean_ref(obj)
            if not subject or not obj:
                return
            add_entity(subject)
            add_entity(obj)
            relation = Relation(subject=subject, predicate=predicate, object=obj, confidence=confidence)
            if relation not in relations:
                relations.append(relation)
            tags.add(predicate)
            if predicate == "causes":
                link = CausalLink(cause=subject, effect=obj, confidence=confidence)
                if link not in causal:
                    causal.append(link)

        # â”€â”€ T1 structured extraction (all natural language, any language) â”€â”€
        t1_data: dict[str, Any] | None = None
        if self.bridge is not None and getattr(self.bridge, "qwen_enabled", False):
            try:
                t1_data = await self.bridge.extract_structured_relations(text, modality.value)
            except Exception as exc:
                logger.warning("T1 extract_structured_relations failed: %s", repr(exc))
                t1_data = None

        if t1_data is None:
            return None

        for ent in t1_data.get("entities", []):
            if isinstance(ent, dict) and ent.get("name"):
                add_entity(str(ent["name"]), ent.get("type"))
            elif isinstance(ent, str):
                add_entity(ent)

        for rel in t1_data.get("relations", []):
            if not isinstance(rel, dict):
                continue
            try:
                conf = float(rel.get("confidence", 0.8))
            except (TypeError, ValueError):
                conf = 0.8
            add_relation(
                str(rel.get("subject", "")),
                str(rel.get("predicate", "")),
                str(rel.get("object", "")),
                max(0.0, min(1.0, conf)),
            )

        for link in t1_data.get("causal", []):
            if not isinstance(link, dict):
                continue
            cause = str(link.get("cause", "")).strip()
            effect = str(link.get("effect", "")).strip()
            if cause and effect:
                try:
                    conf = float(link.get("confidence", 0.8))
                except (TypeError, ValueError):
                    conf = 0.8
                add_relation(cause, "causes", effect, max(0.0, min(1.0, conf)))

        # â”€â”€ Code/Data structural extraction (formal parsers, not NLP) â”€â”€
        if modality == Modality.CODE:
            metadata["structured_extractors"].append("code_structure_parser")
            code_entities, code_relations, code_tags, code_meta = extract_code_structure(text)
            metadata.update(code_meta)
            tags.update(code_tags)
            for name, entity_type in code_entities:
                add_entity(name, entity_type)
            for subject, predicate, obj, confidence in code_relations:
                add_relation(subject, predicate, obj, confidence)

        if modality == Modality.DATA:
            metadata["structured_extractors"].append("data_schema_parser")
            data_entities, data_relations, data_tags, data_meta = extract_data_structure(text)
            metadata.update(data_meta)
            tags.update(data_tags)
            for name, entity_type in data_entities:
                add_entity(name, entity_type)
            for subject, predicate, obj, confidence in data_relations:
                add_relation(subject, predicate, obj, confidence)

        entities = [
            Entity(id=stable_id("ent", name), name=name, type=entity_type)
            for name, entity_type in sorted(entity_names.items())
        ]
        confidence = self._confidence(text, entities, relations, causal, metadata)
        metadata.update({
            "entity_count": len(entities),
            "relation_count": len(relations),
            "causal_count": len(causal),
            "latent_embedding_source": "none",  # set by encode() after _external_embedding
        })

        # Tags from T1-extracted entities and relations only
        typed_tags = {entity.type for entity in entities}
        all_tags = sorted((tags | typed_tags | {entity.name.lower() for entity in entities[:8]}) - {""})[:48]

        return EncoderExtraction(
            entities=entities,
            relations=relations,
            causal=causal,
            tags=all_tags,
            metadata=metadata,
            confidence=confidence,
        )

    def _confidence(
        self,
        text: str,
        entities: list[Entity],
        relations: list[Relation],
        causal: list[CausalLink],
        metadata: dict[str, Any],
    ) -> float:
        if not text.strip():
            return 0.0
        score = 0.62
        score += min(0.18, len(entities) * 0.02)
        score += min(0.22, len(relations) * 0.05)
        score += min(0.1, len(causal) * 0.04)
        if metadata.get("tree_sitter_available"):
            score += 0.04
        if metadata.get("data_schema_detected"):
            score += 0.04
        return round(min(score, 0.94), 4)

    def _surrogate_text(self, content: str, modality: Modality) -> str:
        prefix = modality.value.upper()
        if content.strip().startswith(("http://", "https://", "r2://", "s3://", "file://")):
            return f"{prefix} asset {content.strip()}"
        return f"{prefix} training asset {stable_id('asset', content)}"

    async def _external_embedding(self, content: str, modality: Modality) -> list[float]:
        """Call the real embedding service and return [] on transport failure."""
        adapter = self.multimodal_adapter
        if adapter and hasattr(adapter, "encode"):
            try:
                vector = adapter.encode(content, modality)
                # Handle both sync and async adapters
                if hasattr(vector, "__await__"):
                    vector = await vector
                if vector:
                    return vector
                logger.warning("Embedding service returned empty vector for modality=%s", modality)
            except Exception:
                logger.exception("Embedding service call failed for modality=%s", modality)
        return []

    def _latent_model_name(self, modality: Modality) -> str:
        if modality == Modality.CODE:
            return "nomic-embed-code"
        if modality == Modality.IMAGE:
            return "siglip-2"
        if modality in {Modality.AUDIO, Modality.VIDEO}:
            return "hubert-or-whisper-derived"
        return "nomic-embed-text"
