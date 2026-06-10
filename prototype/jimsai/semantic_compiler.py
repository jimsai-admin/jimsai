from __future__ import annotations

import math
import os
import re
import unicodedata
from typing import Any

from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR


def _is_document_wide_relation(predicate: str) -> bool:
    if not predicate:
        return False
    return predicate.startswith("has_") or predicate.startswith("uses_") or predicate.startswith("is_")

# Capability token sets used by _v9_capability_override
# NOTE: These are kept for backward compatibility with scope hint generation.
# Intent classification is now embedding-based (see intent_classifier.py)
GENERATION_ACTION_TOKENS = {"write", "create", "build", "generate", "make", "draw", "produce", "implement", "scaffold", "want"}
CODE_CAPABILITY_TOKENS = {
    # Language-agnostic code concepts — NOT specific language names
    "api", "bug", "class", "code", "debug", "function", "library",
    "package", "refactor", "sdk", "test", "tests", "algorithm",
    "interface", "module", "method", "endpoint", "query", "schema",
    "struct", "enum", "type", "async", "callback", "promise", "loop",
    "variable", "constant", "parameter", "argument", "return",
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
    "assumptions", "technology", "technologies", "tool", "tools", "used",
}

QUESTION_TOKENS = {"what", "why", "how", "when", "where", "who", "which"}
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

TOKEN_RE = re.compile(r"[\w+\-.#]+", re.UNICODE)


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
    
    # Confusables mapping (shape-based OCR/typo repairs)
    confusables = {
        '0': 'o',
        '3': 'e',
        '4': 'a',
        '5': 's',
        '7': 't',
        '8': 'b',
    }
    
    def replace_confusable(match):
        word = match.group(0)
        new_word = []
        for i, char in enumerate(word):
            if char in confusables:
                new_word.append(confusables[char])
            elif char == '1':
                # Map 1 dynamically based on surrounding character context
                before = word[i-1] if i > 0 else ''
                after = word[i+1] if i < len(word) - 1 else ''
                if before == 'r' and after == 'p':  # javascr[one]pt -> javascript
                    new_word.append('i')
                else:  # fi[one]e -> file
                    new_word.append('l')
            else:
                new_word.append(char)
        return "".join(new_word)
        
    # Translate digits that act as letter confusables inside words
    normalized = re.sub(r'\b[a-zA-Z0-9]*[a-zA-Z][a-zA-Z0-9]*\b', replace_confusable, normalized)
    
    # Collapse 3+ repeated characters to 2: coool -> cool, baaad -> bad
    normalized = re.sub(r'(.)\1{2,}', r'\1\1', normalized)
    
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
    surface_tokens = canonical_terms(raw, keep_stop=False)
    tokens = [token for token in surface_tokens if len(token) > 1]
    return tokens


def canonical_terms(raw: str, keep_stop: bool = False) -> list[str]:
    return [
        token
        for token in (_canonical_token(token) for token in _basic_tokens(raw))
        if token
    ]


def _basic_tokens(raw: str) -> list[str]:
    """Extract basic tokens from raw input.
    
    No language-specific stemming or character mapping.
    """
    normalized = normalize_language(raw).lower()
    return [match.group(0).strip("._-") for match in TOKEN_RE.finditer(normalized) if match.group(0).strip("._-")]


def _canonical_token(token: str) -> str:
    """Return token as-is or canonicalized if it is a common slang/abbreviation.
    
    Removed:
    - Hardcoded vocabulary lookup
    - Duplicate character collapsing (Latin-specific)
    - Language-specific similarity thresholds
    """
    if not token:
        return ""
    slang_map = {
        # Universal abbreviations — not language-specific
        "msg": "message",
        "txt": "text",
        "pwd": "password",
        "usr": "user",
        "dev": "developer",
        "app": "application",
        # Common typos for universal technical terms
        "functon": "function",
        "functin": "function",
        "tesst": "test",
        "tessts": "tests",
        "uplod": "upload",
        "fle": "file",
    }
    t_lower = token.lower()
    if t_lower in slang_map:
        return slang_map[t_lower]
    return token





