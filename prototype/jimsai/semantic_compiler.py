from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR


STOP_WORDS = {
    "a", "an", "the", "yo", "please", "just", "over", "that", "we", "back", "in", "for",
    "to", "of", "and", "or", "on", "with", "can", "you", "i", "me", "my", "is", "are",
    "do", "does", "did", "would", "become",
}
QUESTION_WORDS = {"What", "Why", "How", "When", "Where", "Who", "Which"}
IMPACT_TOKENS = {
    "affect",
    "impact",
    "chang",
    "change",
    "happen",
    "break",
    "depend",
    "downstream",
    "upstream",
    "cause",
    "caus",
    "late",
    "delay",
    "fail",
    "failure",
    "slowdown",
    "occur",
    "block",
    "blocked",
}
DOCUMENT_WIDE_RELATIONS = {
    "has_title",
    "has_case_study",
    "has_author",
    "has_institution",
    "has_objective",
    "has_module",
    "has_problem",
    "uses_technology",
}
PROFILE_QUERY_PATTERNS = (
    r"\bmy\s+name\b",
    r"\bwho\s+am\s+i\b",
    r"\bwhat\s+do\s+you\s+(know|remember)\s+about\s+me\b",
    r"\btell\s+me\s+about\s+me\b",
    r"\bmy\s+profile\b",
)

INTENT_TEMPLATES: dict[str, str] = {
    "FETCH_DOCUMENT": "pull layout document manifest file pdf page download view open retrieve",
    "SYSTEM_DIAGNOSTIC": "error broken status crash failure bug log deployment timeout diagnostic",
    "WORKSPACE_QUERY": "metrics analysis progress overview stats tracking services dependencies affected happen impact change downstream upstream cause late delay why means meaning title company case study objectives modules scope technologies used tools",
    "CODE_GENERATE": "create build scaffold generate api route function class code implementation",
    "RUN_CANVAS": "analyse analyze deep scan full codebase corpus dataset synthesis everything uploaded",
    "RUN_INVENTION": "invent design novel architecture theorem hypothesis protocol plan new solution",
    "GENERAL_FACT": "what explain define describe capital concept general knowledge means meaning title company case study objectives modules technologies",
    "EMOTIONAL_CATCH": "stressed overwhelmed anxious confused giving up frustrated hard worried",
    "META_INQUIRY": "why answer confidence memory trace sources reasoning gaps explain yourself",
}

INTENT_DOMAINS: dict[str, IntentDomain] = {
    "GENERAL_FACT": IntentDomain.GENERAL_KNOWLEDGE,
    "EMOTIONAL_CATCH": IntentDomain.EMOTIONAL_SOCIAL,
    "META_INQUIRY": IntentDomain.META_SYSTEM,
}


