"""Minimal STAND-IN for the incremental grounded prose absorber (no LLM).

The real `grounded_prose_absorber_incremental.py` from the parallel work is NOT
present in this repo (searched by name/glob/content — absent). This is a minimal,
language-agnostic re-implementation of the DESCRIBED interface so the integration
experiment is real and falsifiable, not speculative. It is deliberately small and
honest — swap in the real file when it lands; the experiment harness only depends
on the two documented methods.

Interface (as described): streaming ingestion with statistics queryable at any time.
  ingest_document(text)      — update unigram/bigram/context counters incrementally
  get_current_signatures()   — PMI collocations, statistical pivot markers, counts
  predict_next(prev)         — bigram→unigram backoff prior (the search-prior hook)

Everything is distributional and provenance-free of hardcoded English rules: the
tokenizer keeps words, numbers, and individual punctuation (so code operators count),
and "pivot markers" are discovered as high-frequency, high-context-diversity tokens
(the language-universal relation-proxy idea), never a word list.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_TOK = re.compile(r"\w+|[^\w\s]")


def tokenize(text: str) -> list[str]:
    """Language-agnostic: words, numbers, and single punctuation tokens."""
    return _TOK.findall(text or "")


class GroundedProseAbsorberIncremental:
    def __init__(self) -> None:
        self.docs = 0
        self.tokens = 0
        self.uni: Counter[str] = Counter()
        self.bi: Counter[tuple[str, str]] = Counter()
        self.next_by_prev: dict[str, Counter] = defaultdict(Counter)  # O(1) next-token prior
        self.left_ctx: dict[str, set[str]] = defaultdict(set)   # for pivot diversity
        self.right_ctx: dict[str, set[str]] = defaultdict(set)

    # ── streaming ingestion ───────────────────────────────────────────────
    def ingest_document(self, text: str) -> None:
        toks = tokenize(text)
        if not toks:
            return
        self.docs += 1
        self.tokens += len(toks)
        self.uni.update(toks)
        for a, b in zip(toks, toks[1:]):
            self.bi[(a, b)] += 1
            self.next_by_prev[a][b] += 1
            self.left_ctx[b].add(a)
            self.right_ctx[a].add(b)

    # ── queryable statistics (any time) ───────────────────────────────────
    def pmi(self, a: str, b: str) -> float:
        nab = self.bi[(a, b)]
        if nab == 0 or self.tokens == 0:
            return float("-inf")
        # P(a,b) over bigrams; P(a),P(b) over unigrams
        n_bi = max(1, self.tokens - self.docs)          # #bigram slots
        p_ab = nab / n_bi
        p_a = self.uni[a] / self.tokens
        p_b = self.uni[b] / self.tokens
        return math.log(p_ab / (p_a * p_b)) if p_a and p_b else float("-inf")

    def collocations(self, top: int = 12, min_count: int = 3) -> list[tuple[str, str, float]]:
        out = [(a, b, round(self.pmi(a, b), 2)) for (a, b), c in self.bi.items() if c >= min_count]
        out.sort(key=lambda t: -t[2])
        return out[:top]

    def pivot_markers(self, top: int = 10, min_count: int = 5) -> list[tuple[str, int]]:
        """High-frequency, high-context-diversity tokens — language-universal
        relation proxies (operators/keywords in code, function words in prose)."""
        scored = []
        for t, c in self.uni.items():
            if c >= min_count:
                diversity = len(self.left_ctx[t]) + len(self.right_ctx[t])
                scored.append((t, diversity))
        scored.sort(key=lambda x: -x[1])
        return scored[:top]

    def predict_next(self, prev: str) -> str | None:
        """Bigram MLE with unigram backoff — the search-prior hook. O(1)."""
        d = self.next_by_prev.get(prev)
        if d:
            return d.most_common(1)[0][0]
        return self.uni.most_common(1)[0][0] if self.uni else None

    def next_dist(self, prev: str) -> Counter:
        """Full next-token distribution given prev (for ranked search priors). O(1)."""
        return self.next_by_prev.get(prev) or Counter(dict(self.uni))

    def get_current_signatures(self) -> dict:
        return {
            "docs": self.docs, "tokens": self.tokens, "vocab": len(self.uni),
            "top_collocations": self.collocations(),
            "pivot_markers": self.pivot_markers(),
        }

    def diagnostics(self) -> dict:
        return {"docs": self.docs, "tokens": self.tokens, "vocab": len(self.uni),
                "bigrams": len(self.bi)}
