"""
Multilingual intent classifier using semantic embeddings.

Replaces hardcoded English token sets with embedding-based semantic similarity.
Supports all languages through multilingual-e5 model.
"""

from __future__ import annotations

import numpy as np
from typing import Any
from functools import lru_cache

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore


class EmbeddingClassifier:
    """Multilingual intent classifier using semantic embeddings."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small"):
        """Initialize classifier with multilingual embedding model.
        
        Args:
            model_name: Hugging Face model ID for multilingual embeddings.
                       Use 'intfloat/multilingual-e5-small' for production (lightweight).
                       Use 'intfloat/multilingual-e5-base' for higher accuracy.
        """
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        
        # IR intent prototypes — semantic concept descriptions, not keyword lists.
        # The embedding model maps any query in any language to the same vector space,
        # so these English descriptions work as universal semantic anchors.
        self.ir_prototypes: dict[str, str] = {
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

        # Memory recall prototype — covers any user-stored fact recall in any language
        self.memory_recall_prototype = (
            "Recall stored information, personal facts, user preferences, prior conversations, "
            "remembered notes, tasks, or anything the user previously shared or asked JimsAI to store."
        )
        
        # Embed all prototypes once
        self._prototype_embeddings: dict[str, np.ndarray] = {}
        for ir_target, description in self.ir_prototypes.items():
            try:
                embedding = self.model.encode("passage: " + description, normalize_embeddings=True)
                self._prototype_embeddings[ir_target] = embedding
            except Exception:
                # Fallback: create zero embedding if model fails
                self._prototype_embeddings[ir_target] = np.zeros(self.model.get_sentence_embedding_dimension())
        
        # Memory recall prototype — embed once for is_profile_query detection
        try:
            self.profile_embedding = self.model.encode(
                "passage: " + self.memory_recall_prototype,
                normalize_embeddings=True,
            )
        except Exception:
            dim = self.model.get_sentence_embedding_dimension()
            self.profile_embedding = np.zeros(dim)
    
    def classify_intent(self, query: str) -> tuple[str, float]:
        """Classify query to best IR intent using embedding similarity.
        
        Args:
            query: User query in any language.
        
        Returns:
            Tuple of (best_ir_target, confidence_score)
        """
        try:
            query_embedding = self.model.encode("query: " + query, normalize_embeddings=True)
        except Exception:
            # If embedding fails, return sandbox
            return "OP_ESCAPE_TO_SANDBOX", 0.0
        
        best_ir = "OP_ESCAPE_TO_SANDBOX"
        best_score = 0.0
        
        for ir_target, prototype_embedding in self._prototype_embeddings.items():
            # Cosine similarity (normalized embeddings)
            score = float(np.dot(query_embedding, prototype_embedding))
            if score > best_score:
                best_score = score
                best_ir = ir_target
        
        return best_ir, round(max(0.0, min(1.0, best_score)), 4)
    
    def is_profile_query(self, query: str, threshold: float = 0.70) -> bool:
        """Detect if query is about user profile/identity.
        
        Works across all languages through semantic similarity.
        
        Args:
            query: User query in any language.
            threshold: Similarity threshold for profile classification.
        
        Returns:
            True if query appears to be profile-related.
        """
        try:
            query_embedding = self.model.encode("query: " + query, normalize_embeddings=True)
        except Exception:
            return False
        
        # Cosine similarity
        similarity = float(np.dot(query_embedding, self.profile_embedding))
        return similarity > threshold
    
    def get_intent_scores(self, query: str) -> dict[str, float]:
        """Get similarity scores for all IR intents.
        
        Useful for debugging and measuring confidence distribution.
        
        Args:
            query: User query in any language.
        
        Returns:
            Dict mapping IR targets to similarity scores.
        """
        try:
            query_embedding = self.model.encode("query: " + query, normalize_embeddings=True)
        except Exception:
            return {ir_target: 0.0 for ir_target in self.ir_prototypes}
        
        scores = {}
        for ir_target, prototype_embedding in self._prototype_embeddings.items():
            score = float(np.dot(query_embedding, prototype_embedding))
            scores[ir_target] = round(max(0.0, min(1.0, score)), 4)
        
        return scores
    
    def clear_cache(self) -> None:
        """Clear any internal caches (for memory optimization)."""
        if hasattr(self, '_sentence_cache'):
            self._sentence_cache.cache_clear()


# Global classifier instance (lazy-loaded)
_global_classifier: EmbeddingClassifier | None = None


def get_classifier(model_name: str = "intfloat/multilingual-e5-small") -> EmbeddingClassifier:
    """Get or create global embedding classifier.
    
    Caches classifier to avoid reloading model.
    
    Args:
        model_name: Hugging Face model ID.
    
    Returns:
        EmbeddingClassifier instance.
    """
    global _global_classifier
    
    if _global_classifier is None:
        _global_classifier = EmbeddingClassifier(model_name=model_name)
    
    return _global_classifier


def reset_classifier() -> None:
    """Reset global classifier (for testing)."""
    global _global_classifier
    _global_classifier = None
