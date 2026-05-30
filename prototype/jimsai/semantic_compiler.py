from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR


STOP_WORDS = {
    "a", "an", "the", "yo", "please", "just", "over", "that", "we", "back", "in", "for",
    "to", "of", "and", "or", "on", "with", "can", "you", "i", "me", "my", "is", "are",
    "do", "does", "did", "would", "become", "what", "why", "how", "when", "where", "who", "which",
    "should", "someone",
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
GENERATION_ACTION_TOKENS = {"write", "create", "build", "generate", "make", "draw", "produce", "implement", "scaffold", "want"}
CODE_CAPABILITY_TOKENS = {
    "api",
    "bug",
    "class",
    "code",
    "debug",
    "fastapi",
    "function",
    "javascript",
    "library",
    "package",
    "python",
    "react",
    "refactor",
    "sdk",
    "test",
    "tests",
    "typescript",
}
CODE_DESIGN_TOKENS = {"calls", "consideration", "considerations", "design", "external", "fetch", "http", "safe", "security", "service"}
IMAGE_CAPABILITY_TOKENS = {"image", "picture", "photo", "logo", "poster", "illustration", "dashboard"}
VIDEO_CAPABILITY_TOKENS = {"video", "animation", "clip", "movie", "storyboard"}
AUDIO_CAPABILITY_TOKENS = {"audio", "voice", "speech", "tts", "sound", "music"}
CREATIVE_CAPABILITY_TOKENS = {"story", "poem", "script", "rewrite", "tone", "email", "proposal", "copy"}
AGENTIC_CAPABILITY_TOKENS = {
    "agent",
    "automate",
    "automat",
    "book",
    "browser",
    "click",
    "deploy",
    "deployment",
    "rollback",
    "schedule",
    "send",
    "task",
}
ARCHITECTURE_TOKENS = {
    "adaptive",
    "architecture",
    "answer",
    "answers",
    "csse",
    "energy",
    "inference",
    "memory",
    "retrieval",
    "sppe",
    "t1",
    "t2",
    "thinning",
    "transformer",
    "users",
}
PUBLIC_MEMORY_QUERY_TOKENS = {
    "account",
    "applying",
    "blood",
    "business",
    "cash",
    "caught",
    "change",
    "climate",
    "compliance",
    "compound",
    "consumer",
    "current",
    "emergency",
    "evidence",
    "fafsa",
    "financial",
    "health",
    "hypertension",
    "information",
    "interest",
    "message",
    "operational",
    "principal",
    "phishing",
    "pressure",
    "risk",
    "risks",
    "rip",
    "safety",
    "scam",
    "shore",
    "symptoms",
    "tax",
    "temperature",
    "withholding",
    "assumption",
    "assumptions",
}

INTENT_TEMPLATES: dict[str, str] = {
    "FETCH_DOCUMENT": "pull layout document manifest file pdf page download view open retrieve upload attach",
    "SYSTEM_DIAGNOSTIC": "error broken status crash failure bug log deployment timeout diagnostic",
    "WORKSPACE_QUERY": "metrics analysis progress overview stats tracking services dependencies affected happen impact change downstream upstream cause late delay why means meaning title company case study objectives modules scope technologies used tools",
    "CODE_GENERATE": "create build scaffold generate api route function class code implementation",
    "RUN_CANVAS": "analyse analyze deep scan full codebase corpus dataset synthesis everything uploaded",
    "RUN_INVENTION": "invent design novel architecture theorem hypothesis protocol plan new solution",
    "GENERAL_FACT": "what explain define describe capital concept general knowledge means meaning title company case study objectives modules technologies",
    "EMOTIONAL_CATCH": "stressed overwhelmed anxious confused giving up frustrated hard worried help greeting hello hi",
    "META_INQUIRY": "why answer confidence memory trace sources reasoning gaps explain yourself",
}

INTENT_DOMAINS: dict[str, IntentDomain] = {
    "GENERAL_FACT": IntentDomain.GENERAL_KNOWLEDGE,
    "EMOTIONAL_CATCH": IntentDomain.EMOTIONAL_SOCIAL,
    "META_INQUIRY": IntentDomain.META_SYSTEM,
}

TOKEN_RE = re.compile(r"[a-z0-9_+\-.#]+")
CHAR_CONFUSABLES = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
    }
)
QUESTION_TOKENS = {word.lower() for word in QUESTION_WORDS}
CONTROL_TOKENS = {"if"}


