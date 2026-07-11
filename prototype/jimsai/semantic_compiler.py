from __future__ import annotations

import os
import re
from typing import Any

from .errors import CriticalServiceUnavailable
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


def _looks_like_structural_identifier(value: str) -> bool:
    """Return True for code-like identifiers without language word lists."""
    cleaned = value.strip(".,:;!?")
    if len(cleaned) <= 1:
        return False
    return (
        "." in cleaned
        or "_" in cleaned
        or "#" in cleaned
        or "@" in cleaned
        or any(ch.isdigit() for ch in cleaned)
        # An internal capital marks a code identifier only in MIXED case
        # ("TensorDB", "NoxliDB", "iPhone"). All-caps ("DATABASE", "SUDO",
        # "PERVIOUS") is emphasis/shouting, not a name — treating it as a scoped
        # entity let a shouted COMMON word satisfy the entity-scope gate against
        # an unrelated fact and voice it (an adversarial-fuzz fabrication: "what
        # DATABASE does <untaught> use" answered with another project's DB).
        # Genuine unknown all-caps nonces are still caught via the CLL
        # name-evidence path; only known/common all-caps words are excluded here.
        or (any(ch.isupper() for ch in cleaned[1:]) and any(ch.islower() for ch in cleaned))
    )





def _cf_embed_enabled() -> bool:
    return os.getenv("JIMS_EMBEDDING_PROVIDER", "").strip().lower() == "cloudflare"


