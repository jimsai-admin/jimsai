from __future__ import annotations

import math
import re

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
QUERY_ONLY_PROVENANCES = {"local_extraction"}
RETRIEVAL_STOP_TERMS = {
    "about",
    "after",
    "before",
    "caught",
    "does",
    "should",
    "someone",
    "that",
    "the",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


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
        raw_query_terms = set(ir.tokens) | {str(entity).lower() for entity in ir.scope_constraints.get("entities", [])}
        query_terms = {term for term in raw_query_terms if term not in RETRIEVAL_STOP_TERMS}
        if not query_terms:
            query_terms = raw_query_terms
        query_phrases = self._query_phrases(query)
        question_intent = ir.scope_constraints.get("question_intent", {})
        relation_filter = str(question_intent.get("relation") or "") if isinstance(question_intent, dict) else ""
        user_profile_query = bool(ir.scope_constraints.get("profile_query")) or bool(raw_query_terms & USER_PROFILE_TOKENS)
        has_entity_scope = bool(ir.scope_constraints.get("entities")) and relation_filter not in DOCUMENT_WIDE_RELATIONS
        effective_limit = 24 if relation_filter in DOCUMENT_WIDE_RELATIONS or relation_filter == "means" else limit
        results: dict[str, RetrievalResult] = {}
        for sig in self.memory.visible_signatures(workspace_id=workspace_id, user_id=user_id):
            if sig.id in exclude_ids:
                continue
            if sig.provenance in QUERY_ONLY_PROVENANCES:
                continue
            reasons: list[str] = []
            matched_terms: set[str] = set()
            score = 0.0
            entity_names = {e.name.lower() for e in sig.structured.entities}
            entity_matches = {
                term
                for entity in entity_names
                for term in query_terms
                if term_matches(entity, term)
            }
            if entity_matches:
                matched_terms.update(entity_matches)
                score += 0.35
                reasons.append("entity_index")
            tag_names = {tag.lower() for tag in sig.abstraction_tags}
            tag_matches = {
                term
                for tag in tag_names
                for term in query_terms
                if term_matches(tag, term) or term in tag or tag in term
            }
            if tag_matches:
                matched_terms.update(tag_matches)
                score += 0.18
                reasons.append("abstraction_tag_index")
            raw_excerpt = sig.raw_excerpt.lower()
            phrase_matches = {phrase for phrase in query_phrases if phrase in raw_excerpt}
            if phrase_matches:
                matched_terms.update(term for phrase in phrase_matches for term in phrase.split())
                score += min(0.5, 0.28 * len(phrase_matches))
                reasons.append("phrase_index")
            excerpt_matches = {term for term in query_terms if len(term) >= 3 and term in raw_excerpt}
            if len(excerpt_matches) >= 2:
                matched_terms.update(excerpt_matches)
                score += min(0.28, 0.06 * len(excerpt_matches))
                reasons.append("excerpt_term_index")
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
                    matched_terms.update(
                        term
                        for term in query_terms
                        if term_matches(relation.subject, term) or term_matches(relation.object, term)
                    )
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
                causal_matches = {
                    term
                    for causal in causal_terms
                    for term in query_terms
                    if term_matches(causal, term) or term in causal
                }
                if causal_matches:
                    matched_terms.update(causal_matches)
                    score += 0.2
                    reasons.append("causal_index")
            score += 0.1 * sig.importance.current_score
            if len(query_terms) >= 5 and not relation_filter and not user_profile_query:
                coverage = len(matched_terms) / max(len(query_terms), 1)
                if coverage >= 0.4:
                    score += 0.2 * coverage
                    reasons.append("query_coverage_boost")
                elif coverage < 0.25 and reasons:
                    score *= 0.55
                    reasons.append("low_query_coverage_penalty")
            if score >= 0.12:
                results[sig.id] = RetrievalResult(signature=sig, score=round(score, 4), reasons=reasons or ["importance_index"])
        ranked = sorted(results.values(), key=lambda r: (-r.score, r.signature.id))
        for result in ranked[:effective_limit]:
            result.signature.importance.retrieval_count += 1
            result.signature.importance.current_score = min(1.0, result.signature.importance.current_score + 0.01)
        return ranked[:effective_limit]

    def _query_phrases(self, query: str) -> set[str]:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9_+\-.#]+", query.lower())
            if len(token) >= 3 and token not in RETRIEVAL_STOP_TERMS
        ]
        phrases: set[str] = set()
        for size in (2, 3):
            for index in range(0, max(0, len(tokens) - size + 1)):
                phrases.add(" ".join(tokens[index : index + size]))
        return phrases
