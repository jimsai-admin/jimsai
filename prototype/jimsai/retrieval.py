from __future__ import annotations

import math

from .encoder import hash_embedding
from .memory import FourLayerMemoryStore
from .models import RetrievalResult, SemanticIR


DOCUMENT_WIDE_RELATIONS = {
    "has_title",
    "has_case_study",
    "has_author",
    "has_institution",
    "has_student_id",
    "has_objective",
    "has_module",
    "has_problem",
    "uses_technology",
    "has_name",
    "has_role",
    "is_building",
}

USER_PROFILE_PREDICATES = {"has_name", "has_role", "is_building"}
USER_PROFILE_TOKENS = {"i", "me", "my", "mine", "myself", "name", "profile", "know", "remember"}


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    lnorm = math.sqrt(sum(a * a for a in left)) or 1.0
    rnorm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (lnorm * rnorm)


def term_matches(left: str, right: str) -> bool:
    left = left.lower()
    right = right.lower()
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


class MultiIndexRetrievalEngine:
    def __init__(self, memory: FourLayerMemoryStore) -> None:
        self.memory = memory

    def retrieve(
        self,
        ir: SemanticIR,
        query: str,
        limit: int = 8,
        exclude_ids: set[str] | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ) -> list[RetrievalResult]:
        exclude_ids = exclude_ids or set()
        query_vec = hash_embedding(query)
        query_terms = set(ir.tokens) | {str(entity).lower() for entity in ir.scope_constraints.get("entities", [])}
        question_intent = ir.scope_constraints.get("question_intent", {})
        relation_filter = str(question_intent.get("relation") or "") if isinstance(question_intent, dict) else ""
        user_profile_query = bool(ir.scope_constraints.get("profile_query")) or bool(query_terms & USER_PROFILE_TOKENS)
        has_entity_scope = bool(ir.scope_constraints.get("entities")) and relation_filter not in DOCUMENT_WIDE_RELATIONS
        effective_limit = 24 if relation_filter in DOCUMENT_WIDE_RELATIONS or relation_filter == "means" else limit
        results: dict[str, RetrievalResult] = {}
        for sig in self.memory.visible_signatures(workspace_id=workspace_id, user_id=user_id):
            if sig.id in exclude_ids:
                continue
            reasons: list[str] = []
            score = 0.0
            entity_names = {e.name.lower() for e in sig.structured.entities}
            if any(term_matches(entity, term) for entity in entity_names for term in query_terms):
                score += 0.35
                reasons.append("entity_index")
            if relation_filter:
                relation_matched = False
                for relation in sig.structured.relations:
                    if relation.predicate != relation_filter:
                        continue
                    relation_scope_matched = any(
                        term_matches(relation.subject, term) or term_matches(relation.object, term)
                        for term in query_terms
                    )
                    if has_entity_scope and not relation_scope_matched:
                        continue
                    relation_matched = True
                    break
                if relation_matched:
                    score += 0.55
                    reasons.append("relation_index")
            if user_profile_query and sig.user_id == user_id:
                profile_relations = {relation.predicate for relation in sig.structured.relations} & USER_PROFILE_PREDICATES
                profile_tags = {"user", "profile", "user_profile_training"} & set(sig.abstraction_tags)
                if profile_relations or profile_tags:
                    score += 0.6
                    reasons.append("user_profile_memory")
            semantic = max(cosine(query_vec, sig.latent_embedding), 0.0)
            if semantic > 0:
                score += 0.35 * semantic
                reasons.append("semantic_index")
            if sig.structured.causal_chain:
                causal_terms = {c.cause.lower() for c in sig.structured.causal_chain} | {c.effect.lower() for c in sig.structured.causal_chain}
                if any(term_matches(causal, term) for causal in causal_terms for term in query_terms):
                    score += 0.2
                    reasons.append("causal_index")
            score += 0.1 * sig.importance.current_score
            if score >= 0.12:
                results[sig.id] = RetrievalResult(signature=sig, score=round(score, 4), reasons=reasons or ["importance_index"])
        ranked = sorted(results.values(), key=lambda r: (-r.score, r.signature.id))
        for result in ranked[:effective_limit]:
            result.signature.importance.retrieval_count += 1
            result.signature.importance.current_score = min(1.0, result.signature.importance.current_score + 0.01)
        return ranked[:effective_limit]
