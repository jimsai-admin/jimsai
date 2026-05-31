from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Any

from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR
from .intent_classifier import get_classifier


# Language-universal document relations (not language-specific)
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

# Capability token sets used by _v9_capability_override
# NOTE: These are kept for backward compatibility with scope hint generation.
# Intent classification is now embedding-based (see intent_classifier.py)
GENERATION_ACTION_TOKENS = {"write", "create", "build", "generate", "make", "draw", "produce", "implement", "scaffold", "want"}
CODE_CAPABILITY_TOKENS = {
    "api", "bug", "class", "code", "debug", "fastapi", "function", "javascript",
    "library", "package", "python", "react", "refactor", "sdk", "test", "tests", "typescript",
}
CODE_DESIGN_TOKENS = {"calls", "consideration", "considerations", "design", "external", "fetch", "http", "safe", "security", "service"}
IMAGE_CAPABILITY_TOKENS = {"image", "picture", "photo", "logo", "poster", "illustration", "dashboard"}
VIDEO_CAPABILITY_TOKENS = {"video", "animation", "clip", "movie", "storyboard"}
AUDIO_CAPABILITY_TOKENS = {"audio", "voice", "speech", "tts", "sound", "music"}
CREATIVE_CAPABILITY_TOKENS = {"story", "poem", "script", "rewrite", "tone", "email", "proposal", "copy"}
AGENTIC_CAPABILITY_TOKENS = {
    "agent", "automate", "automat", "book", "browser", "click", "deploy", "deployment",
    "rollback", "schedule", "send", "task",
}
ARCHITECTURE_TOKENS = {
    "adaptive", "architecture", "answer", "answers", "csse", "energy", "inference",
    "memory", "retrieval", "sppe", "t1", "t2", "thinning", "transformer", "users",
}
PUBLIC_MEMORY_QUERY_TOKENS = {
    "account", "applying", "blood", "business", "cash", "caught", "change", "climate",
    "compliance", "compound", "consumer", "current", "emergency", "evidence", "fafsa",
    "financial", "health", "hypertension", "information", "interest", "message",
    "operational", "principal", "phishing", "pressure", "risk", "risks", "rip", "safety",
    "scam", "shore", "symptoms", "tax", "temperature", "withholding", "assumption",
    "assumptions",
}

# Token sets no longer used for intent classification (moved to embeddings)
# Kept for reference only
STOP_WORDS = {
    "a", "an", "the", "yo", "please", "just", "over", "that", "we", "back", "in", "for",
    "to", "of", "and", "or", "on", "with", "can", "you", "i", "me", "my", "is", "are",
    "do", "does", "did", "would", "become", "what", "why", "how", "when", "where", "who", "which",
    "should", "someone",
}
QUESTION_TOKENS = {"what", "why", "how", "when", "where", "who", "which"}
CONTROL_TOKENS = {"if"}
IMPACT_TOKENS = {
    "affect", "impact", "chang", "change", "happen", "break", "depend", "downstream",
    "upstream", "cause", "caus", "late", "delay", "fail", "failure", "slowdown", "occur",
    "block", "blocked",
}

INTENT_DOMAINS: dict[str, IntentDomain] = {
    "GENERAL_FACT": IntentDomain.GENERAL_KNOWLEDGE,
    "EMOTIONAL_CATCH": IntentDomain.EMOTIONAL_SOCIAL,
    "META_INQUIRY": IntentDomain.META_SYSTEM,
}

TOKEN_RE = re.compile(r"[a-z0-9_+\-.#]+")


def _stem(token: str) -> str:
    """Return token unchanged - no language-specific stemming.
    
    Removed English-specific suffix stripping (ing, ed, s, etc.)
    to support all languages universally.
    """
    return token


def normalize_language(raw: str) -> str:
    """Normalize language input for analysis.
    
    Handles:
    - Unicode NFKC normalization (universal)
    - Character confusables (OCR/typo fixes: 0→o, 1→l, 3→e, 4→a, 5→s, 7→t, 8→b)
    - Duplicate character collapsing (coool→cool)
    - Whitespace normalization
    
    These are shape-based fixes (not language-specific or English-centric).
    Intent classification moved to embedding-based system (intent_classifier.py).
    """
    # Unicode normalization
    normalized = unicodedata.normalize("NFKC", str(raw or ""))
    
    # Fix common OCR/typing confusables (shape-based, not language-specific)
    char_map = str.maketrans("01345678", "oleasytb")
    normalized = normalized.translate(char_map)
    
    # Collapse 3+ repeated characters to 2: coool→cool, baaad→bad
    normalized = re.sub(r"(.)\1{2,}", r"\1\1", normalized)
    
    # Normalize whitespace
    return re.sub(r"\s+", " ", normalized).strip()


def sanitize(raw: str) -> list[str]:
    """Extract meaningful tokens from raw input.
    
    Filters out:
    - Stop words (noise reduction)
    - Very short tokens (< 2 chars)
    - Language-independent noise
    
    Note: Intent classification is now embedding-based (intent_classifier.py),
    not token-based, so this is just for data cleaning.
    """
    surface_tokens = canonical_terms(raw, keep_stop=False)  # Apply stop word filter
    tokens = [token for token in surface_tokens if len(token) > 1]
    return tokens