def _stem(token: str) -> str:
    if token in STOP_WORDS or token in QUESTION_TOKENS or token in CONTROL_TOKENS:
        return token
    for suffix in ("ing", "ingly", "edly", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def normalize_language(raw: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(raw or ""))
    normalized = normalized.translate(CHAR_CONFUSABLES)
    normalized = re.sub(r"([A-Za-z])\1{2,}", r"\1\1", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def sanitize(raw: str) -> list[str]:
    surface_tokens = canonical_terms(raw, keep_stop=True)
    vocabulary = _semantic_vocabulary()
    tokens = [token for token in surface_tokens if token not in STOP_WORDS and len(token) > 1]
    known_tokens = [token for token in tokens if token in vocabulary]
    if not known_tokens and _looks_like_short_conversation(surface_tokens):
        return ["greet"]
    return tokens


def canonical_terms(raw: str, keep_stop: bool = False) -> list[str]:
    return [
        token
        for token in (_canonical_token(token) for token in _basic_tokens(raw))
        if token and (keep_stop or token not in STOP_WORDS)
    ]


def _basic_tokens(raw: str) -> list[str]:
    normalized = normalize_language(raw).lower()
    return [_stem(match.group(0).strip("._-")) for match in TOKEN_RE.finditer(normalized) if match.group(0).strip("._-")]


def _canonical_token(token: str) -> str:
    if not token:
        return ""
    vocabulary = _semantic_vocabulary()
    if token in vocabulary or len(token) <= 1:
        return token
    collapsed = re.sub(r"([a-z])\1+", r"\1", token)
    if collapsed in vocabulary:
        return collapsed
    best = token
    best_score = 0.0
    for candidate in vocabulary:
        score = _token_similarity(token, candidate)
        if score > best_score:
            best = candidate
            best_score = score
    threshold = 0.84 if len(token) <= 3 else 0.72
    return best if best_score >= threshold else token


def _semantic_vocabulary() -> set[str]:
    raw_terms: set[str] = set(STOP_WORDS) | QUESTION_TOKENS | CONTROL_TOKENS
    raw_terms.update(IMPACT_TOKENS)
    for values in (
        GENERATION_ACTION_TOKENS,
        CODE_CAPABILITY_TOKENS,
        CODE_DESIGN_TOKENS,
        IMAGE_CAPABILITY_TOKENS,
        VIDEO_CAPABILITY_TOKENS,
        AUDIO_CAPABILITY_TOKENS,
        CREATIVE_CAPABILITY_TOKENS,
        AGENTIC_CAPABILITY_TOKENS,
        ARCHITECTURE_TOKENS,
        PUBLIC_MEMORY_QUERY_TOKENS,
    ):
        raw_terms.update(values)
    for template in INTENT_TEMPLATES.values():
        raw_terms.update(_basic_tokens_without_canonicalization(template))
    return {_stem(term.lower()) for term in raw_terms if term}


def _basic_tokens_without_canonicalization(raw: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(raw or "")).translate(CHAR_CONFUSABLES).lower()
    return [_stem(match.group(0).strip("._-")) for match in TOKEN_RE.finditer(normalized) if match.group(0).strip("._-")]


def _token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if len(left) >= 3 and right.startswith(left):
        return 0.86
    if len(right) >= 3 and left.startswith(right):
        return 0.78
    if _consonant_skeleton(left) and _consonant_skeleton(left) == _consonant_skeleton(right):
        return 0.88
    distance = _edit_distance(left, right)
    edit_score = 1.0 - distance / max(len(left), len(right), 1)
    ngram_score = _ngram_jaccard(left, right)
    return max(edit_score, ngram_score)


def _consonant_skeleton(token: str) -> str:
    return re.sub(r"[aeiou]+", "", token)


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for col, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(current[-1] + 1, previous[col] + 1, previous[col - 1] + cost))
        previous = current
    return previous[-1]


def _ngram_jaccard(left: str, right: str, size: int = 2) -> float:
    if len(left) < size or len(right) < size:
        return 0.0
    left_ngrams = {left[index : index + size] for index in range(len(left) - size + 1)}
    right_ngrams = {right[index : index + size] for index in range(len(right) - size + 1)}
    return len(left_ngrams & right_ngrams) / max(len(left_ngrams | right_ngrams), 1)


def _looks_like_short_conversation(surface_tokens: list[str]) -> bool:
    return len(surface_tokens) <= 4 and bool(set(surface_tokens) & QUESTION_TOKENS)


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
        surface_tokens = canonical_terms(raw_input, keep_stop=True)
        surface_set = set(surface_tokens)
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
        impact_surface = bool(surface_set & IMPACT_TOKENS)
        if ("if" in surface_set and impact_surface) or re.search(r"\bwhat\s+(happens?|breaks?|is\s+affected)\s+if\b", raw_lower):
            question_intent = {"kind": "causal_impact", "relation": "causes", "direction": "outgoing"}
        elif "why" in surface_tokens[:3]:
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

    def _v9_capability_override(self, tokens: list[str], raw_input: str) -> tuple[str, float, str] | None:
        token_set = {token.strip(".,:;!?").lower() for token in tokens}
        raw_lower = raw_input.lower()
        has_generation_action = bool(token_set & GENERATION_ACTION_TOKENS)
        if (token_set & CODE_CAPABILITY_TOKENS) and (
            has_generation_action
            or bool(token_set & {"bug", "debug", "refactor", "test", "tests"})
            or bool(token_set & CODE_DESIGN_TOKENS)
        ):
            return "CODE_GENERATE", 0.3, "coding"
        if has_generation_action and token_set & IMAGE_CAPABILITY_TOKENS:
            return "WORKSPACE_QUERY", 0.28, "image_generation"
        if has_generation_action and token_set & VIDEO_CAPABILITY_TOKENS:
            return "WORKSPACE_QUERY", 0.28, "video_generation"
        if has_generation_action and token_set & AUDIO_CAPABILITY_TOKENS:
            return "WORKSPACE_QUERY", 0.28, "audio_generation"
        creative_match = has_generation_action and bool(token_set & CREATIVE_CAPABILITY_TOKENS)
        if creative_match or re.search(r"\b(rewrite|draft|compose)\b", raw_lower):
            return "WORKSPACE_QUERY", 0.24, "creative_text"
        if token_set & AGENTIC_CAPABILITY_TOKENS:
            return "WORKSPACE_QUERY", 0.28, "agentic_task"
        if len(token_set & ARCHITECTURE_TOKENS) >= 2:
            return "WORKSPACE_QUERY", 0.28, "system_architecture"
        if len(token_set & PUBLIC_MEMORY_QUERY_TOKENS) >= 2:
            return "WORKSPACE_QUERY", 0.28, "public_memory"
        return None

    def compile(self, raw_input: str, namespace: str = "TECHNICAL", session: dict[str, Any] | None = None) -> SemanticIR:
        session = session or {}
        normalized_input = normalize_language(raw_input)
        tokens = sanitize(raw_input)
        hypotheses = self.resolve_hypotheses(self.score_intents(tokens))
        primary = hypotheses[0]
        target_ir = primary.target_ir
        confidence = primary.score
        scope = self._scope_from_tokens(tokens, normalized_input)
        raw_lower = normalized_input.lower()
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
        v9_override = self._v9_capability_override(tokens, normalized_input)
        if v9_override:
            target_ir, override_confidence, capability_hint = v9_override
            confidence = max(confidence, override_confidence)
            scope["v9_capability_hint"] = capability_hint
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