def _cf_embed_texts(texts: list[str]) -> list[list[float]]:
    """Cloudflare Workers AI embeddings (@cf/baai/bge-base-en-v1.5, 768-d), sync.

    De-Modal replacement for the intent classifier's embedding calls: an embedding
    endpoint on a provider already in use, no Modal, no generative model. Returns []
    on failure so callers degrade gracefully (never raise -> never 500)."""
    import os as _os
    import httpx

    account = _os.getenv("CF_ACCOUNT_ID")
    token = _os.getenv("CF_VECTORIZE_API_TOKEN") or _os.getenv("CF_TOKEN")
    if not (account and token) or not texts:
        return []
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/baai/bge-base-en-v1.5"
    try:
        r = httpx.post(
            url,
            json={"text": texts},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=float(_os.getenv("JIMS_INTENT_EMBEDDING_TIMEOUT", "8") or "8"),
        )
        if r.status_code == 200:
            data = (r.json().get("result") or {}).get("data")
            if isinstance(data, list) and len(data) == len(texts):
                return data
    except Exception:
        pass
    return []


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

    # ── Embedding helpers ──────────────────────────────────────────────────

    def _fetch_embedding(self, text: str) -> list[float]:
        """Embed a single text via the Modal Embedding Service.

        Real embeddings only: failures return [] so semantic routing is skipped
        until the real embedding service recovers.
        """
        if _cf_embed_enabled():
            vecs = _cf_embed_texts([text])
            return vecs[0] if vecs else []
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
        return []

    def _fetch_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the Modal Embedding Service."""
        if not texts:
            return []
        if _cf_embed_enabled():
            return _cf_embed_texts(texts)
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
        return []

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
        if len(vectors) != len(texts):
            return self._prototype_embeddings

        for target, vec in zip(targets, vectors):
            if vec and any(value != 0.0 for value in vec):
                self._prototype_embeddings[target] = vec

        # Quality check: if embeddings are all near-identical, disable semantic
        # prototype routing until real embeddings recover.
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
                    "Embedding service returned near-identical vectors; disabling semantic prototype routing until real embeddings recover."
                )
                self._prototype_embeddings.clear()

        return self._prototype_embeddings

    def _get_memory_recall_embedding(self) -> list[float]:
        if self._memory_recall_embedding is None:
            self._get_prototype_embeddings()  # trigger quality check first
            vector = self._fetch_embedding(
                "passage: " + self.memory_recall_prototype
            )
            if vector and any(value != 0.0 for value in vector):
                self._memory_recall_embedding = vector
            else:
                return []
        return self._memory_recall_embedding

    # Public interface

    def classify_intent(self, query: str) -> tuple[str, float]:
        """Return (ir_target, confidence) from real embedding semantics only."""
        prototypes = self._get_prototype_embeddings()
        if not prototypes:
            # De-LLM fail-safe: an unreachable embedding provider must NEVER 500 a
            # query. Default to workspace/memory recall (low confidence); the CLL
            # concept index, retrieval, and memory-first routing still answer or emit
            # an honest gap.
            return "WORKSPACE_QUERY", 0.30

        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            return "WORKSPACE_QUERY", 0.30

        best_ir = "OP_ESCAPE_TO_SANDBOX"
        best_score = 0.0
        for ir_target, proto_emb in prototypes.items():
            score = self._cosine(query_emb, proto_emb)
            if score > best_score:
                best_score = score
                best_ir = ir_target

        return best_ir, round(max(0.0, min(1.0, best_score)), 4)

    def is_memory_recall_query(self, query: str, threshold: float = 0.55) -> bool:
        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            return False  # embeddings unavailable -> can't confirm; downstream still handles

        recall_emb = self._get_memory_recall_embedding()
        if not recall_emb:
            raise CriticalServiceUnavailable("memory recall prototype embedding unavailable")
        return self._cosine(query_emb, recall_emb) > threshold

    def is_profile_query(self, query: str, threshold: float = 0.55) -> bool:
        return self.is_memory_recall_query(query, threshold)

    def get_intent_scores(self, query: str) -> dict[str, float]:
        query_emb = self._fetch_embedding("query: " + query)
        if not query_emb or all(v == 0.0 for v in query_emb):
            raise CriticalServiceUnavailable("intent query embedding unavailable")

        prototypes = self._get_prototype_embeddings()
        if not prototypes:
            raise CriticalServiceUnavailable("intent embedding prototypes unavailable")
        return {
            t: round(max(0.0, min(1.0, self._cosine(query_emb, emb))), 4)
            for t, emb in prototypes.items()
        }


class _LLMClassifier:
    """Embedding-intent path used only when T1 did not produce a route."""

    def __init__(self, qwen_bridge: Any) -> None:
        self.qwen_bridge = qwen_bridge
        self._embedding_classifier: _FallbackClassifier | None = None

    @property
    def _embed_cls(self) -> _FallbackClassifier:
        if self._embedding_classifier is None:
            self._embedding_classifier = _FallbackClassifier()
        return self._embedding_classifier

    def classify_intent(self, query: str) -> tuple[str, float]:
        return self._embed_cls.classify_intent(query)

    def classify_intent_with_memory_check(self, query: str) -> tuple[str, float, bool]:
        target_ir, confidence = self._embed_cls.classify_intent(query)
        is_memory = self._embed_cls.is_memory_recall_query(query, threshold=0.38)
        return target_ir, confidence, is_memory

    def is_profile_query(self, query: str, threshold: float = 0.55) -> bool:
        return self._embed_cls.is_memory_recall_query(query, threshold)


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
        entities = {
            entity.strip(".,:;!?")
            for entity in re.findall(r"\b[\w#@][\w\-.#@]*\b", raw_input, flags=re.UNICODE)
            if _looks_like_structural_identifier(entity)
        }
        # Proper-noun entities via the CLL name-evidence mechanism (mid-sentence
        # capitalization / digits), the SAME signal the concept index uses —
        # this is why "the Vorbani project" yields entity 'vorbani' but a
        # sentence-initial "What" does not. It replaces the old camelCase-only
        # heuristic that silently missed every plain proper noun, which in turn
        # caused entity-less queries to inherit stale dialogue focus (ghost
        # leaks). Language-agnostic, no word list; falls back to camelCase-only
        # when the concept index is not active.
        try:
            from .cll_shadow import get_shadow, index_enabled, shadow_enabled
            if index_enabled() or shadow_enabled():
                shadow = get_shadow()
                if shadow.loaded:
                    _, literals = shadow.encode(raw_input, mode="query")
                    entities.update(lit[2:] for lit in literals)
        except Exception:
            pass
        if entities:
            scope["entities"] = sorted(entities)
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

    def base_ir(self, raw_input: str, namespace: str = "TECHNICAL") -> SemanticIR:
        tokens = _raw_tokens(raw_input)
        scope = self._scope_from_tokens(tokens, raw_input, existing_scope={})
        return SemanticIR(
            target_ir="OP_ESCAPE_TO_SANDBOX",
            system_action="UNCLASSIFIED",
            confidence=0.0,
            scope_constraints=scope,
            execution_mode=ExecutionMode.GROQ_BOUNDED_INTERFACE,
            domain_namespace=namespace,
            intent_domain=IntentDomain.UNKNOWN,
            tokens=tokens,
            hypotheses=[],
        )

    def compile(self, raw_input: str, namespace: str = "TECHNICAL", session: dict[str, Any] | None = None) -> SemanticIR:
        session = session or {}
        # Use raw text directly — no preprocessing pipeline, no normalisation.
        # The LLM (Qwen 1.7B) and embedding model handle all languages natively.
        tokens = _raw_tokens(raw_input)
        scope = self._scope_from_tokens(tokens, raw_input, existing_scope={})

        # 1. Classify intent AND check memory recall in a single embedding call.
        # Using one embedding avoids two Modal round-trips for every query.
        target_ir, confidence, is_memory_query = self.classifier.classify_intent_with_memory_check(raw_input)

        # 2. Memory store/recall — fires when memory recall prototype similarity is high.
        # This works for writes ("My name is X") and recalls ("What is my name?") in any language.
        if is_memory_query or target_ir == "WORKSPACE_QUERY":
            scope["profile_query"] = True
            target_ir = "WORKSPACE_QUERY"
            confidence = max(confidence, self.confidence_threshold)

        # 3. Session context rescue — inherit active intent when classifier is uncertain
        execution_mode = ExecutionMode.GROQ_BOUNDED_INTERFACE

        # 4. Scope enrichment — language-neutral entity + number extraction
        scope = self._scope_from_tokens(tokens, raw_input, existing_scope=scope)
        # 5. Mark profile write in scope
        if scope.get("profile_write"):
            scope["profile_query"] = True

        # 6. Session object carry-forward (discourse-focus inheritance)
        # A query that names NO entities and has conversational context
        # inherits the focus referent as a CANDIDATE. The relation type is
        # irrelevant to what "it" refers to — the old uses_/has_/is_ prefix
        # guard was a vocabulary heuristic that blocked exactly the most
        # common dialogue follow-ups ("what database does it USE?"). Wrong
        # narrowing is already handled downstream: retrieval intersection,
        # entity-scoped claims, the 15-minute topic decay, and gap honesty.
        context_inherited = False
        if "entities" not in scope and session.get("ACTIVE_OBJECT"):
            scope["entities"] = [session["ACTIVE_OBJECT"]]
            context_inherited = True

        hypotheses: list[Hypothesis] = []
        routed_target = target_ir
        if target_ir == "OP_ESCAPE_TO_SANDBOX" or confidence < self.confidence_threshold:
            hypotheses.append(
                Hypothesis(
                    target_ir=target_ir,
                    score=round(confidence, 4),
                    role="candidate",
                    reason="service-backed intent score below routing threshold",
                )
            )
            routed_target = "OP_ESCAPE_TO_SANDBOX"
            execution_mode = ExecutionMode.AIR_GAPPED_CONTAINER

        domain = IntentDomain.UNKNOWN if routed_target == "OP_ESCAPE_TO_SANDBOX" else self._domain_for_ir(routed_target)
        return SemanticIR(
            target_ir=routed_target,
            system_action=routed_target,
            confidence=round(confidence, 4),
            scope_constraints=scope,
            execution_mode=execution_mode,
            domain_namespace=namespace,
            intent_domain=domain,
            tokens=tokens,
            hypotheses=hypotheses,
            context_inherited=context_inherited,
        )