def canonical_terms(raw: str, keep_stop: bool = False) -> list[str]:
    return [
        token
        for token in (_canonical_token(token) for token in _basic_tokens(raw))
        if token and (keep_stop or token not in STOP_WORDS)
    ]


def _basic_tokens(raw: str) -> list[str]:
    """Extract basic tokens from raw input.
    
    No language-specific stemming or character mapping.
    """
    normalized = normalize_language(raw).lower()
    return [match.group(0).strip("._-") for match in TOKEN_RE.finditer(normalized) if match.group(0).strip("._-")]


def _canonical_token(token: str) -> str:
    """Return token as-is - no language-specific canonicalization.
    
    Removed:
    - Hardcoded vocabulary lookup
    - Duplicate character collapsing (Latin-specific)
    - Language-specific similarity thresholds
    """
    return token if token else ""


def _semantic_vocabulary() -> set[str]:
    """Return empty set - vocabulary is now learned from embeddings.
    
    Kept for backward compatibility with existing code.
    """
    return set()



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
    def __init__(self, confidence_threshold: float = 0.50) -> None:
        self.confidence_threshold = confidence_threshold
        self._classifier: Any = None  # Lazy initialization
        # Template vectors kept for backward compatibility in score_intents
        # Maps intent names to token frequency vectors for lexical scoring
        self.template_vectors: dict[str, Counter[str]] = {
            "FETCH_DOCUMENT": _vectorize(["document", "file", "download", "upload", "attachment"]),
            "SYSTEM_DIAGNOSTIC": _vectorize(["error", "bug", "crash", "failure", "log", "issue"]),
            "WORKSPACE_QUERY": _vectorize(["query", "workspace", "information", "analytics"]),
            "CODE_GENERATE": _vectorize(["code", "function", "api", "python", "javascript"]),
            "RUN_CANVAS": _vectorize(["analyze", "codebase", "synthesis", "full"]),
            "RUN_INVENTION": _vectorize(["invent", "design", "create", "novel", "architecture"]),
            "GENERAL_FACT": _vectorize(["explain", "define", "what", "concept"]),
            "EMOTIONAL_CATCH": _vectorize(["help", "support", "stressed", "overwhelmed"]),
            "META_INQUIRY": _vectorize(["meta", "system", "about", "yourself"]),
            "OP_ESCAPE_TO_SANDBOX": _vectorize(["unknown", "sandbox", "escape"]),
        }

    @property
    def classifier(self) -> Any:
        """Lazy initialize classifier on first access."""
        if self._classifier is None:
            self._classifier = get_classifier()
        return self._classifier

    def score_intents(self, tokens: list[str]) -> list[Hypothesis]:
        """Score intents using lexical method (kept for backward compatibility).
        
        The compile() method now uses embedding-based classification.
        This is kept for tests and legacy code.
        """
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
            if entity.lower() not in QUESTION_TOKENS
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
        # Profile query detection moved to embedding-based check in compile() method
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
        
        # Use embedding-based intent classification (primary - HIGH PRIORITY)
        target_ir, confidence = self.classifier.classify_intent(raw_input)
        
        # Keep hypotheses for backward compatibility (use lexical scoring)
        hypotheses = self.resolve_hypotheses(self.score_intents(tokens))
        
        scope = self._scope_from_tokens(tokens, normalized_input)
        raw_lower = normalized_input.lower()
        causal_question = raw_lower.startswith("why ") and scope.get("entities")
        
        # === HEURISTIC OVERRIDES: Only when embedding confidence is LOW (<0.65) ===
        if confidence < 0.65:
            # Apply question intent override only for very specific causal patterns
            if scope.get("question_intent") and causal_question:
                target_ir = "WORKSPACE_QUERY"
                confidence = max(confidence, 0.24)
            
            # Apply impact token override only if entities are present
            if scope.get("entities") and ((set(tokens) & IMPACT_TOKENS) or causal_question):
                target_ir = "WORKSPACE_QUERY"
                confidence = max(confidence, 0.22)
        
        # === PROFILE QUERY DETECTION: Always route to WORKSPACE_QUERY ===
        is_profile = self.classifier.is_profile_query(raw_input, threshold=0.85)
        if is_profile:
            scope["profile_query"] = True
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, 0.24)
        
        
        # === V9_CAPABILITY_OVERRIDE: Only if specific v9 capabilities detected ===
        v9_override = self._v9_capability_override(tokens, normalized_input)
        if v9_override:
            target_ir, override_confidence, capability_hint = v9_override
            confidence = max(confidence, override_confidence)
            scope["v9_capability_hint"] = capability_hint
        elif target_ir == "CODE_GENERATE":
            # If embedding classifier identified code generation (even if v9 override didn't),
            # still set the capability hint for test compatibility
            scope["v9_capability_hint"] = "coding"
        
        # === SANDBOX FALLBACK: Low confidence or explicit OP_ESCAPE ===
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