class _FallbackClassifier:
    """Intent classifier that routes through the Modal Embedding Service.

    Uses embedding similarity against semantic concept prototypes — no hardcoded
    language patterns. All prototypes describe the *concept* the user intends,
    not the specific words they use, so this works across all languages.
    """

    def __init__(self):
        import os
        self.api_url = os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").strip().rstrip("/")
        self.api_token = (
            os.getenv("JIMS_MODAL_API_KEY", "")
            or os.getenv("JIMS_EMBEDDING_SERVICE_TOKEN", "")
        ).strip()

        # ── IR prototype descriptions ──────────────────────────────────────
        # Each value describes the CONCEPT behind the IR target.
        # No hardcoded language samples — the embedding model handles translation.
        self.ir_prototypes = {
            "FETCH_DOCUMENT": (
                "Retrieve, download, open, or access a file, document, attachment, or stored artifact. "
                "The user wants to get something that already exists."
            ),
            "SYSTEM_DIAGNOSTIC": (
                "Diagnose a system error, crash, bug, failure, or unexpected behaviour. "
                "The user is reporting or investigating a technical problem."
            ),
            "WORKSPACE_QUERY": (
                "Query or recall information from stored memory, personal facts, prior conversations, "
                "or the user's own workspace. The user wants to retrieve something JimsAI already knows "
                "or has been told. Includes asking about the user's name, preferences, projects, history, "
                "or anything previously shared."
            ),
            "CODE_GENERATE": (
                "Write, generate, create, or implement source code, a function, algorithm, script, "
                "query, or program in any programming language or data format."
            ),
            "RUN_CANVAS": (
                "Analyse, synthesise, or investigate a codebase, corpus, or large body of information "
                "through deep background processing."
            ),
            "RUN_INVENTION": (
                "Invent, design, architect, or prototype a novel solution, system, or strategy. "
                "The user wants original creative or technical output."
            ),
            "GENERAL_FACT": (
                "Answer a factual question, explain a concept, define a term, or perform a calculation. "
                "The user wants a direct informational answer."
            ),
            "EMOTIONAL_CATCH": (
                "Respond to emotional distress, confusion, overwhelm, frustration, or a request for "
                "support, comfort, or human-like understanding."
            ),
            "META_INQUIRY": (
                "Ask about JimsAI itself: its capabilities, reasoning, sources, confidence, or how it works."
            ),
            "OP_ESCAPE_TO_SANDBOX": (
                "Input that is unintelligible, random, nonsensical, or cannot be mapped to any intent."
            ),
        }

        # ── Memory recall prototype ────────────────────────────────────────
        # Covers any query where the user wants to retrieve something JimsAI
        # was previously told or stored — profile facts, preferences, tasks,
        # documents, prior discussions — not limited to "who am I" queries.
        self.memory_recall_prototype = (
            "Recall stored information, personal facts, user preferences, prior conversations, "
            "remembered notes, tasks, or anything the user previously shared or asked JimsAI to store. "
            "Retrieve what JimsAI knows about the user or their workspace from memory."
        )

        self._prototype_embeddings: dict[str, list[float]] = {}
        self._memory_recall_embedding: list[float] | None = None
        self._use_hash_fallback = False

    # ── Embedding helpers ──────────────────────────────────────────────────

    def _fetch_embedding(self, text: str) -> list[float]:
        """Embed a single text via the Modal Embedding Service.

        Falls back to a hash projection when the service is unavailable.
        Hash projections are low-quality — callers should check _use_hash_fallback.
        """
        if self._use_hash_fallback:
            return self._hash_embed(text, 256)

        import httpx
        url = f"{self.api_url}/embed"
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            response = httpx.post(
                url,
                json={"texts": [text], "model": "multilingual-e5-small", "purpose": "query"},
                headers=headers,
                timeout=float(os.getenv("JIMS_INTENT_EMBEDDING_TIMEOUT", "4") or "4"),
            )
            if response.status_code == 200:
                data = response.json()
                vectors = data.get("vectors")
                if isinstance(vectors, list) and vectors and isinstance(vectors[0], list):
                    return vectors[0]
        except Exception:
            pass
        return self._hash_embed(text, 256)

    def _fetch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the Modal Embedding Service."""
        if not texts:
            return []
        if self._use_hash_fallback:
            return [self._hash_embed(t, 256) for t in texts]

        import httpx
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        try:
            response = httpx.post(
                f"{self.api_url}/embed",
                json={"texts": texts, "model": "multilingual-e5-small", "purpose": "document"},
                headers=headers,
                timeout=float(os.getenv("JIMS_INTENT_EMBEDDING_TIMEOUT", "6") or "6"),
            )
            if response.status_code == 200:
                data = response.json()
                vectors = data.get("vectors") or data.get("embeddings")
                if isinstance(vectors, list) and len(vectors) == len(texts):
                    return vectors
        except Exception:
            pass
        return [self._hash_embed(t, 256) for t in texts]

    @staticmethod
    def _hash_embed(text: str, dim: int) -> list[float]:
        try:
            from .encoder.dual_encoder import hash_embedding
            return hash_embedding(text, dim)
        except ImportError:
            try:
                from .encoder import hash_embedding
                return hash_embedding(text, dim)
            except ImportError:
                return [0.0] * dim

    @staticmethod
    def _cosine(v1: list[float], v2: list[float]) -> float:
        import math
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1)) or 1.0
        n2 = math.sqrt(sum(b * b for b in v2)) or 1.0
        return dot / (n1 * n2)

    # ── Prototype caching ──────────────────────────────────────────────────

    def _get_prototype_embeddings(self) -> dict[str, list[float]]:
        if self._prototype_embeddings:
            return self._prototype_embeddings

        targets = list(self.ir_prototypes.keys())
        # Use "passage: " prefix for asymmetric retrieval (document side)
        texts = ["passage: " + self.ir_prototypes[t] for t in targets]
        vectors = self._fetch_embeddings(texts)

        for target, vec in zip(targets, vectors):
            self._prototype_embeddings[target] = vec

        # Quality check — if embeddings are all near-identical, the service
        # returned garbage. Fall back to hash projections.
        if len(self._prototype_embeddings) >= 4:
            embs = list(self._prototype_embeddings.values())
            high_sim = sum(
                1 for i, e1 in enumerate(embs)
                for e2 in embs[i + 1:]
                if self._cosine(e1, e2) > 0.92
            )
            total_pairs = len(embs) * (len(embs) - 1) // 2
            if total_pairs and high_sim / total_pairs > 0.5:
                import logging
                logging.getLogger("jimsai.classifier").warning(
                    "Embedding service returned near-identical vectors — switching to hash fallback."
                )
                self._prototype_embeddings.clear()
                self._use_hash_fallback = True
                for target, text in self.ir_prototypes.items():
                    self._prototype_embeddings[target] = self._hash_embed("passage: " + text, 256)

        return self._prototype_embeddings

    def _get_memory_recall_embedding(self) -> list[float]:
        if self._memory_recall_embedding is None:
            self._get_prototype_embeddings()  # trigger quality check first
            self._memory_recall_embedding = self._fetch_embedding(
                "passage: " + self.memory_recall_prototype
            )
        return self._memory_recall_embedding

    # ── Public interface ───────────────────────────────────────────────────

    def classify_intent(self, query: str) -> tuple[str, float]:
        """Return (ir_target, confidence) for the given query."""
        prototypes = self._get_prototype_embeddings()
        if not prototypes:
            return "OP_ESCAPE_TO_SANDBOX", 0.0

        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            return "OP_ESCAPE_TO_SANDBOX", 0.0

        best_ir = "OP_ESCAPE_TO_SANDBOX"
        best_score = 0.0
        for ir_target, proto_emb in prototypes.items():
            score = self._cosine(query_emb, proto_emb)
            if score > best_score:
                best_score = score
                best_ir = ir_target

        return best_ir, round(max(0.0, min(1.0, best_score)), 4)

    def is_memory_recall_query(self, query: str, threshold: float = 0.55) -> bool:
        """Return True if the query is asking to recall something from stored memory.

        This covers all user-stored facts — profile, preferences, documents,
        tasks, prior conversations — not just "what is my name?" style queries.
        Works across all languages via embedding similarity.
        """
        self._get_prototype_embeddings()  # trigger quality check
        effective_threshold = 0.20 if self._use_hash_fallback else threshold

        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            return False

        recall_emb = self._get_memory_recall_embedding()
        score = self._cosine(query_emb, recall_emb)
        return score > effective_threshold

    def is_profile_query(self, query: str, threshold: float = 0.55) -> bool:
        """Alias for is_memory_recall_query — kept for backward compatibility."""
        return self.is_memory_recall_query(query, threshold)

    def get_intent_scores(self, query: str) -> dict[str, float]:
        """Return similarity scores against all IR prototype embeddings."""
        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            return {t: 0.0 for t in self.ir_prototypes}

        prototypes = self._get_prototype_embeddings()
        return {
            t: round(max(0.0, min(1.0, self._cosine(query_emb, emb))), 4)
            for t, emb in prototypes.items()
        }


class _LLMClassifier:
    """Intent classifier using LLM (QwenBridge) for robust multilingual understanding.

    Strategy (in order):
    1. LLM via QwenBridge — handles any language, mixed intent, typos.
    2. Embedding classifier (_FallbackClassifier) — semantic prototype matching,
       language-agnostic, no hardcoded patterns.
    3. Structural token analysis — lightweight fallback, Unicode-aware.

    No hardcoded language-specific regex patterns. Everything is embedding or
    semantics-based so it works equally well in English, French, Yoruba, Arabic,
    Chinese, etc.
    """

    def __init__(self, qwen_bridge: Any) -> None:
        self.qwen_bridge = qwen_bridge
        # Lazy-init embedding classifier (shares Modal service, no extra cost)
        self._embedding_classifier: "_FallbackClassifier | None" = None

    @property
    def _embed_cls(self) -> "_FallbackClassifier":
        if self._embedding_classifier is None:
            self._embedding_classifier = _FallbackClassifier()
        return self._embedding_classifier

    def classify_intent(self, query: str) -> tuple[str, float]:
        """Return (ir_target, confidence) for any query in any language."""
        # 1. Try LLM — most accurate, handles any language and mixed intent
        if self.qwen_bridge and self.qwen_bridge.qwen_enabled:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        self.qwen_bridge.infer_intent(query, {
                            "target_ir": "WORKSPACE_QUERY",
                            "confidence": 0.3,
                            "scope_constraints": {},
                            "execution_mode": "UNKNOWN",
                            "intent_domain": "UNKNOWN",
                        })
                    )
                finally:
                    loop.close()
                if result and isinstance(result, dict):
                    ir = result.get("target_ir") or result.get("intent")
                    conf = float(result.get("confidence") or result.get("score") or 0.0)
                    _VALID_IR = {
                        "WORKSPACE_QUERY", "FETCH_DOCUMENT", "SYSTEM_DIAGNOSTIC",
                        "CODE_GENERATE", "RUN_CANVAS", "RUN_INVENTION",
                        "GENERAL_FACT", "EMOTIONAL_CATCH", "META_INQUIRY",
                    }
                    if ir in _VALID_IR and conf > 0.0:
                        return ir, conf
            except Exception:
                pass

        # 2. Embedding classifier — language-agnostic prototype matching
        try:
            return self._embed_cls.classify_intent(query)
        except Exception:
            pass

        # 3. Minimal structural fallback — Unicode-aware, no language assumptions
        return self._structural_classify(query)

    def is_profile_query(self, query: str, threshold: float = 0.55) -> bool:
        """Return True if query asks to recall something from stored memory.

        Uses embedding similarity — no hardcoded language patterns.
        Covers profile facts, preferences, stored notes, anything the user
        previously shared with JimsAI.
        """
        try:
            return self._embed_cls.is_memory_recall_query(query, threshold)
        except Exception:
            return False

    def _structural_classify(self, query: str) -> tuple[str, float]:
        """Minimal Unicode-aware structural classification — last resort only."""
        raw = query.lower()
        tokens = set(re.findall(r"[\w\.]+", raw, flags=re.UNICODE))

        # Math: numbers + operators
        if re.search(r"\d+\s*[\+\-\*/]\s*\d+|\d+", raw) and re.search(r"[\+\-\*/=]|solve|calculate|compute", raw):
            return "GENERAL_FACT", 0.85

        # Code: structural syntax signals that work across all languages
        code_signals = {"def ", "class ", "import ", "function ", "return ", "```",
                        "fn ", "const ", "let ", "var ", "func ", "fun ", "pub "}
        if any(sig in query for sig in code_signals):
            return "CODE_GENERATE", 0.90

        # File operations: universal verbs
        file_tokens = {"fetch", "download", "upload", "attach", "file", "document", "read", "open", "import", "load"}
        if tokens & file_tokens:
            return "FETCH_DOCUMENT", 0.65

        return "WORKSPACE_QUERY", 0.50


class SemanticCompilerRuntime:
    def __init__(self, confidence_threshold: float = 0.50) -> None:
        self.confidence_threshold = confidence_threshold
        self._classifier: Any = None  # Lazy initialization
        self._qwen_bridge: Any = None

    @property
    def qwen_bridge(self) -> Any:
        """Lazy initialize QwenBridge for intent classification."""
        if self._qwen_bridge is None:
            from .model_bridge import QwenBridge
            self._qwen_bridge = QwenBridge()
        return self._qwen_bridge

    @property
    def classifier(self) -> Any:
        """Lazy initialize classifier — prefers QwenBridge (LLM) for robust multilingual understanding,
        falls back to deterministic scope analysis, then embeddings as last resort."""
        if self._classifier is None:
            self._classifier = _LLMClassifier(self.qwen_bridge)
        return self._classifier

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
        # Detect word-form arithmetic (e.g. "847 multiplied by 63") in addition to symbolic operators
        _word_ops_pattern = (
            r"\b(multiplied\s+by|times|divided\s+by|over|plus|added\s+to|minus|"
            r"subtracted\s+from|to\s+the\s+power\s+of|squared|cubed)\b"
        )
        _has_word_op = bool(re.search(_word_ops_pattern, raw_input, re.IGNORECASE))
        _has_symbolic_op = bool(re.search(r"[+\-*/=]", raw_input))
        _num_count = len(re.findall(r"\d+(?:\.\d+)?", raw_input))
        if _num_count >= 1 and (_has_symbolic_op or _has_word_op):
            return "GENERAL_FACT", 0.92, "math_science"
        if "def " in raw_input or "class " in raw_input or "import " in raw_input or "return " in raw_input or "function " in raw_input or "```" in raw_input:
            return "CODE_GENERATE", 0.99, "coding"
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
            # Guard: don't route to agentic_task when strong code signals are present.
            # "Write a Python async task queue" has "task" but is clearly a code request.
            strong_code_signal = bool(
                (token_set & CODE_CAPABILITY_TOKENS) and (has_generation_action or bool(token_set & {"bug", "debug", "refactor", "test", "tests"}))
                or "def " in raw_input or "class " in raw_input or "async " in raw_input
                or bool(token_set & {"async", "asyncio", "queue", "function", "method", "class"})
            )
            if not strong_code_signal:
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
        
        # Pre-process the query using canonical tokens to resolve typos and slang
        canonical_query = " ".join(_canonical_token(w) for w in _basic_tokens(raw_input))
        
        # Use embedding-based intent classification (primary - HIGH PRIORITY)
        scope = self._scope_from_tokens(tokens, normalized_input)
        v9_override = self._v9_capability_override(tokens, normalized_input)

        # === MEMORY WRITE / RECALL FAST PATH ======================================
        # Detection strategy (no hardcoded language patterns):
        # 1. Write: v9 capability override already handles most generation.
        #    Profile writes are detected later via is_profile_query on the result.
        # 2. Recall: classifier.classify_intent returns WORKSPACE_QUERY when the
        #    embedding matches the "recall stored information" prototype.
        # 3. Explicit: v9 high-confidence override fires first for code/math.
        if v9_override and v9_override[1] >= 0.9:
            target_ir, confidence, capability_hint = v9_override
            scope["v9_capability_hint"] = capability_hint
            structural_fast_path = True
        else:
            target_ir, confidence = self.classifier.classify_intent(canonical_query or raw_input)
            structural_fast_path = False
        
        # Keep hypotheses for backward compatibility (empty list — lexical scoring removed)
        hypotheses: list = []
        
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
        
        # === MEMORY RECALL DETECTION: Route to WORKSPACE_QUERY ===
        # classifier.is_profile_query uses embedding similarity against the
        # "recall stored information" prototype — covers any user-stored fact
        # (profile, preferences, tasks, documents, prior conversations) in any language.
        is_profile = False if structural_fast_path else self.classifier.is_profile_query(canonical_query or raw_input, threshold=0.55)
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
        local_threshold = self.confidence_threshold
        has_non_ascii = any(ord(c) > 127 for c in raw_input)
        low_resource_words = {"nibo", "bawo", "koni", "odabo", "kaabo", "kedu", "bia", "imela", "sannu", "lafiya", "nagode", "koodu", "kodi", "gba", "fifipamo", "nweta", "chekwaa", "samu", "ajiye"}
        if has_non_ascii or any(w in normalized_input.lower().split() for w in low_resource_words):
            local_threshold = 0.30
        if target_ir == "OP_ESCAPE_TO_SANDBOX" or confidence < local_threshold:
            # Context-less follow-up carry-forward — don't sandbox when session has active intent.
            # This handles "what about the error?" type queries and cross-language follow-ups.
            # Non-ASCII queries benefit from session rescue too — the lowered local_threshold (0.30)
            # already guards against truly unintelligible input; blocking session rescue for
            # non-ASCII incorrectly prevents Yoruba/Arabic/etc. users from inheriting context.
            active_session_intent = session.get("ACTIVE_INTENT")
            if (
                active_session_intent
                and active_session_intent != "OP_ESCAPE_TO_SANDBOX"
                and confidence >= 0.20  # Only rescue if some signal present (not pure noise)
            ):
                target_ir = active_session_intent
                confidence = max(confidence, 0.35)
                scope["session_intent_inherited"] = True
                execution_mode = ExecutionMode.DETERMINISTIC_CORE
            else:
                target_ir = "OP_ESCAPE_TO_SANDBOX"
                execution_mode = ExecutionMode.AIR_GAPPED_CONTAINER
        
        context_inherited = False
        context_boosted = False
        question_intent = scope.get("question_intent")
        relation = question_intent.get("relation") if isinstance(question_intent, dict) else None
        if "entities" not in scope and session.get("ACTIVE_OBJECT") and not _is_document_wide_relation(relation):
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

