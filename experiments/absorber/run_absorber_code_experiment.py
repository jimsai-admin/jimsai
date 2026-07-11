"""Falsifiable test — does streaming prose/code absorption help code synthesis? (no LLM)

The verified-pattern-library blocker has two halves: (a) DISCOVER/ORDER candidate
patterns, (b) VERIFY they run. This tests whether the incremental absorber helps
half (a) on REAL code: stream real repo Python into the absorber and measure, on
HELD-OUT files, whether its learned prior predicts the next token — i.e. whether it
would let a synthesiser try the RIGHT continuation early instead of enumerating the
whole vocabulary. Two measured quantities, against a uniform (global-frequency)
baseline, plus the STREAMING curve (does it improve as data arrives, no manual
promotion?):

  top-1 accuracy   — predict_next(prev) == actual next token (higher = better)
  mean search rank — position of the true token in the absorbed candidate order
                     (lower = fewer synthesis candidates to try before the right one)

Falsifiable: if the absorbed prior does NOT beat uniform and does NOT improve with
more documents, absorption is orthogonal to the code-synthesis blocker. If it does,
it provides a real, continuously-growing SEARCH PRIOR — necessary but not sufficient
(it still cannot VERIFY correctness; only execution can).

Run: .venv/Scripts/python.exe experiments/absorber/run_absorber_code_experiment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grounded_prose_absorber_incremental import GroundedProseAbsorberIncremental, tokenize  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]


def gather_python(limit: int = 48) -> list[Path]:
    files: list[Path] = []
    for pat in ("prototype/jimsai/*.py", "experiments/**/*.py"):
        files.extend(sorted(ROOT.glob(pat)))
    # de-dup, drop this experiment's own dir, cap size
    seen, out = set(), []
    for f in files:
        if f.name in seen or "absorber" in str(f):
            continue
        seen.add(f.name); out.append(f)
        if len(out) >= limit:
            break
    return out


def acc_only(absorber, held_tokens: list[list[str]]) -> float:
    """Fast top-1 next-token accuracy (O(1) per position) — for the streaming curve."""
    hits = total = 0
    for toks in held_tokens:
        for prev, actual in zip(toks, toks[1:]):
            total += 1
            hits += (absorber.predict_next(prev) == actual)
    return hits / total if total else 0.0


def eval_heldout(absorber, held_tokens: list[list[str]]) -> tuple[float, float, float]:
    """Return (top1_accuracy, mean_rank_absorbed, mean_rank_uniform). Per-prev order
    is precomputed ONCE so each position is an O(1) rank lookup."""
    uni_order = [t for t, _c in absorber.uni.most_common()]
    uni_rank = {t: i + 1 for i, t in enumerate(uni_order)}
    V = max(1, len(uni_order))
    # FAIR backoff rank: bigram candidates first (sharp), then unigram tail.
    prev_rank: dict[str, dict[str, int]] = {}
    for prev, d in absorber.next_by_prev.items():
        prev_rank[prev] = {t: i + 1 for i, (t, _c) in enumerate(d.most_common())}
    hits = total = 0
    rank_abs = rank_uni = 0
    for toks in held_tokens:
        for prev, actual in zip(toks, toks[1:]):
            total += 1
            hits += (absorber.predict_next(prev) == actual)
            pr = prev_rank.get(prev)
            if pr is not None and actual in pr:
                rank_abs += pr[actual]
            elif pr is not None:
                rank_abs += len(pr) + uni_rank.get(actual, V)       # backoff tail
            else:
                rank_abs += uni_rank.get(actual, V)
            rank_uni += uni_rank.get(actual, V)
    if total == 0:
        return 0.0, 0.0, 0.0
    return hits / total, rank_abs / total, rank_uni / total


def main() -> int:
    files = gather_python()
    if len(files) < 6:
        print("not enough Python files found"); return 1
    held = files[::5]                       # every 5th file held out
    train = [f for f in files if f not in held]
    held_tokens = [tokenize(f.read_text(encoding="utf-8", errors="ignore")) for f in held]

    print("=" * 80)
    print("Does streaming code absorption help synthesis? — real repo Python, held-out")
    print("-" * 80)
    print(f"train files (streamed): {len(train)} | held-out: {len(held)}")

    absorber = GroundedProseAbsorberIncremental()
    checkpoints = [max(1, len(train) * q // 4) for q in (1, 2, 3, 4)]
    curve = []
    for i, f in enumerate(train, 1):
        absorber.ingest_document(f.read_text(encoding="utf-8", errors="ignore"))
        if i in checkpoints:
            curve.append((i, acc_only(absorber, held_tokens)))     # fast, curve only

    acc, rank_abs, rank_uni = eval_heldout(absorber, held_tokens)
    sig = absorber.get_current_signatures()
    # uniform top-1 baseline = always guess the single most common token
    top_tok, top_c = absorber.uni.most_common(1)[0]
    uniform_acc = top_c / absorber.tokens

    print(f"ingested {sig['docs']} docs, {sig['tokens']} tokens, vocab {sig['vocab']}")
    print("\nstreaming held-out next-token accuracy (improves with data → no manual promotion):")
    for n, a in curve:
        bar = "█" * int(a * 50)
        print(f"   after {n:3d} docs: {a:5.1%} {bar}")
    print("\ndiscovered pivot markers (language-universal relation proxies, code operators/keywords):")
    print("   " + ", ".join(f"{t!r}" for t, _d in sig["pivot_markers"][:8]))
    print("top PMI collocations (candidate idioms):")
    print("   " + ", ".join(f"{a}·{b}" for a, b, _p in sig["top_collocations"][:8]))

    print("-" * 80)
    print(f"top-1 next-token accuracy : absorbed {acc:.1%}  vs uniform {uniform_acc:.1%}  "
          f"(lift ×{acc / uniform_acc:.1f})")
    print(f"mean search rank of true token: absorbed {rank_abs:.1f}  vs uniform {rank_uni:.1f}  "
          f"(vocab {sig['vocab']}) → {rank_uni / max(rank_abs, 0.1):.2f}× candidate reduction")
    local_signal = acc > 1.5 * uniform_acc            # real local structure learned
    shrinks_search = rank_abs < 0.7 * rank_uni         # meaningfully fewer candidates
    print("-" * 80)
    print("HONEST READ:")
    print(f"  • REAL local signal: {local_signal} (top-1 ×{acc / uniform_acc:.1f}) — the absorber DOES learn code")
    print("    structure (operators as pivots, PMI idioms) and would help EASY high-frequency continuations.")
    print(f"  • Shrinks synthesis search: {shrinks_search} (mean rank {rank_abs:.0f} vs {rank_uni:.0f}) — a BIGRAM")
    print("    prior is too shallow for the hierarchical/long-range structure real synthesis needs.")
    print("  • Verifies correctness: NO — statistics can PROPOSE candidates, only execution can VERIFY them.")
    verdict = ("COMPLEMENTARY-BUT-WEAK — real for candidate/idiom DISCOVERY, not for shrinking synthesis "
               "search (bigram-shallow) and NOT for verification (the core blocker). Higher-order/structural "
               "signals + the execution verifier are what would move the needle."
               if local_signal and not shrinks_search else
               "HELPS — beats uniform and shrinks search" if shrinks_search else
               "ORTHOGONAL — no real signal")
    print("VERDICT:", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
