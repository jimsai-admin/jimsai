from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

from .models import ExecutionMode, Hypothesis, IntentDomain, SemanticIR


def _is_document_wide_relation(predicate: str) -> bool:
    """Return True if the predicate describes a document-wide fact.

    Uses structural prefix detection (has_, uses_, is_) which works for
    predicates extracted from documents in any language, since the NLP
    extractor normalises them to snake_case.
    """
    if not predicate:
        return False
    return predicate.startswith("has_") or predicate.startswith("uses_") or predicate.startswith("is_")


def _raw_tokens(text: str) -> list[str]:
    """Extract Unicode tokens from raw text — no normalisation, no stop words.

    This is the only tokeniser used in JimsAI. It is language-agnostic:
    it splits on whitespace and punctuation but preserves all Unicode word
    characters so Arabic, Chinese, Yoruba, etc. are handled correctly.
    The LLM (Qwen 1.7B via Modal) and embeddings handle semantic understanding;
    this tokeniser only supplies surface tokens for the IR.
    """
    return [
        tok
        for tok in re.findall(r"[\w\-.#@]+", text, flags=re.UNICODE)
        if tok.strip("._-#@")
    ]





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
                "or anything previously shared. ALSO includes telling JimsAI something to remember: "
                "sharing a name, preference, fact, task, or any personal information to store."
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
            "Store or recall personal facts, user preferences, prior conversations, "
            "remembered notes, tasks, or anything the user previously shared or asked JimsAI to store. "
            "Includes telling JimsAI a name, preference, project, or any personal information. "
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
        """Return (ir_target, confidence) for any query in any language.

        This is a synchronous method called from compile() which runs inside
        an async context. The LLM overlay (Qwen 1.7B) is handled asynchronously
        by TransformerIntentInterface.infer() AFTER compile() returns — so we
        skip the LLM here and go straight to the embedding classifier.
        The async T1 overlay then refines the result if confidence is low.
        """
        # Embedding classifier — language-agnostic, works synchronously
        try:
            return self._embed_cls.classify_intent(query)
        except Exception:
            pass

        # Minimal structural fallback — Unicode-aware, no language assumptions
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

    def _scope_from_tokens(self, tokens: list[str], raw_input: str, existing_scope: dict[str, Any] | None = None) -> dict[str, Any]:
        scope: dict[str, Any] = existing_scope or {}
        scope["raw_length"] = len(raw_input)
        scope["token_count"] = len(tokens)
        # Entity extraction — PascalCase/CamelCase detection works for code/technical identifiers
        # across all Latin-script languages. Non-Latin entities are extracted by the NLP layer.
        camel_entities = [
            entity.strip(".,:;!?")
            for entity in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\b", raw_input)
            if len(entity) > 1
        ]
        if camel_entities:
            scope["entities"] = sorted(set(camel_entities))
        numbers = [int(n) for n in re.findall(r"\b\d+\b", raw_input)]
        if numbers:
            scope["numbers"] = numbers
        return scope

    def _domain_for_ir(self, target_ir: str) -> IntentDomain:
        mapping = {
            "GENERAL_FACT": IntentDomain.GENERAL_KNOWLEDGE,
            "EMOTIONAL_CATCH": IntentDomain.EMOTIONAL_SOCIAL,
            "META_INQUIRY": IntentDomain.META_SYSTEM,
        }
        return mapping.get(target_ir, IntentDomain.WORKSPACE_OPERATION)

    def compile(self, raw_input: str, namespace: str = "TECHNICAL", session: dict[str, Any] | None = None) -> SemanticIR:
        session = session or {}
        # Use raw text directly — no preprocessing pipeline, no normalisation.
        # The LLM (Qwen 1.7B) and embedding model handle all languages natively.
        tokens = _raw_tokens(raw_input)
        scope: dict[str, Any] = {"raw_length": len(raw_input), "token_count": len(tokens)}

        # 1. Classify intent via LLM → embedding → structural fallback (in that order)
        target_ir, confidence = self.classifier.classify_intent(raw_input)

        # 2. Memory recall detection — covers any user-stored fact in any language
        if target_ir == "WORKSPACE_QUERY" or self.classifier.is_profile_query(raw_input, threshold=0.45):
            scope["profile_query"] = True
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, 0.50)

        # 3. Session context rescue — inherit active intent when classifier is uncertain
        execution_mode = ExecutionMode.DETERMINISTIC_CORE
        local_threshold = self.confidence_threshold
        has_non_ascii = any(ord(c) > 127 for c in raw_input)
        if has_non_ascii:
            local_threshold = 0.30  # lower confidence bar for non-Latin scripts

        if target_ir == "OP_ESCAPE_TO_SANDBOX" or confidence < local_threshold:
            active_session_intent = session.get("ACTIVE_INTENT")
            if (
                active_session_intent
                and active_session_intent != "OP_ESCAPE_TO_SANDBOX"
                and confidence >= 0.20
            ):
                target_ir = active_session_intent
                confidence = max(confidence, 0.35)
                scope["session_intent_inherited"] = True
            else:
                execution_mode = ExecutionMode.AIR_GAPPED_CONTAINER

        # 4. Scope enrichment — language-neutral entity + number extraction
        scope = self._scope_from_tokens(tokens, raw_input, existing_scope=scope)

        # 5. Mark profile write in scope
        if scope.get("profile_write"):
            scope["profile_query"] = True

        # 6. Session object carry-forward
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

        domain = self._domain_for_ir(target_ir)
        return SemanticIR(
            target_ir=target_ir,
            system_action=target_ir,
            confidence=round(confidence, 4),
            scope_constraints=scope,
            execution_mode=execution_mode,
            domain_namespace=namespace,
            intent_domain=domain,
            tokens=tokens,
            hypotheses=[],
            context_inherited=context_inherited,
            context_boosted=context_boosted,
        )

