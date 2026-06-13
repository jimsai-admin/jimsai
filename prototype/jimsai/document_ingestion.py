from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .encoder import stable_id
from .models import Confidence, Entity, MemorySignature, Relation, SignatureIntent, StructuredSignature


@dataclass(frozen=True)
class DocumentFact:
    subject: str
    predicate: str
    object: str
    raw_excerpt: str
    confidence: float = 0.88


def is_document_like(text: str) -> bool:
    upper = text.upper()
    return (
        len(text) > 10
        or "ABSTRACT" in upper
        or "CHAPTER ONE" in upper
        or "TABLE OF CONTENTS" in upper
        or "LIST OF ABBREVIATIONS" in upper
    )


def extract_document_facts(text: str) -> list[DocumentFact]:
    facts: list[DocumentFact] = []
    subject = _document_subject(text)

    def add(subject: str, predicate: str, obj: str, raw_excerpt: str = "", confidence: float = 0.88) -> None:
        value = _clean_value(obj)
        if not value:
            return
        facts.append(
            DocumentFact(
                subject=subject,
                predicate=predicate,
                object=value,
                raw_excerpt=raw_excerpt or value,
                confidence=confidence,
            )
        )

    title = _extract_title(text)
    if title:
        add(subject, "has_title", title, title, 0.93)

    for label, value in _extract_labeled_values(text):
        predicate = _label_to_predicate(label)
        if predicate:
            add(subject, predicate, value, f"{label}: {value}", 0.9)

    for subject, meaning in _extract_abbreviations(text):
        add(subject, "means", meaning, f"{subject} {meaning}", 0.95)

    for objective in _extract_bullets_between(text, "Specific Objectives", "Scope of the Project"):
        if objective.lower().startswith("to "):
            add(subject, "has_objective", objective, objective, 0.9)

    for problem in _extract_bullets_between(text, "Statement of the Problem", "Choice and Motivation"):
        add(subject, "has_problem", problem, problem, 0.86)

    for module in _extract_module_lines(text):
        add(subject, "has_module", module, module, 0.9)

    for technology in _extract_technologies(text):
        add(subject, "uses_technology", technology, technology, 0.86)

    return _dedupe_facts(facts)


def fact_to_signature(fact: DocumentFact, source_id: str) -> MemorySignature:
    sig_id = stable_id("docsig", f"{source_id}:{fact.subject}:{fact.predicate}:{fact.object}")
    subject_entity = Entity(id=stable_id("ent", fact.subject), name=fact.subject, type="document_subject")
    object_entities = _object_entities(fact.object)
    structured = StructuredSignature(
        entities=[subject_entity, *object_entities],
        relations=[Relation(subject=fact.subject, predicate=fact.predicate, object=fact.object, confidence=fact.confidence)],
        intent=SignatureIntent(type="document_fact", certainty="confirmed"),
    )
    return MemorySignature(
        id=sig_id,
        provenance="document_structured_extraction",
        structured=structured,
        latent_embedding=_fact_embedding(fact),
        abstraction_tags=[fact.predicate, fact.subject.lower(), "document_fact"],
        confidence=Confidence(score=fact.confidence, source="document_structured_extractor"),
        linked_signatures=[source_id],
        raw_excerpt=fact.raw_excerpt[:500],
    )


def _extract_title(text: str) -> str:
    explicit = _match_one(text, r"TITLE:\s*(.+)")
    if explicit:
        return explicit
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if line.startswith("DESIGN AND IMPLEMENTATION"):
            parts = [line]
            for next_line in lines[index + 1 : index + 5]:
                if not next_line or next_line.startswith("Case Study"):
                    break
                parts.append(next_line)
            return " ".join(parts)
    return ""


def _document_subject(text: str) -> str:
    title = _extract_title(text)
    if title:
        return stable_id("doc", title)
    first_content = next((line.strip() for line in text.splitlines() if len(line.strip()) >= 8), "")
    return stable_id("doc", first_content or text[:120] or "document")


