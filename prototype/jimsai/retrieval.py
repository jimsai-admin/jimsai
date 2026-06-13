from __future__ import annotations

import math
import re

from .encoder import stable_id
from .memory import FourLayerMemoryStore
from .models import RetrievalResult, SemanticIR


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    lnorm = math.sqrt(sum(a * a for a in left)) or 1.0
    rnorm = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (lnorm * rnorm)


def term_matches(left: str, right: str) -> bool:
    left = left.lower()
    right = right.lower()
    return left == right or left.startswith(f"{right}.") or right.startswith(f"{left}.")


def _is_document_wide_relation(predicate: str) -> bool:
    return predicate.startswith("has_") or predicate.startswith("uses_") or predicate.startswith("is_")


class MultiIndexRetrievalEngine:
    def __init__(self, memory: FourLayerMemoryStore) -> None:
        self.memory = memory
        self._last_retrieval_stats: dict[str, int] = {"semantic_hits": 0, "lexical_hits": 0, "total": 0}

    def get_last_retrieval_stats(self) -> dict[str, int]:
        """Return stats from the most recent retrieve() call.

        Returns a dict with:
          - semantic_hits: count of results whose latent_embedding_source == "external_service"
          - lexical_hits: count of results using hash_projection or with no embedding source
          - total: total results returned
        """
        return dict(self._last_retrieval_stats)

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
        # query_vec is intentionally empty — in-memory retrieval is lexical-first.
        # Signatures with real embeddings are surfaced via Vectorize similarity
        # search in pipeline._hydrate_persistent_retrieval() before this runs.
        # Hash embeddings have been removed; cosine on empty vec yields 0.0,
        # which correctly demotes unembedded signatures to lexical-only paths.
        query_vec: list[float] = []
        raw_query_terms = set(ir.tokens) | {str(entity).lower() for entity in ir.scope_constraints.get("entities", [])}
        query_terms = raw_query_terms
        query_phrases = self._query_phrases(query)
        question_intent = ir.scope_constraints.get("question_intent", {})
        relation_filter = str(question_intent.get("relation") or "") if isinstance(question_intent, dict) else ""
        user_profile_query = bool(ir.scope_constraints.get("profile_query"))
        has_entity_scope = bool(ir.scope_constraints.get("entities")) and not _is_document_wide_relation(relation_filter)
        effective_limit = 24 if _is_document_wide_relation(relation_filter) or relation_filter == "means" else limit
        results: dict[str, RetrievalResult] = {}
        for sig in self.memory.visible_signatures(workspace_id=workspace_id, user_id=user_id):
            if sig.id in exclude_ids:
                continue
            if sig.provenance == "local_extraction":
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
                # Use the same term_matches convention as entity matching:
                # exact match or one is a dot-prefixed extension of the other.
                # Substring matching (term in tag) is deliberately removed — it
                # was causing "code" to match "encoding", "processor" to match
                # "proc", producing cross-query retrieval contamination.
                if term_matches(tag, term)
            }
            if tag_matches:
                matched_terms.update(tag_matches)
                score += 0.18
                reasons.append("abstraction_tag_index")
            raw_excerpt = self._content_excerpt(sig.raw_excerpt).lower()
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
                # Check for user-profile relations: subject is "user" with structural predicate
                profile_relations = {
                    relation.predicate
                    for relation in sig.structured.relations
                    if relation.subject.lower() == "user"
                    and (relation.predicate.startswith("has_") or relation.predicate.startswith("is_"))
                }
                # Check for profile-related abstraction tags — any tag that contains
                # "profile" or "user" as a substring (language-neutral prefix check)
                profile_tags = {
                    tag for tag in sig.abstraction_tags
                    if "profile" in tag.lower() or tag.lower() in {"user", "personal", "identity"}
                }
                if profile_relations or profile_tags:
                    score += 0.6
                    reasons.append("user_profile_memory")
            if sig.user_id == user_id:
                user_relation_score = 0.0
                for relation in sig.structured.relations:
                    if relation.subject.lower() != "user":
                        continue
                    relation_terms = set(re.findall(r"\w+", relation.predicate.lower(), flags=re.UNICODE))
                    relation_terms.update(re.findall(r"\w+", relation.object.lower(), flags=re.UNICODE))
                    overlap = query_terms & relation_terms
                    if overlap:
                        matched_terms.update(overlap)
                        user_relation_score = max(user_relation_score, min(0.5, 0.18 * len(overlap)))
                if user_relation_score:
                    score += user_relation_score
                    reasons.append("user_relation_index")
            semantic = max(cosine(query_vec, sig.latent_embedding), 0.0)
            latent_source = str(sig.metadata.get("latent_embedding_source") or "hash_projection")

            # ── Semantic-first retrieval architecture ────────────────────────
            # Real embeddings (external_service) are the PRIMARY signal.
            # Lexical signals VERIFY the semantic match — they don't replace it.
            # Hash projections are structurally unreliable: hard-cap their
            # contribution and block unverified candidates entirely.
            if latent_source == "external_service":
                if semantic < 0.30:
                    # Hard gate: below semantic threshold, skip this signature
                    # entirely to prevent cross-query contamination.
                    continue
                # Semantic majority — lexical boosts verify/amplify the match
                score = semantic * 0.65
                reasons.append("semantic_index")
                if entity_matches:
                    score += 0.15
                if phrase_matches:
                    score += 0.15
                if user_profile_query and sig.user_id == user_id:
                    score += 0.20
            else:
                # Hash fallback path: lexical must fire, semantic is a weak tiebreaker,
                # and total score is hard-capped to prevent hash retrieval from
                # outcompeting real-embedded signatures in mixed-corpus queries.
                has_structured_or_lexical_evidence = bool(reasons or matched_terms)
                if not has_structured_or_lexical_evidence:
                    # No lexical match at all → skip entirely, never hallucinate
                    continue
                # Lexical score is already accumulated in `score` above.
                # Demote and cap it.
                score = score * 0.40
                score = min(score, 0.45)
                if semantic > 0:
                    score += 0.04 * semantic  # weak tiebreaker only
                    reasons.append("semantic_tiebreaker")
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

            # Cross-query contamination guard: signatures whose raw_excerpt is
            # itself a prior query prompt (provenance="local_extraction" is already
            # filtered above, but resolved-prompt-memory and ingested prompts can
            # still slip through). If the excerpt looks like a raw user prompt
            # (starts with "Prompt:" or "prompt:") and no strong structural match
            # exists, apply a heavy penalty so prior queries don't surface as answers.
            if (
                raw_excerpt.startswith("prompt:")
                and not any(r in reasons for r in ("entity_index", "relation_index", "user_profile_memory", "user_relation_index", "causal_index"))
                and "phrase_index" not in reasons
            ):
                score *= 0.15
                reasons.append("prompt_excerpt_penalty")

            if score >= 0.12 and self._passes_evidence_gate(
                query_terms=query_terms,
                matched_terms=matched_terms,
                reasons=reasons,
                relation_filter=relation_filter,
                user_profile_query=user_profile_query,
            ):
                results[sig.id] = RetrievalResult(signature=sig, score=round(score, 4), reasons=reasons or ["importance_index"])
        ranked = sorted(results.values(), key=lambda r: (-r.score, r.signature.id))
        deduped = self._deduplicate_by_predicate(ranked, user_id)
        final = deduped[:effective_limit]
        for result in final:
            result.signature.importance.retrieval_count += 1
            result.signature.importance.current_score = min(1.0, result.signature.importance.current_score + 0.01)

        # Compute and cache retrieval stats for observability
        semantic_hits = sum(
            1 for r in final
            if str(r.signature.metadata.get("latent_embedding_source") or "hash_projection") == "external_service"
        )
        lexical_hits = len(final) - semantic_hits
        self._last_retrieval_stats = {
            "semantic_hits": semantic_hits,
            "lexical_hits": lexical_hits,
            "total": len(final),
        }

        return final

    def _query_phrases(self, query: str) -> set[str]:
        # Unicode-aware tokenization — preserves non-Latin scripts (Arabic, CJK, Yoruba, etc.)
        tokens = [
            token
            for token in re.findall(r"[\w_+\-.#]+", query.lower(), flags=re.UNICODE)
            if len(token) >= 3
        ]
        phrases: set[str] = set()
        for size in (2, 3):
            for index in range(0, max(0, len(tokens) - size + 1)):
                phrases.add(" ".join(tokens[index : index + size]))
        return phrases

    def _content_excerpt(self, excerpt: str) -> str:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", excerpt).strip())
            if sentence.strip()
        ]
        content_sentences = [
            sentence
            for sentence in sentences
            if not self._is_provenance_sentence(sentence.lower())
        ]
        return " ".join(content_sentences) if content_sentences else excerpt

    def _is_provenance_sentence(self, lower_sentence: str) -> bool:
        return (
            lower_sentence.startswith("source url:")
            or lower_sentence.startswith("source license:")
            or "training text is local paraphrase" in lower_sentence
        )

    def _passes_evidence_gate(
        self,
        query_terms: set[str],
        matched_terms: set[str],
        reasons: list[str],
        relation_filter: str,
        user_profile_query: bool,
    ) -> bool:
        if not reasons:
            return False
        # Semantic index already passed the hard gate (cosine ≥ 0.30), always admit.
        if "semantic_index" in reasons:
            return True
        if relation_filter and "relation_index" in reasons:
            return True
        if user_profile_query and "user_profile_memory" in reasons:
            return True
        if "user_relation_index" in reasons:
            return True
        if "phrase_index" in reasons or "causal_index" in reasons:
            return True
        if len(query_terms) <= 2:
            return bool(matched_terms)
        if len(matched_terms) >= 2:
            return True
        if _is_document_wide_relation(relation_filter) and "relation_index" in reasons:
            return True
        return False

    def _deduplicate_by_predicate(
        self,
        results: list[RetrievalResult],
        user_id: str | None,
    ) -> list[RetrievalResult]:
        """For user profile facts, keep only the highest-scoring result per
        (user_id, subject, predicate) triple.

        This handles contradictions — e.g. three "has_name" memories — without
        needing to know which specific predicates to watch for.  It works for
        any predicate in any language because it operates on the structured
        relation graph, not on raw text.

        Non-user-profile signatures pass through untouched.
        """
        if not user_id:
            return results

        # Map (user_id, subject, predicate) → best score seen so far
        seen: dict[tuple[str, str, str], float] = {}
        deduped: list[RetrievalResult] = []

        for result in results:
            sig = result.signature

            # Only deduplicate signatures that belong to this user and contain
            # user-profile relations (subject == "user").
            if sig.user_id != user_id:
                deduped.append(result)
                continue

            profile_keys = [
                (sig.user_id, rel.subject.lower(), rel.predicate)
                for rel in sig.structured.relations
                if rel.subject.lower() == "user"
            ]

            if not profile_keys:
                deduped.append(result)
                continue

            # For each predicate key, check whether this result beats the best
            # score seen so far.  If it does for any key, include this result
            # and evict any previously included result for that key.
            should_include = False
            for key in profile_keys:
                if key not in seen or result.score > seen[key]:
                    seen[key] = result.score
                    should_include = True

            if should_include:
                # Remove any already-added lower-scoring result that shares a
                # predicate key with this one.
                deduped = [
                    r for r in deduped
                    if not any(
                        (r.signature.user_id, rel.subject.lower(), rel.predicate) in profile_keys
                        for rel in r.signature.structured.relations
                    )
                ]
                deduped.append(result)

        return deduped
