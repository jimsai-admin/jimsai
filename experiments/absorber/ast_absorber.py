"""AST-aware absorber with graceful TOKEN FALLBACK (no LLM).

Token bigrams were measured too shallow to shrink synthesis search. This conditions
the next-token prior on STRUCTURAL context — the enclosing statement type from the
AST (If / Return / Assign / For / FunctionDef …) — which captures control/data-flow
regularities a bigram cannot. Honest constraint respected: when the source does NOT
parse (messy, minified, or a language with no lightweight parser), it FALLS BACK to
token bigrams. AST is never required; it is a bonus when available.

Expectations (kept modest, per the plan): this can only improve candidate PROPOSAL
(search prior), never verification. It degrades to the token result on unparseable
or low-resource input. It does not touch prose→spec, architecture, or taste.
"""

from __future__ import annotations

import ast
import io
import tokenize
from collections import Counter, defaultdict

_KEEP = {tokenize.NAME, tokenize.OP, tokenize.NUMBER, tokenize.STRING}


class AstAwareAbsorber:
    def __init__(self) -> None:
        self.docs = self.parsed = self.fell_back = 0
        self.uni: Counter[str] = Counter()
        self.bi: dict[str, Counter] = defaultdict(Counter)          # prev -> next (fallback)
        self.ctx: dict[tuple[str, str], Counter] = defaultdict(Counter)  # (stmt_type, prev) -> next

    def _tokens(self, source: str):
        out = []
        try:
            for t in tokenize.generate_tokens(io.StringIO(source).readline):
                if t.type in _KEEP:
                    out.append((t.start[0], t.string))
        except Exception:
            return None                         # messy-safe: unlexable → no tokens
        return out

    def _line_stmt(self, source: str):
        """Map each source line to its innermost enclosing statement type (or None
        if the source does not parse — the fallback trigger)."""
        try:
            tree = ast.parse(source)
        except Exception:
            return None
        m: dict[int, tuple[str, int]] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.stmt) and hasattr(n, "lineno"):
                end = getattr(n, "end_lineno", n.lineno)
                span = end - n.lineno
                for ln in range(n.lineno, end + 1):
                    if ln not in m or span < m[ln][1]:
                        m[ln] = (type(n).__name__, span)
        return {ln: t for ln, (t, _s) in m.items()}

    def ingest_code(self, source: str) -> None:
        self.docs += 1
        toks = self._tokens(source)
        if not toks:
            return
        self.uni.update(s for _l, s in toks)
        for (_l1, a), (_l2, b) in zip(toks, toks[1:]):
            self.bi[a][b] += 1                  # token bigram always (the fallback)
        stmt = self._line_stmt(source)
        if stmt is not None:
            self.parsed += 1
            for (_l1, a), (l2, b) in zip(toks, toks[1:]):
                self.ctx[(stmt.get(l2, "Module"), a)][b] += 1   # AST-conditioned
        else:
            self.fell_back += 1

    # ── prediction with backoff: ast-context → bigram → unigram ───────────
    def predict_next(self, stmt_type: str, prev: str):
        d = self.ctx.get((stmt_type, prev))
        if d:
            return d.most_common(1)[0][0]
        d = self.bi.get(prev)
        if d:
            return d.most_common(1)[0][0]
        return self.uni.most_common(1)[0][0] if self.uni else None

    def rank_maps(self):
        """Precompute rank lookups once (fast eval)."""
        ctx_rank = {k: {t: i + 1 for i, (t, _c) in enumerate(d.most_common())}
                    for k, d in self.ctx.items()}
        ctx_len = {k: len(d) for k, d in self.ctx.items()}
        bi_rank = {p: {t: i + 1 for i, (t, _c) in enumerate(d.most_common())}
                   for p, d in self.bi.items()}
        bi_len = {p: len(d) for p, d in self.bi.items()}
        uni_order = [t for t, _c in self.uni.most_common()]
        uni_rank = {t: i + 1 for i, t in enumerate(uni_order)}
        return ctx_rank, ctx_len, bi_rank, bi_len, uni_rank, max(1, len(uni_order))
