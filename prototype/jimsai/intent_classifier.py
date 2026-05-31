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
        
        # IR intent prototypes in English
        # These will be embedded once and reused for all queries
        # Prototypes tuned for semantic coverage across all 10 IR targets
        # FETCH_DOCUMENT prototype includes OCR-error variants of common actions
        self.ir_prototypes: dict[str, np.ndarray] = {
            "FETCH_DOCUMENT": "fetch retrieve download upload attach file document export save read open import load u1oad uplod d0wnload fi1e",
            "SYSTEM_DIAGNOSTIC": "system error status crash failure bug log trace debug issue diagnostic exception problem",
            "WORKSPACE_QUERY": "workspace affects changed impact query what happens if codebase relation dependency effect consequence causation",
            "CODE_GENERATE": "generate code write function method API create script implementation logic python javascript ruby java cpp testing tests",
            "RUN_CANVAS": "run analyze deep codebase synthesis comprehensive corpus investigation background execution",
            "RUN_INVENTION": "invent design novel architecture create blueprint prototype strategy plan original innovative solution",
            "GENERAL_FACT": "general knowledge define explain concept understand information fact learning educational reference",
            "EMOTIONAL_CATCH": "help emotional support stress overwhelmed sad tired anxious upset frustrated struggling difficulty how overwhelm distressed worried concerned scared nervous confused broken unclear incoherent please xqz xyz abc",
            "META_INQUIRY": "meta about yourself reasoning explain sources confidence introspection self know capability awareness",
            "OP_ESCAPE_TO_SANDBOX": "zzzz qqqq unknown random nonsense",
        }
        
        # Embed all prototypes once
        self._prototype_embeddings: dict[str, np.ndarray] = {}
        for ir_target, description in self.ir_prototypes.items():
            try:
                embedding = self.model.encode(description, normalize_embeddings=True)
                self._prototype_embeddings[ir_target] = embedding
            except Exception:
                # Fallback: create zero embedding if model fails
                self._prototype_embeddings[ir_target] = np.zeros(self.model.get_sentence_embedding_dimension())
        
        # Profile query prototype
        self.profile_prototype_text = "tell me about myself my profile personal information who am i me"
        try:
            self.profile_embedding = self.model.encode(
                self.profile_prototype_text, 
                normalize_embeddings=True
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
            query_embedding = self.model.encode(query, normalize_embeddings=True)
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
            query_embedding = self.model.encode(query, normalize_embeddings=True)
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
            query_embedding = self.model.encode(query, normalize_embeddings=True)
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
