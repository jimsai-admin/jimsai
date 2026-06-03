from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass
from io import StringIO
from typing import Any

from .models import CausalLink, Confidence, Entity, MemorySignature, Modality, Relation, SignatureIntent, StructuredSignature


QUESTION_SUBJECTS = {"what", "why", "how", "when", "where", "who", "which"}
STOP_TAGS = {
    "about",
    "after",
    "before",
    "between",
    "could",
    "first",
    "from",
    "have",
    "into",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "using",
    "where",
    "which",
    "would",
}
DEPENDENCY_VERBS = {
    "depends on": "depends_on",
    "depend on": "depends_on",
    "requires": "depends_on",
    "require": "depends_on",
    "uses": "depends_on",
    "use": "depends_on",
    "calls": "calls",
    "call": "calls",
    "imports": "imports",
    "import": "imports",
    "queries": "queries",
    "query": "queries",
    "reads": "reads",
    "read": "reads",
    "writes": "writes",
    "write": "writes",
    "publishes to": "publishes_to",
    "sends to": "sends_to",
    "emits": "emits",
}
CAUSAL_VERBS = {
    "causes",
    "cause",
    "triggers",
    "trigger",
    "invalidates",
    "invalidate",
    "breaks",
    "break",
    "blocks",
    "block",
    "delays",
    "delay",
    "forces",
    "force",
    "leads to",
    "results in",
    "produces",
    "produce",
}
ENTITY_TYPE_HINTS = [
    ("service", re.compile(r"(Service|Controller|Gateway|Repository|Worker|Queue|API)$", re.IGNORECASE)),
    ("method", re.compile(r"^[A-Za-z][\w]*\.[a-z_][\w]*$", re.IGNORECASE)),
    ("state", re.compile(r"\.(failure|blocked|delay|drift|timeout|shutdown|slowdown|late_delivery|recount|invalidat|change)", re.IGNORECASE)),
    ("database", re.compile(r"(Postgres|Supabase|Redis|Neo4j|Vectorize|R2|MySQL|Database|DB)$", re.IGNORECASE)),
    ("table", re.compile(r"(Table|_table|\.table|schema)$", re.IGNORECASE)),
    ("module", re.compile(r"(Module|Engine|Layer|Runtime|Pipeline|Compiler|Encoder)$", re.IGNORECASE)),
    ("person", re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")),
]


def bounded_excerpt(text: str, max_chars: int = 1200) -> str:
    """Keep a retrievable excerpt without cutting through words or sentences."""
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


@dataclass(frozen=True)
class EncoderExtraction:
    entities: list[Entity]
    relations: list[Relation]
    causal: list[CausalLink]
    tags: list[str]
    metadata: dict[str, Any]
    confidence: float


def clean_ref(value: str) -> str:
    return value.strip().strip(".,:;!?)]}\"'")


def stable_id(prefix: str, text: str) -> str:
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def hash_embedding(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"[\w\.]+", text.lower(), flags=re.UNICODE):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


class DualRepresentationEncoder:
    def __init__(self, multimodal_adapter: object | None = None) -> None:
        self.multimodal_adapter = multimodal_adapter

    def encode(
        self,
        content: str,
        modality: Modality = Modality.TEXT,
        intent_type: str = "workspace_query",
        provenance: str = "local_extraction",
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> MemorySignature:
        if modality in {Modality.TEXT, Modality.CODE, Modality.DATA}:
            signature = self.encode_text(
                content,
                intent_type=intent_type,
                provenance=provenance,
                modality=modality,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        else:
            signature = self.encode_text(
                self._surrogate_text(content, modality),
                intent_type=intent_type,
                provenance=provenance,
                modality=modality,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            signature.raw_excerpt = content[:500]
        vector = self._external_embedding(content, modality)
        if vector:
            signature.latent_embedding = vector
            signature.confidence.source = "dual_encoder_external_latent"
            signature.metadata["latent_encoder"] = self._latent_model_name(modality)
            signature.metadata["latent_embedding_source"] = "external_service"
            signature.metadata["reembedding_required"] = False
        elif self.multimodal_adapter and modality in {Modality.TEXT, Modality.CODE, Modality.DATA}:
            signature.metadata["latent_embedding_source"] = "hash_projection"
            signature.metadata["reembedding_required"] = True
            signature.metadata["reembedding_reason"] = "external_embedding_service_unavailable_or_returned_no_vector"
            signature.metadata["reembedding_target"] = self._latent_model_name(modality)
        elif modality not in {Modality.TEXT, Modality.CODE, Modality.DATA}:
            signature.latent_embedding = []
            signature.confidence.score = min(signature.confidence.score, 0.35)
            signature.confidence.source = "external_multimodal_encoding_required"
            signature.metadata["latent_encoder"] = "kaggle_batch_or_external_service_required"
            signature.metadata["queued_for_multimodal_training"] = True
            signature.metadata["reembedding_required"] = True
            signature.metadata["reembedding_reason"] = "multimodal_embedding_required"
        return signature

    def encode_text(
        self,
        text: str,
        intent_type: str = "workspace_query",
        provenance: str = "local_extraction",
        modality: Modality = Modality.TEXT,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> MemorySignature:
        extraction = self._extract(text, modality)
        structured = StructuredSignature(
            entities=extraction.entities,
            relations=extraction.relations,
            causal_chain=extraction.causal,
            intent=SignatureIntent(type=intent_type, certainty="confirmed" if extraction.confidence >= 0.72 else "candidate"),
        )
        sig_id = stable_id("sig", f"{provenance}:{intent_type}:{modality.value}:{text}")
        return MemorySignature(
            id=sig_id,
            provenance=provenance,
            structured=structured,
            latent_embedding=hash_embedding(text),
            abstraction_tags=extraction.tags,
            confidence=Confidence(score=extraction.confidence, source="dual_encoder_structured_hash_latent"),
            modality=modality,
            linked_signatures=[],
            raw_excerpt=bounded_excerpt(text),
            workspace_id=workspace_id,
            user_id=user_id,
            metadata=extraction.metadata,
        )

    def _extract(self, text: str, modality: Modality) -> EncoderExtraction:
        entity_names: dict[str, str] = {}
        relations: list[Relation] = []
        causal: list[CausalLink] = []
        tags: set[str] = {modality.value, "dual_representation"}
        metadata: dict[str, Any] = {"encoder_version": "layer1_v8_2026_05", "structured_extractors": []}

        def add_entity(name: str, entity_type: str | None = None) -> None:
            cleaned = clean_ref(name)
            if not cleaned or cleaned.lower() in QUESTION_SUBJECTS:
                return
            entity_names[cleaned] = entity_type or entity_names.get(cleaned) or infer_entity_type(cleaned)

        def add_relation(subject: str, predicate: str, obj: str, confidence: float) -> None:
            subject = clean_ref(subject)
            obj = clean_ref(obj)
            if not subject or not obj or subject.lower() in QUESTION_SUBJECTS:
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

        metadata["structured_extractors"].append("entity_surface_forms")
        for name in extract_entity_names(text):
            add_entity(name)
        for subject, predicate, obj, confidence in extract_sentence_relations(text):
            add_relation(subject, predicate, obj, confidence)
        if modality == Modality.CODE:
            metadata["structured_extractors"].append("tree_sitter_or_code_patterns")
            code_entities, code_relations, code_tags, code_meta = extract_code_structure(text)
            metadata.update(code_meta)
            tags.update(code_tags)
            for name, entity_type in code_entities:
                add_entity(name, entity_type)
            for subject, predicate, obj, confidence in code_relations:
                add_relation(subject, predicate, obj, confidence)
        if modality == Modality.DATA:
            metadata["structured_extractors"].append("data_schema")
            data_entities, data_relations, data_tags, data_meta = extract_data_structure(text)
            metadata.update(data_meta)
            tags.update(data_tags)
            for name, entity_type in data_entities:
                add_entity(name, entity_type)
            for subject, predicate, obj, confidence in data_relations:
                add_relation(subject, predicate, obj, confidence)

        for token in re.findall(r"\b[^\W\d_][\w]{4,}\b", text.lower(), flags=re.UNICODE):
            if token not in STOP_TAGS:
                tags.add(token)
            if len(entity_names) < 12 and not entity_names and token not in STOP_TAGS:
                add_entity(token, "concept")

        entities = [Entity(id=stable_id("ent", name), name=name, type=entity_type) for name, entity_type in sorted(entity_names.items())]
        confidence = self._confidence(text, entities, relations, causal, metadata)
        metadata.update(
            {
                "entity_count": len(entities),
                "relation_count": len(relations),
                "causal_count": len(causal),
                "latent_embedding_source": "hash_projection",
            }
        )
        typed_tags = {entity.type for entity in entities}
        return EncoderExtraction(
            entities=entities,
            relations=relations,
            causal=causal,
            tags=sorted((tags | typed_tags | {entity.name.lower() for entity in entities[:8]}) - {""})[:48],
            metadata=metadata,
            confidence=confidence,
        )

    def _confidence(self, text: str, entities: list[Entity], relations: list[Relation], causal: list[CausalLink], metadata: dict[str, Any]) -> float:
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

    def _external_embedding(self, content: str, modality: Modality) -> list[float]:
        adapter = self.multimodal_adapter
        if adapter and hasattr(adapter, "encode"):
            try:
                vector = adapter.encode(content, modality)
                if vector:
                    return vector
            except Exception:
                return []
        return []

    def _latent_model_name(self, modality: Modality) -> str:
        if modality == Modality.CODE:
            return "nomic-embed-code"
        if modality == Modality.IMAGE:
            return "siglip-2"
        if modality in {Modality.AUDIO, Modality.VIDEO}:
            return "hubert-or-whisper-derived"
        return "nomic-embed-text"


def extract_entity_names(text: str) -> list[str]:
    names = set()
    dotted = r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+"
    camel = r"[A-Z][A-Za-z0-9_]*(?:[A-Z][A-Za-z0-9_]*)?"
    title_phrase = r"[A-Z][a-z]+(?:\s+[A-Z][a-z0-9]+){1,5}"
    for pattern in (dotted, camel, title_phrase):
        for match in re.finditer(pattern, text):
            value = clean_ref(match.group(0))
            if value and value.lower() not in QUESTION_SUBJECTS:
                names.add(value)
    return sorted(names)


def extract_sentence_relations(text: str) -> list[tuple[str, str, str, float]]:
    facts: list[tuple[str, str, str, float]] = []
    subject = r"(?P<subject>[A-Za-z][\w\.]*)"
    obj = r"(?P<object>[A-Za-z][\w\.]*)"
    phrase_subject = r"(?P<subject>[A-Za-z][\w\.]*(?:\s+[A-Z][A-Za-z0-9_]*){0,4})"
    phrase_obj = r"(?P<object>[A-Za-z][\w\.]*(?:\s+[A-Z][A-Za-z0-9_]*){0,5})"
    dep_verbs = "|".join(re.escape(verb) for verb in sorted(DEPENDENCY_VERBS, key=len, reverse=True))
    causal_verbs = "|".join(re.escape(verb) for verb in sorted(CAUSAL_VERBS, key=len, reverse=True))
    for match in re.finditer(
        r"\bmy\s+name\s+is\s+(?P<object>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,4})",
        text,
        flags=re.IGNORECASE,
    ):
        facts.append(("user", "has_name", match.group("object"), 0.96))
    for match in re.finditer(r"\bi\s+am\s+(?:a|an)\s+(?P<object>[a-z][a-z0-9_\-\s]{2,80}?)(?:[.;,]|$)", text, flags=re.IGNORECASE):
        role = clean_ref(match.group("object"))
        if role:
            facts.append(("user", "has_role", role, 0.9))
    for match in re.finditer(r"\bi\s+am\s+building\s+(?P<object>[A-Za-z0-9][A-Za-z0-9_\-\s]{2,120}?)(?:[.;,]|$)", text, flags=re.IGNORECASE):
        project = clean_ref(match.group("object"))
        if project:
            facts.append(("user", "is_building", project, 0.9))
    for match in re.finditer(rf"{subject}\s+(?P<verb>{dep_verbs})\s+{obj}", text, flags=re.IGNORECASE):
        facts.append((match.group("subject"), DEPENDENCY_VERBS[match.group("verb").lower()], match.group("object"), 0.84))
    for match in re.finditer(rf"{subject}\s+(?P<verb>{causal_verbs})\s+{obj}", text, flags=re.IGNORECASE):
        facts.append((match.group("subject"), "causes", match.group("object"), 0.86))
    for match in re.finditer(rf"if\s+{subject}.*?\bthen\s+{obj}", text, flags=re.IGNORECASE):
        facts.append((match.group("subject"), "causes", match.group("object"), 0.82))
    for match in re.finditer(rf"{phrase_subject}\s+(?:is|are)\s+(?:a|an|the)?\s*{phrase_obj}", text):
        facts.append((match.group("subject"), "is_a", match.group("object"), 0.72))
    for match in re.finditer(rf"{phrase_subject}\s+(?:means|stands for)\s+{phrase_obj}", text, flags=re.IGNORECASE):
        facts.append((match.group("subject"), "means", match.group("object"), 0.9))
    return facts


def extract_code_structure(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, float]], set[str], dict[str, Any]]:
    entities: list[tuple[str, str]] = []
    relations: list[tuple[str, str, str, float]] = []
    tags = {"code", "call_graph", "tree_sitter_contract"}
    metadata: dict[str, Any] = {"tree_sitter_available": tree_sitter_available(), "language": infer_code_language(text)}
    for match in re.finditer(r"^\s*class\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "class"))
    for match in re.finditer(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "function"))
    for match in re.finditer(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_][\w]*)", text, flags=re.MULTILINE):
        entities.append((match.group("name"), "function"))
    for match in re.finditer(r"^\s*(?:import|from)\s+(?P<name>[A-Za-z_][\w\.]*)", text, flags=re.MULTILINE):
        module = match.group("name")
        entities.append((module, "module"))
        for function_name, _ in entities:
            relations.append((function_name, "imports", module, 0.68))
    for match in re.finditer(r"(?P<caller>[A-Za-z_][\w]*)\s*\([^)]*\).*?\n(?:.|\n){0,220}?(?P<callee>[A-Za-z_][\w]*)\s*\(", text):
        caller = match.group("caller")
        callee = match.group("callee")
        if caller != callee and not caller[0].islower():
            relations.append((caller, "calls", callee, 0.58))
    metadata["code_entity_count"] = len(entities)
    return dedupe_pairs(entities), dedupe_relation_tuples(relations), tags, metadata


def extract_data_structure(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, float]], set[str], dict[str, Any]]:
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


def infer_code_language(text: str) -> str:
    if re.search(r"^\s*(?:async\s+)?def\s+", text, flags=re.MULTILINE):
        return "python"
    if re.search(r"^\s*(?:export\s+)?(?:async\s+)?function\s+", text, flags=re.MULTILINE):
        return "javascript"
    if re.search(r"\b(public|private|protected)\s+class\s+\w+", text):
        return "java_or_csharp"
    if re.search(r"#include\s+<", text):
        return "cpp"
    return "unknown"


def infer_entity_type(name: str) -> str:
    for entity_type, pattern in ENTITY_TYPE_HINTS:
        if pattern.search(name):
            return entity_type
    if name.isupper() and len(name) <= 8:
        return "abbreviation"
    if "." in name:
        return "qualified_symbol"
    if name[:1].isupper():
        return "concept"
    return "term"


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
