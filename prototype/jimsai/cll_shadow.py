"""
Concept Language Layer — shadow-mode concept index for the production pipeline.

Activated by JIMS_CONCEPT_INDEX=shadow. In shadow mode this module OBSERVES
every retrieval: it encodes the query and the visible signatures into concept
IDs (from the from-source lexicon built by experiments/concept_model/
build_lexicon.py) and logs what concept-intersection retrieval WOULD have
returned next to what the production engine actually returned. Zero behavior
change — it exists to gather evidence before JIMS_CONCEPT_INDEX=on is judged
by the generative harness (P4 multilingual is the success bar).

Design doc: docs/concept_language_layer.md. Anti-hardcoding protocol applies:
this module contains no vocabulary and no language-specific branches; all
language data comes from the lexicon file (env JIMS_CONCEPT_LEXICON_PATH).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("jimsai.cll_shadow")

_CJK_RUN = re.compile(r"[一-鿿]+")
_TOKEN = re.compile(r"[^\W_]+")


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def surface_key(surface: str) -> str:
    text = _strip_marks(surface.lower())
    text = re.sub(r"[^\w一-鿿]+", " ", text).strip()
    text = re.sub(r"(?<=[一-鿿]) (?=[一-鿿])", "", text)
    return re.sub(r"\s+", " ", text)


class ConceptShadowIndex:
    """Language-agnostic concept encoder + posting-list index, shadow-only."""

    def __init__(self, lexicon_path: str | None = None):
        path = Path(
            lexicon_path
            or os.getenv("JIMS_CONCEPT_LEXICON_PATH", "")
            or Path(__file__).resolve().parents[2] / "experiments" / "concept_model" / "data" / "lexicon.jsonl"
        )
        # surface key → list of concept ids (source/popularity order), all languages pooled:
        # shadow mode cannot trust query language detection, so it matches every language's
        # surfaces at once (recall-first; production 'on' mode can add language priors).
        self.surfaces: dict[str, list[str]] = defaultdict(list)
        self.loaded = False
        # Typo-robust O(1) lookups over the growing lexicon (no word lists):
        #   skeleton — (first char, last char, sorted interior): identifies a
        #     word from its anchors, robust to interior transpositions
        #     ("proejct" → "project"), the dominant real-typo class.
        #   anagram  — sorted full letters: catches transpositions that move
        #     the boundary characters. Both require a UNIQUE candidate.
        self._skeleton: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        self._anagram: dict[str, set[str]] = defaultdict(set)
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    key = surface_key(row["surface"])
                    if key and row["concept"] not in self.surfaces[key]:
                        self.surfaces[key].append(row["concept"])
            for key in self.surfaces:
                if " " in key or _CJK_RUN.search(key):
                    continue
                if len(key) >= 5:
                    self._skeleton[(key[0], key[-1], "".join(sorted(key[1:-1])))].add(key)
                if len(key) >= 4:
                    self._anagram["".join(sorted(key))].add(key)
            self.loaded = True
            self._max_phrase = max((k.count(" ") + 1 for k in self.surfaces), default=1)
            self._max_cjk = max((len(k) for k in self.surfaces if _CJK_RUN.fullmatch(k)), default=4)
            logger.info("CLL shadow index loaded: %d surface keys from %s", len(self.surfaces), path)
        else:
            logger.warning("CLL shadow: lexicon not found at %s — shadow disabled", path)
        self._sig_concepts: dict[str, frozenset[str]] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._assertive: dict[str, set[str]] = defaultdict(set)
        # Corpus name-memory: tokens seen capitalized MID-sentence anywhere in
        # an indexed document are name-evidenced everywhere (frequency is the
        # wrong signal — popular entities stay names however often discussed).
        self._name_evidence: set[str] = set()
        self._doc_count = 0

    def _typo_repair(self, word: str) -> str | None:
        """O(1) recovery of a misspelled CONTENT word from its letter anchors.
        Only fires on a unique candidate; unknown-but-correct words stay
        unknown (soft literals) rather than being guessed at."""
        if len(word) >= 5:
            candidates = self._skeleton.get((word[0], word[-1], "".join(sorted(word[1:-1])))) or set()
            candidates = candidates - {word}
            if len(candidates) == 1:
                return next(iter(candidates))
        if len(word) >= 4:
            candidates = self._anagram.get("".join(sorted(word))) or set()
            candidates = candidates - {word}
            if len(candidates) == 1:
                return next(iter(candidates))
        return None

    # ── encoding ──

    def encode(self, text: str, mode: str = "query") -> tuple[set[str], set[str]]:
        """→ (concept ids, hard literal keys). No language argument by design.

        Asymmetric literal policy (M1 shadow finding, 2026-07-07):
        - mode="document" (indexing): recall-first — ANY capitalized or
          digit-bearing unknown token indexes as a literal, including
          sentence-initial ones. A record must never lose its entity because
          the entity opened the sentence ("Tepogi is in ..." must index
          L:tepogi, or literal-gated queries veto the correct record).
        - mode="query": precision — digits or MID-sentence capitals as before
          (French "Quelle ..." must not gate), plus corpus-memory promotion: a
          sentence-initial capitalized token DOES count as a literal when the
          index has already seen it as one (orthography alone is not name
          evidence, but corpus memory is).
        """
        concepts: set[str] = set()
        literals: set[str] = set()
        text = re.sub(r"(?<=[一-鿿])[^\w一-鿿]+(?=[一-鿿])", "", text)
        for match in re.finditer(r"[一-鿿]+|[^一-鿿]+", text):
            chunk = match.group(0)
            if _CJK_RUN.fullmatch(chunk):
                i = 0
                while i < len(chunk):
                    for size in range(min(self._max_cjk, len(chunk) - i), 0, -1):
                        piece = chunk[i : i + size]
                        if piece in self.surfaces or size == 1:
                            concepts.update(self.surfaces.get(piece, [])[:3])
                            i += size
                            break
            else:
                stripped = _strip_marks(chunk)
                # Sentence-initial capitalization is orthography, not name
                # evidence: only mid-sentence capitals or digits mark a token
                # as name-like. (Discovered live: French "Quelle ..." became a
                # spurious gating literal and vetoed a correct match.)
                # Clause boundaries include ':' — a colon introduces a clause
                # ("prompt: Which city…"), so the following token is clause-
                # initial and its capitalization is orthography, not name
                # evidence. Punctuation semantics, not language vocabulary.
                sentence_initial: set[int] = set()
                pos = 0
                for sentence_match in re.finditer(r"[^.!?。？！:：]+", stripped):
                    first = _TOKEN.search(sentence_match.group(0))
                    if first:
                        sentence_initial.add(pos)
                    pos += len(_TOKEN.findall(sentence_match.group(0)))
                words = _TOKEN.findall(stripped)
                i = 0
                while i < len(words):
                    matched = False
                    for size in range(min(self._max_phrase, len(words) - i), 0, -1):
                        phrase = " ".join(w.lower() for w in words[i : i + size])
                        if phrase in self.surfaces:
                            concepts.update(self.surfaces[phrase][:3])
                            i += size
                            matched = True
                            break
                    if not matched:
                        raw = words[i]
                        key = f"L:{raw.lower()}"
                        has_digit = any(ch.isdigit() for ch in raw)
                        has_upper = any(ch.isupper() for ch in raw)
                        if mode == "document":
                            name_like = has_digit or has_upper
                            if has_upper and i not in sentence_initial:
                                self._name_evidence.add(key)  # true name evidence
                        else:
                            # Query side: mid-sentence capitals and digits are
                            # direct evidence; sentence-initial capitals count
                            # only when the corpus name-memory backs them.
                            name_like = has_digit or (
                                has_upper
                                and (i not in sentence_initial
                                     or key in self._name_evidence)
                            )
                        if name_like:
                            literals.add(key)
                        elif mode == "query":
                            repaired = self._typo_repair(raw.lower())
                            if repaired:
                                concepts.update(self.surfaces[repaired][:3])
                        i += 1
        return concepts, literals

    # ── shadow observation / concept retrieval ──

    def _gate_literal(self, key: str) -> bool:
        """A query literal participates in the hard gate iff it is genuine
        name evidence: seen capitalized mid-sentence somewhere in the corpus
        (name-memory), or never seen at all (a ghost entity must veto — gap
        honesty is an index property). Frequency is deliberately NOT the
        signal: it conflates function words with popular entities."""
        return key in self._name_evidence or len(self._postings.get(key, ())) == 0

    def index_documents(self, visible_signatures: list) -> None:
        """Per-sentence indexing: a key found in a DECLARATIVE sentence is
        assertive evidence; in an interrogative sentence it is mere mention.
        'Questions don't assert' enforced at the index, symmetric with the
        claim-selection rule in the reasoning bridge."""
        for sig in visible_signatures:
            sig_id = getattr(sig, "id", None)
            if sig_id is None or sig_id in self._sig_concepts:
                continue
            text = str(getattr(sig, "raw_excerpt", "") or "")
            all_keys: set[str] = set()
            for chunk in re.split(r"(?<=[.!?。？！؟])\s+", text):
                if not chunk.strip():
                    continue
                concepts, literals = self.encode(chunk, mode="document")
                keys = concepts | literals
                all_keys |= keys
                if not chunk.rstrip(" .").endswith(("?", "？", "؟")):
                    for key in keys:
                        self._assertive[key].add(sig_id)
            self._sig_concepts[sig_id] = frozenset(all_keys)
            for key in all_keys:
                self._postings[key].add(sig_id)
            self._doc_count += 1

    def known_query_literals(self, query: str) -> int:
        """How many of the query's hard literals the corpus already knows.
        Used as ROUTING evidence: a query naming known workspace entities is
        a memory question regardless of what its wording resembles."""
        if not self.loaded:
            return 0
        _, literals = self.encode(query)
        return sum(1 for lit in literals if len(self._postings.get(lit, ())) > 0)

    def known_terms(self, terms: list[str]) -> int:
        """How many of the given terms (already-normalized entity strings,
        e.g. inherited dialogue focus) the corpus knows as indexed literals.
        Case-insensitive; checks postings directly rather than re-encoding —
        an inherited entity arrives lowercased and would not re-tokenize as a
        capitalized literal."""
        if not self.loaded:
            return 0
        return sum(1 for t in terms
                   if t and len(self._postings.get(f"L:{t.lower()}", ())) > 0)

    def concept_hits(self, query: str, visible_signatures: list,
                     limit: int = 8) -> list[str]:
        """Ordered concept-index retrieval (used by shadow reports AND on-mode
        candidate injection). The hard-literal gate applies only to RARE query
        literals — a ghost entity (df 0) correctly vetoes everything."""
        if not self.loaded:
            return []
        self.index_documents(visible_signatures)
        q_concepts, q_literals = self.encode(query)
        gate_literals = {l for l in q_literals if self._gate_literal(l)}
        if any(len(self._postings.get(l, ())) == 0 for l in gate_literals):
            # The asked-about entity is unknown to the corpus: the concept
            # index ABSTAINS (returns nothing) rather than matching on
            # co-occurring words — gap honesty as an index property.
            return []
        candidates: dict[str, float] = defaultdict(float)
        assertive_hit: set[str] = set()
        for key in q_concepts | q_literals:
            df = len(self._postings.get(key, ()))
            if not df:
                continue
            idf = math.log(1.0 + self._doc_count / df)
            for sig_id in self._postings[key]:
                if gate_literals and not (gate_literals & self._sig_concepts[sig_id]):
                    continue
                # Assertive occurrences (declarative sentences) outweigh mere
                # mentions in questions — records that STATE things about the
                # asked-about entity rank above records that ASK about it.
                if sig_id in self._assertive.get(key, ()):
                    assertive_hit.add(sig_id)
                    candidates[sig_id] += idf * 2.0
                else:
                    candidates[sig_id] += idf
        # "Questions don't assert" at the index: a record that only MENTIONS the
        # query's concepts inside a question (a stored prompt / prior query, or
        # the current query echoed into memory) states nothing and must never be
        # returned as a fact answer. Keep only records with >=1 assertive match.
        # (If nothing asserts — a corpus of only questions — fall back to all, so
        # the honest gap path still runs rather than a hard crash.)
        answerable = {s: sc for s, sc in candidates.items() if s in assertive_hit}
        ranked = answerable or candidates
        return [sid for sid, _ in sorted(ranked.items(), key=lambda kv: -kv[1])[:limit]]

    def observe(
        self,
        query: str,
        visible_signatures: list,
        actual_result_ids: list[str],
        limit: int = 8,
    ) -> dict:
        """Index visible signatures (cached), run concept retrieval, log the diff."""
        if not self.loaded:
            return {}
        shadow_ids = self.concept_hits(query, visible_signatures, limit=limit)
        q_concepts, q_literals = self.encode(query)

        actual = set(actual_result_ids)
        shadow = set(shadow_ids)
        report = {
            "query": query[:300],
            "query_concepts": len(q_concepts),
            "query_literals": len(q_literals),
            "shadow_hits": shadow_ids,
            "agreement": sorted(actual & shadow),
            "shadow_only": sorted(shadow - actual),
            "actual_only": sorted(actual - shadow),
        }
        # Durable evidence sink (JIMS_CLL_SHADOW_LOG=<path>): append one JSON
        # line per observation so agreement analysis never depends on console
        # logger configuration. Failure here must never affect retrieval.
        sink = os.getenv("JIMS_CLL_SHADOW_LOG", "").strip()
        if sink:
            try:
                with open(sink, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(report, ensure_ascii=False) + "\n")
            except OSError:
                pass
        logger.info(
            "CLL shadow: concepts=%d literals=%d | shadow=%d actual=%d agree=%d shadow_only=%d actual_only=%d",
            len(q_concepts), len(q_literals), len(shadow), len(actual),
            len(actual & shadow), len(shadow - actual), len(actual - shadow),
        )
        return report


_shadow: ConceptShadowIndex | None = None


def shadow_enabled() -> bool:
    return os.getenv("JIMS_CONCEPT_INDEX", "off").strip().lower() == "shadow"


def index_enabled() -> bool:
    """JIMS_CONCEPT_INDEX=on: concept-index hits are MERGED into production
    retrieval (observe() still records the same evidence report)."""
    return os.getenv("JIMS_CONCEPT_INDEX", "off").strip().lower() == "on"


def get_shadow() -> ConceptShadowIndex:
    global _shadow
    if _shadow is None:
        _shadow = ConceptShadowIndex()
    return _shadow
