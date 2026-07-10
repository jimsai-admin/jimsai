from __future__ import annotations

import os
from typing import Any

FUNCTIONAL_CARDINALITY_VALUES = {"one", "single", "functional", "unique"}
MULTI_CARDINALITY_VALUES = {"many", "multiple", "set", "list"}


def normalize_relation_cardinality(value: Any) -> str | None:
    value_text = str(value or "").strip().lower()
    if value_text in FUNCTIONAL_CARDINALITY_VALUES:
        return "one"
    if value_text in MULTI_CARDINALITY_VALUES:
        return "many"
    return None


def relation_cardinality_overlay(value: Any) -> dict[str, str]:
    raw_items: list[tuple[Any, Any]] = []
    if isinstance(value, dict):
        raw_items = list(value.items())
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            predicate = item.get("predicate") or item.get("name")
            cardinality = item.get("cardinality") or item.get("object_cardinality") or item.get("value")
            raw_items.append((predicate, cardinality))

    normalized: dict[str, str] = {}
    for predicate_raw, value_raw in raw_items:
        predicate = str(predicate_raw or "").strip()
        cardinality = normalize_relation_cardinality(value_raw)
        if predicate and cardinality:
            normalized[predicate[:80]] = cardinality
    return normalized


def configured_functional_predicates() -> set[str]:
    configured = os.getenv("JIMS_FUNCTIONAL_RELATION_PREDICATES", "")
    return {item.strip() for item in configured.split(",") if item.strip()}


def metadata_marks_functional(metadata: dict, predicate: str) -> bool:
    relation_cardinality = metadata.get("relation_cardinality")
    if isinstance(relation_cardinality, dict):
        value = relation_cardinality.get(predicate) or relation_cardinality.get("*")
        if normalize_relation_cardinality(value) == "one":
            return True
        if value is True:
            return True

    functional_predicates = metadata.get("functional_predicates")
    if isinstance(functional_predicates, (list, tuple, set)) and predicate in {
        str(item).strip() for item in functional_predicates
    }:
        return True

    relation_schemas = metadata.get("relation_schemas")
    if isinstance(relation_schemas, dict):
        schema = relation_schemas.get(predicate)
        if isinstance(schema, dict):
            cardinality = schema.get("cardinality") or schema.get("object_cardinality")
            return normalize_relation_cardinality(cardinality) == "one"
    return False


def relation_is_functional(signature: Any, predicate: str) -> bool:
    metadata = getattr(signature, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata_marks_functional(metadata, predicate) or predicate in configured_functional_predicates()


def metadata_marks_multivalued(metadata: dict, predicate: str) -> bool:
    relation_cardinality = metadata.get("relation_cardinality")
    if isinstance(relation_cardinality, dict):
        value = relation_cardinality.get(predicate) or relation_cardinality.get("*")
        if normalize_relation_cardinality(value) == "many":
            return True
    schemas = metadata.get("relation_schemas")
    if isinstance(schemas, dict):
        schema = schemas.get(predicate)
        if isinstance(schema, dict):
            card = schema.get("cardinality") or schema.get("object_cardinality")
            if normalize_relation_cardinality(card) == "many":
                return True
    multi = metadata.get("multivalued_predicates")
    if isinstance(multi, (list, tuple, set)) and predicate in {str(m).strip() for m in multi}:
        return True
    return False


def configured_multivalued_predicates() -> set[str]:
    configured = os.getenv("JIMS_MULTIVALUED_RELATION_PREDICATES", "")
    return {item.strip() for item in configured.split(",") if item.strip()}


def relation_is_multivalued(signature: Any, predicate: str) -> bool:
    """True when the ontology/metadata EXPLICITLY marks this relation as a set
    (a subject may hold many objects — "speaks", "member_of"). Used to EXEMPT
    such relations from latest-wins supersession. Absent an explicit marker a
    relation is treated as single-valued (its current value is its latest
    assertion) — the projection engine's default, made precise by ontology
    cardinality data (M5) rather than a hardcoded predicate list."""
    metadata = getattr(signature, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata_marks_multivalued(metadata, predicate) or predicate in configured_multivalued_predicates()