def _extract_labeled_values(text: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for line in text.splitlines():
        match = re.match(r"^\s*(?P<label>[^:\n]{2,80})\s*:\s*(?P<value>[^:\n]{1,240})\s*$", line)
        if not match:
            continue
        label = _clean_value(match.group("label"))
        value = _clean_value(match.group("value"))
        if label and value:
            values.append((label, value))
    return values


def _label_to_predicate(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    normalized = re.sub(r"^(name_of_the_|name_of_|the_)", "", normalized)
    if not normalized:
        return ""
    if normalized in {"researcher", "author", "writer", "creator"}:
        return "has_author"
    if normalized in {"case_study", "case", "study_case"}:
        return "has_case_study"
    if normalized in {"student_id", "id", "identifier"}:
        return "has_student_id"
    if normalized in {"institution", "university", "school", "organization", "organisation"}:
        return "has_institution"
    if normalized == "title":
        return "has_title"
    return f"has_{normalized}"


def _extract_abbreviations(text: str) -> list[tuple[str, str]]:
    block = _section(text, "LIST OF ABBREVIATIONS", "DEFINITION OF TERMINOLOGIES")
    rows: list[tuple[str, str]] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("abbreviation"):
            continue
        match = re.match(r"^([A-Z][A-Z0-9]{1,8})\s+(.+)$", stripped)
        if match:
            rows.append((match.group(1), match.group(2).strip()))
    return rows


def _extract_bullets_between(text: str, start: str, end: str) -> list[str]:
    block = _section(text, start, end)
    bullets: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if _is_bullet(stripped):
            bullets.append(_clean_value(_strip_bullet(stripped)))
    return bullets


def _extract_module_lines(text: str) -> list[str]:
    block = _section(text, "Scope of the Project", "Methodology and Techniques Used")
    modules: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not _is_bullet(stripped) or "Module" not in stripped:
            continue
        modules.append(_clean_value(_strip_bullet(stripped).split(":", 1)[0]))
    return modules


def _extract_technologies(text: str) -> list[str]:
    block = _section(text, "Technologies and Tools Used", "Presentation of the New System")
    technologies: set[str] = set()
    for line in block.splitlines():
        stripped = _clean_value(_strip_bullet(line))
        if not stripped:
            continue
        for item in re.split(r",|;|\band\b", stripped, flags=re.IGNORECASE):
            candidate = _clean_value(item)
            if 1 < len(candidate) <= 80 and re.search(r"[A-Za-z0-9]", candidate):
                technologies.add(candidate)
    return sorted(technologies)


def _section(text: str, start: str, end: str) -> str:
    candidates: list[str] = []
    for start_match in re.finditer(re.escape(start), text, flags=re.IGNORECASE):
        tail = text[start_match.end() :]
        end_match = re.search(re.escape(end), tail, flags=re.IGNORECASE)
        candidates.append(tail[: end_match.start()] if end_match else tail)
    if not candidates:
        return ""
    return max(candidates, key=lambda block: (sum(char.isalpha() for char in block), len(block.strip())))


def _match_one(text: str, pattern: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags=flags)
    return _clean_value(match.group(1)) if match else ""


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" .;\t\r\n"))


def _is_bullet(value: str) -> bool:
    stripped = value.lstrip()
    if not stripped:
        return False
    if re.match(r"^(?:\d+|[A-Za-z])[\).\]]\s+", stripped):
        return True
    first = stripped[0]
    category = unicodedata.category(first)
    return category.startswith("P") or category.startswith("S")


def _strip_bullet(value: str) -> str:
    stripped = value.strip()
    stripped = re.sub(r"^(?:\d+|[A-Za-z])[\).\]]\s+", "", stripped)
    if stripped:
        first = stripped[0]
        if unicodedata.category(first).startswith(("P", "S")):
            return stripped[1:].strip()
    return stripped.strip()


def _dedupe_facts(facts: list[DocumentFact]) -> list[DocumentFact]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[DocumentFact] = []
    for fact in facts:
        key = (fact.subject.lower(), fact.predicate, fact.object.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def _object_entities(value: str) -> list[Entity]:
    names = sorted(
        {
            item.strip()
            for item in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\b", value)
            if len(item.strip()) > 1
        }
    )[:6]
    return [Entity(id=stable_id("ent", name), name=name, type="document_value") for name in names]


def _fact_embedding(fact: DocumentFact) -> list[float]:
    # Hash embeddings removed — document fact signatures are stored with
    # latent_embedding=[] and flagged reembedding_required=True until
    # the autonomous re-embedding loop processes them via Modal.
    return []
