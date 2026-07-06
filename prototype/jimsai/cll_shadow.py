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
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    key = surface_key(row["surface"])
                    if key and row["concept"] not in self.surfaces[key]:
                        self.surfaces[key].append(row["concept"])
            self.loaded = True
            self._max_phrase = max((k.count(" ") + 1 for k in self.surfaces), default=1)
            self._max_cjk = max((len(k) for k in self.surfaces if _CJK_RUN.fullmatch(k)), default=4)
            logger.info("CLL shadow index loaded: %d surface keys from %s", len(self.surfaces), path)
        else:
            logger.warning("CLL shadow: lexicon not found at %s — shadow disabled", path)
        self._sig_concepts: dict[str, frozenset[str]] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._doc_count = 0

    # ── encoding ──

    def encode(self, text: str) -> tuple[set[str], set[str]]:
        """→ (concept ids, hard literal keys). No language argument by design."""
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
                sentence_initial: set[int] = set()
                pos = 0
                for sentence_match in re.finditer(r"[^.!?。？！]+", stripped):
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
                        name_like = any(ch.isdigit() for ch in raw) or (
                            any(ch.isupper() for ch in raw) and i not in sentence_initial
                        )
                        if name_like:
                            literals.add(f"L:{raw.lower()}")
                        i += 1
        return concepts, literals

    # ── shadow observation ──

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
        for sig in visible_signatures:
            sig_id = getattr(sig, "id", None)
            if sig_id is None or sig_id in self._sig_concepts:
                continue
            concepts, literals = self.encode(str(getattr(sig, "raw_excerpt", "") or ""))
            keys = frozenset(concepts | literals)
            self._sig_concepts[sig_id] = keys
            for key in keys:
                self._postings[key].add(sig_id)
            self._doc_count += 1

        q_concepts, q_literals = self.encode(query)
        candidates: dict[str, float] = defaultdict(float)
        for key in q_concepts | q_literals:
            df = len(self._postings.get(key, ()))
            if not df:
                continue
            idf = math.log(1.0 + self._doc_count / df)
            for sig_id in self._postings[key]:
                if q_literals and not (q_literals & self._sig_concepts[sig_id]):
                    continue
                candidates[sig_id] += idf
        shadow_ids = [sid for sid, _ in sorted(candidates.items(), key=lambda kv: -kv[1])[:limit]]

        actual = set(actual_result_ids)
        shadow = set(shadow_ids)
        report = {
            "query_concepts": len(q_concepts),
            "query_literals": len(q_literals),
            "shadow_hits": shadow_ids,
            "agreement": sorted(actual & shadow),
            "shadow_only": sorted(shadow - actual),
            "actual_only": sorted(actual - shadow),
        }
        logger.info(
            "CLL shadow: concepts=%d literals=%d | shadow=%d actual=%d agree=%d shadow_only=%d actual_only=%d",
            len(q_concepts), len(q_literals), len(shadow), len(actual),
            len(actual & shadow), len(shadow - actual), len(actual - shadow),
        )
        return report


_shadow: ConceptShadowIndex | None = None


def shadow_enabled() -> bool:
    return os.getenv("JIMS_CONCEPT_INDEX", "off").strip().lower() == "shadow"


def get_shadow() -> ConceptShadowIndex:
    global _shadow
    if _shadow is None:
        _shadow = ConceptShadowIndex()
    return _shadow