def _stem(token: str) -> str:
    for suffix in ("ing", "ingly", "edly", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def sanitize(raw: str) -> list[str]:
    cleaned = re.sub(r"[^A-Za-z0-9_\-.\s]", " ", raw.lower())
    tokens = [_stem(t) for t in cleaned.split() if t and t not in STOP_WORDS]
    return tokens


def _vectorize(tokens: list[str]) -> Counter[str]:
    return Counter(tokens)


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(left[t] * right.get(t, 0) for t in left)
    lnorm = math.sqrt(sum(v * v for v in left.values()))
    rnorm = math.sqrt(sum(v * v for v in right.values()))
    if lnorm == 0 or rnorm == 0:
        return 0.0
    return dot / (lnorm * rnorm)


class SemanticCompilerRuntime:
    def __init__(self, confidence_threshold: float = 0.18) -> None:
        self.confidence_threshold = confidence_threshold
        self.template_vectors = {
            intent: _vectorize(sanitize(template))
            for intent, template in INTENT_TEMPLATES.items()
        }

    def score_intents(self, tokens: list[str]) -> list[Hypothesis]:
        user_vec = _vectorize(tokens)
        hypotheses = [
            Hypothesis(target_ir=intent, score=round(_cosine(user_vec, vec), 4))
            for intent, vec in self.template_vectors.items()
        ]
        hypotheses.sort(key=lambda h: (-h.score, h.target_ir))
        return hypotheses

    def resolve_hypotheses(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        positive = [h for h in hypotheses if h.score > 0.0]
        if not positive:
            return [Hypothesis(target_ir="OP_ESCAPE_TO_SANDBOX", score=0.0, role="primary", reason="No ontology match")]
        roles = ["primary", "overlay", "secondary"]
        resolved: list[Hypothesis] = []
        for idx, hyp in enumerate(positive[:3]):
            role = roles[idx] if idx < len(roles) else "candidate"
            resolved.append(hyp.model_copy(update={"role": role, "reason": "deterministic lexical score"}))
        return resolved

    def _scope_from_tokens(self, tokens: list[str], raw_input: str) -> dict[str, Any]:
        scope: dict[str, Any] = {"raw_length": len(raw_input), "token_count": len(tokens)}
        for token in tokens:
            if re.fullmatch(r"\d+", token):
                scope.setdefault("numbers", []).append(int(token))
            if token.endswith(".pdf"):
                scope["document_type"] = "PDF"
            if token in {"april", "may", "june", "july"}:
                scope["temporal_hint"] = token
        camel_entities = [
            entity.strip(".,:;!?")
            for entity in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\b", raw_input)
            if entity not in QUESTION_WORDS
        ]
        if "late" in tokens:
            camel_entities.extend(f"{entity}.late_delivery" for entity in list(camel_entities) if "." not in entity)
        if "blocked" in tokens or "block" in tokens:
            camel_entities.extend(f"{entity}.blocked" for entity in list(camel_entities) if "." in entity and not entity.endswith(".blocked"))
        if "failure" in tokens or "fail" in tokens:
            camel_entities.extend(f"{entity}.failure" for entity in list(camel_entities) if "." in entity and not entity.endswith(".failure"))
        if any(token.startswith("chang") for token in tokens):
            camel_entities.extend(f"{entity}_change" for entity in list(camel_entities) if "." in entity)
        raw_lower = raw_input.lower()
        question_intent: dict[str, str] = {}
        if re.search(r"\bwhat\s+(happens?|breaks?|is\s+affected)\s+if\b", raw_lower) or re.search(r"\bif\b.*\b(occurs?|changes?|fails?|breaks?)\b", raw_lower):
            question_intent = {"kind": "causal_impact", "relation": "causes", "direction": "outgoing"}
        elif raw_lower.startswith("why "):
            question_intent = {"kind": "causal_explanation", "relation": "causes", "direction": "incoming"}
        elif re.search(r"\bwhat\s+(does|do)\b.*\bdepend\s+on\b", raw_lower):
            question_intent = {"kind": "dependency_upstream", "relation": "depends_on", "direction": "outgoing"}
        elif re.search(r"\b(what|who|which)\b.*\bdepends?\s+on\b", raw_lower):
            question_intent = {"kind": "dependency_downstream", "relation": "depends_on", "direction": "incoming"}
        elif re.search(r"\b(what\s+does\s+)?[A-Z0-9]{2,8}\s+(mean|means|stand\s+for)\b", raw_input, flags=re.IGNORECASE):
            question_intent = {"kind": "definition_lookup", "relation": "means", "direction": "outgoing"}
        elif re.search(r"\b(title\s+of\s+the\s+project|project\s+title|final\s+year\s+project)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_title", "direction": "outgoing"}
        elif re.search(r"\b(case\s+study|company\s+.*\bcase\s+study|case\s+study\s+company)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_case_study", "direction": "outgoing"}
        elif re.search(r"\b(specific\s+objectives?|objectives?\s+of\s+the\s+study)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_objective", "direction": "outgoing"}
        elif re.search(r"\b(modules?\s+.*\bscope|scope\s+.*\bmodules?|modules?\s+are\s+in)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_module", "direction": "outgoing"}
        elif re.search(r"\b(technologies?\s+.*\bused|tools?\s+used|technologies?\s+and\s+tools)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "uses_technology", "direction": "outgoing"}
        elif re.search(r"\b(problems?\s+with\s+the\s+current\s+system|statement\s+of\s+the\s+problem)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_problem", "direction": "outgoing"}
        elif re.search(r"\b(author|researcher)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_author", "direction": "outgoing"}
        elif re.search(r"\b(institution|university)\b", raw_lower):
            question_intent = {"kind": "document_lookup", "relation": "has_institution", "direction": "outgoing"}
        if any(re.search(pattern, raw_lower) for pattern in PROFILE_QUERY_PATTERNS):
            scope["profile_query"] = True
        if question_intent:
            scope["question_intent"] = question_intent
        if camel_entities:
            scope["entities"] = sorted(set(camel_entities))
        return scope

    def compile(self, raw_input: str, namespace: str = "TECHNICAL", session: dict[str, Any] | None = None) -> SemanticIR:
        session = session or {}
        tokens = sanitize(raw_input)
        hypotheses = self.resolve_hypotheses(self.score_intents(tokens))
        primary = hypotheses[0]
        target_ir = primary.target_ir
        confidence = primary.score
        scope = self._scope_from_tokens(tokens, raw_input)
        raw_lower = raw_input.lower()
        causal_question = raw_lower.startswith("why ") and scope.get("entities")
        if scope.get("question_intent"):
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, 0.24)
        if scope.get("profile_query"):
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, 0.24)
        if scope.get("entities") and ((set(tokens) & IMPACT_TOKENS) or causal_question or scope.get("question_intent")):
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, 0.22)
        execution_mode = ExecutionMode.DETERMINISTIC_CORE
        if target_ir == "OP_ESCAPE_TO_SANDBOX" or confidence < self.confidence_threshold:
            target_ir = "OP_ESCAPE_TO_SANDBOX"
            execution_mode = ExecutionMode.AIR_GAPPED_CONTAINER
        context_inherited = False
        context_boosted = False
        question_intent = scope.get("question_intent")
        relation = question_intent.get("relation") if isinstance(question_intent, dict) else None
        if "entities" not in scope and session.get("ACTIVE_OBJECT") and relation not in DOCUMENT_WIDE_RELATIONS:
            scope["entities"] = [session["ACTIVE_OBJECT"]]
            context_inherited = True
        if confidence < 0.8 and session.get("ACTIVE_INTENT") == target_ir:
            confidence = min(confidence + 0.15, 1.0)
            context_boosted = True
        domain = INTENT_DOMAINS.get(target_ir, IntentDomain.WORKSPACE_OPERATION)
        return SemanticIR(
            target_ir=target_ir,
            system_action=target_ir,
            confidence=round(confidence, 4),
            scope_constraints=scope,
            execution_mode=execution_mode,
            domain_namespace=namespace,
            intent_domain=domain,
            tokens=tokens,
            hypotheses=hypotheses,
            context_inherited=context_inherited,
            context_boosted=context_boosted,
        )
