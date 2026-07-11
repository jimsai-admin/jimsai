"""Falsifiable: does AST-structural absorption shrink synthesis search? (no LLM)

Re-runs the held-out prediction test with the AST-aware absorber (statement-type
context) vs the token-bigram baseline vs uniform, on real repo Python. Reports the
parsed-vs-fallback split (the messy/low-resource honesty), and runs one candidate
through candidate_bridge to the execution verifier.

Success bar (agreed, modest): mean search rank < 0.5× uniform AND ≥1 mined candidate
passes execution-verification through the bridge. Anything less is reported plainly.

Run: .venv/Scripts/python.exe experiments/absorber/run_absorber_ast_experiment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ast_absorber import AstAwareAbsorber                              # noqa: E402
from candidate_bridge import extract_candidates, promote              # noqa: E402
from run_bridge_messy import DOCS as MESSY_DOCS                        # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
MESSY = ["def broken(::: garbage ;;;", "%%% not python at all %%%"]   # force fallback demo


def gather() -> list[Path]:
    files, seen = [], set()
    for pat in ("prototype/jimsai/*.py", "experiments/**/*.py"):
        for f in sorted(ROOT.glob(pat)):
            if f.name not in seen and "absorber" not in str(f):
                seen.add(f.name); files.append(f)
    return files[:48]


def evaluate(ab: AstAwareAbsorber, held: list[Path]):
    """FAIR rank = position of the true token when candidates are ordered by an
    INTERPOLATED backoff score (how a real backoff LM ranks), not strict
    ctx-first concatenation (which unfairly penalised the sparse AST context)."""
    import bisect
    total_tok = sum(ab.uni.values()) or 1
    p_uni = {t: c / total_tok for t, c in ab.uni.items()}
    asc = sorted(p_uni.values())                       # ascending, for threshold counts
    V = max(1, len(p_uni))

    def interp_rank(actual, dists, lu):
        boosted = set()
        for _w, d, _s in dists:
            boosted |= set(d)

        def score(t):
            s = lu * p_uni.get(t, 0.0)
            for w, d, cs in dists:
                if cs:
                    s += w * d.get(t, 0) / cs
            return s
        sa = score(actual)
        higher = sum(1 for t in boosted if t != actual and score(t) > sa)
        thr = sa / lu if lu else 0.0               # non-boosted beat actual iff p_uni > thr
        above = len(asc) - bisect.bisect_right(asc, thr)
        boosted_above = sum(1 for t in boosted if p_uni.get(t, 0.0) > thr)
        return 1 + higher + max(0, above - boosted_above)

    hit_ast = hit_bi = total = 0
    r_ast = r_bi = r_uni = 0
    for f in held:
        src = f.read_text(encoding="utf-8", errors="ignore")
        toks = ab._tokens(src)
        stmt = ab._line_stmt(src) or {}
        if not toks:
            continue
        for (_l1, prev), (l2, actual) in zip(toks, toks[1:]):
            total += 1
            st = stmt.get(l2, "Module")
            ctx_d = ab.ctx.get((st, prev), {})
            bi_d = ab.bi.get(prev, {})
            cs = sum(ctx_d.values()); bs = sum(bi_d.values())
            hit_ast += int(ab.predict_next(st, prev) == actual)
            hit_bi += int(bool(bi_d) and max(bi_d, key=bi_d.get) == actual)
            r_ast += interp_rank(actual, [(0.6, ctx_d, cs), (0.3, bi_d, bs)], 0.1)
            r_bi += interp_rank(actual, [(0.7, bi_d, bs)], 0.3)
            r_uni += interp_rank(actual, [], 1.0)
    n = max(1, total)
    return {"acc_ast": hit_ast / n, "acc_bi": hit_bi / n,
            "rank_ast": r_ast / n, "rank_bi": r_bi / n, "rank_uni": r_uni / n, "V": V}


def main() -> int:
    files = gather()
    held = files[::5]
    train = [f for f in files if f not in held]

    ab = AstAwareAbsorber()
    for f in train:
        ab.ingest_code(f.read_text(encoding="utf-8", errors="ignore"))
    for m in MESSY:                              # show graceful fallback on unparseable
        ab.ingest_code(m)

    print("=" * 84)
    print("Does AST-structural absorption shrink synthesis search? — real repo Python, held-out")
    print("-" * 84)
    print(f"train {len(train)} files (+{len(MESSY)} messy) | held-out {len(held)}")
    print(f"parsed as AST: {ab.parsed}/{ab.docs} docs | fell back to tokens: {ab.fell_back} "
          f"(messy/low-resource → fallback, AST benefit degrades gracefully)")

    m = evaluate(ab, held)
    print(f"\ntop-1 accuracy : AST-context {m['acc_ast']:.1%}  vs bigram {m['acc_bi']:.1%}")
    print(f"mean search rank: AST-context {m['rank_ast']:.1f}  bigram {m['rank_bi']:.1f}  "
          f"uniform {m['rank_uni']:.1f}  (vocab {m['V']})")
    ratio = m["rank_ast"] / m["rank_uni"]
    print(f"AST mean rank is {ratio:.2f}× uniform  (bar: < 0.50×)  → "
          f"{'CLEARS' if ratio < 0.5 else 'MISSES'} the bar")
    print(f"AST vs bigram rank: {m['rank_ast']:.0f} vs {m['rank_bi']:.0f}  "
          f"({'AST better' if m['rank_ast'] < m['rank_bi'] else 'no gain over bigram'})")

    # ≥1 execution-verified candidate through the bridge
    res = promote(extract_candidates(MESSY_DOCS))
    verified = len(res["ledger"])
    print(f"\nbridge: {verified} candidate(s) execution-verified and ledger-eligible "
          f"({', '.join(c.name for c in res['ledger'])})")

    clears_rank = ratio < 0.5
    ok = clears_rank and verified >= 1
    print("-" * 84)
    print("HONEST READ:")
    print(f"  • structural context {'DOES' if m['rank_ast'] < 0.9 * m['rank_bi'] else 'does NOT'} beat token bigrams "
          f"(rank {m['rank_ast']:.0f} vs {m['rank_bi']:.0f})")
    print(f"  • {'CLEARS' if clears_rank else 'MISSES'} the <0.5× uniform bar for real synthesis-search reduction")
    print("  • still only PROPOSES candidates — verification (the bridge gate) remains the blocker's answer")
    print("  • degrades to tokens on unparseable/low-resource code (fallback count above)")
    print("VERDICT:", "PASS — AST context meaningfully shrinks search AND a candidate verifies through the bridge"
          if ok else "PARTIAL/HONEST-NEGATIVE — see numbers; structural helps candidate proposal but "
          f"{'did not clear the search-reduction bar' if not clears_rank else 'bridge produced no verified unit'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
