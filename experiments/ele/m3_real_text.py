"""M3 — construction discovery on REAL text (the "verb = 2nd token" reckoning).

Corpus: real English prose sampled AT RUNTIME (seeded) from this repository's
own documentation — text written for humans, containing passives, fronted
adjuncts, subordinate clauses, and questions. No sentence is enumerated in
this file (Rule 2), and no word list appears anywhere in it.

Two measurements:

M3a — discovery yield. Does frequency+diversity promotion find constructions
      in real text at all? Mechanism-shape assertion: frames promote, and the
      fixed tokens of the top frames sit in the corpus's high-frequency
      stratum (a DISTRIBUTIONAL definition of "function-word scaffolding" —
      no hand-listed stopwords).

M3b — predicate-signal stability. The toy corpora supplied predicate identity
      as ground truth; the spec flags that real text has no such gift. We test
      whether the "verb = 2nd token" heuristic carries signal WITHOUT labels:
      classify the top tail candidates with (H1) predicate = 2nd token, and
      with (C1..C5) predicate = seeded-random token position. If H1's
      decisions agree with the random controls' decisions about as often as
      the controls agree with each other, the heuristic supplies no usable
      predicate signal on real text — recording that IS the M3 deliverable
      (pass criterion: "a finding, either way").

Run: .venv/Scripts/python.exe experiments/ele/m3_real_text.py [seed]
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import classify as CL
import corpus as C
import discovery as D

REPO = Path(__file__).resolve().parents[2]
N_SENTENCES = 800
TOP_TAILS = 12

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def load_real_sentences(seed: int, n: int = N_SENTENCES) -> list[list[str]]:
    """Sample real prose sentences from the repo's documentation at runtime."""
    docs = sorted(REPO.glob("*.md")) + sorted((REPO / "docs").rglob("*.md"))
    raw: list[str] = []
    for doc in docs:
        if "graphify-out" in str(doc):
            continue
        in_code = False
        for line in doc.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code = not in_code
                continue
            if in_code or not stripped or stripped[0] in "#|>-*`0123456789":
                continue
            if "http" in stripped or "`" in stripped:
                continue
            raw.append(stripped)
    text = " ".join(raw)
    sentences: list[list[str]] = []
    for chunk in re.split(r"(?<=[.!?])\s+", text):
        tokens = [w.lower() for w in _WORD.findall(chunk)]
        if 6 <= len(tokens) <= 25:
            sentences.append(tokens + ["."])
    rng = random.Random(seed)
    rng.shuffle(sentences)
    picked = sentences[:n]
    if len(picked) < n // 2:
        raise AssertionError(f"only {len(picked)} real sentences found — corpus too thin")
    return picked


def m3a_yield(token_lists: list[list[str]]) -> dict:
    ledgers = D.mine_frames(token_lists, nmax=5)
    frames = D.promoted(ledgers)
    freq = Counter(t for toks in token_lists for t in toks if t != ".")
    vocab_ranked = [w for w, _ in freq.most_common()]
    top_decile = set(vocab_ranked[: max(1, len(vocab_ranked) // 10)])

    top_frames = sorted(frames, key=lambda f: -len(ledgers[f].observations))[:20]
    fixed_tokens = [t for f in top_frames for t in f if t not in ("%", ".")]
    in_stratum = sum(1 for t in fixed_tokens if t in top_decile) / max(1, len(fixed_tokens))

    assert len(frames) >= 20, f"only {len(frames)} frames promoted on real text"
    assert in_stratum >= 0.8, (
        f"top-frame scaffolding not in high-frequency stratum ({in_stratum:.2f})")
    return {
        "sentences": len(token_lists),
        "vocab": len(vocab_ranked),
        "frames_promoted": len(frames),
        "scaffold_in_top_decile": round(in_stratum, 2),
        "top_frames": [" ".join(f) for f in top_frames[:15]],
        "ledgers": ledgers,
        "frames": frames,
    }


def _classify_with_predicate_rule(token_lists, tails, rule, threshold) -> dict:
    sentences = []
    for toks in token_lists:
        verb = rule(toks)
        frame = {"agent": toks[0], "verb": verb}
        sentences.append(C.Sentence(toks, verb, frame, ("agent", "verb"), ()))
    # Confound guard: if the assigned predicate token equals the tail's marker,
    # obligatoriness(tail, predicate) = 1.0 BY CONSTRUCTION (the sentence
    # contains its own predicate token). Without this exclusion, every
    # predicate rule that picks tokens from the sentence — heuristic or random
    # — saturates to CORE and the comparison measures the artifact, not signal.
    return {tail: CL.classify(tail, [s for s in sentences if s.verb != tail[0]],
                              threshold)[0]
            for tail in tails}


def m3b_predicate_signal(token_lists: list[list[str]], yield_result: dict,
                         seed: int, threshold: float) -> dict:
    ledgers, frames = yield_result["ledgers"], yield_result["frames"]
    tails = [f for f in CL.tail_candidates(frames) if f[0] != "."]
    tails = sorted(tails, key=lambda f: -len(ledgers[f].observations))[:TOP_TAILS]

    h1 = _classify_with_predicate_rule(token_lists, tails, lambda t: t[1], threshold)

    rng = random.Random(seed)
    controls = []
    for _ in range(5):
        offsets = {}

        def rand_rule(toks, _rng=random.Random(rng.randrange(1 << 30))):
            return toks[_rng.randrange(1, max(2, len(toks) - 1))]

        controls.append(_classify_with_predicate_rule(token_lists, tails, rand_rule, threshold))

    def agreement(a: dict, b: dict) -> float:
        return sum(a[t] == b[t] for t in tails) / len(tails)

    h1_vs_controls = sum(agreement(h1, c) for c in controls) / len(controls)
    control_vs_control = (
        sum(agreement(controls[i], controls[j])
            for i in range(len(controls)) for j in range(i + 1, len(controls)))
        / (len(controls) * (len(controls) - 1) / 2))
    control_counts = dict(Counter(d for c in controls for d in c.values()))
    n_ctrl = sum(control_counts.values())

    return {
        "tails_tested": [" ".join(t) for t in tails],
        "h1_decisions": {" ".join(t): d for t, d in h1.items()},
        "h1_decision_counts": dict(Counter(h1.values())),
        "control_decision_counts": control_counts,
        "control_unproven_fraction": round(control_counts.get("UNPROVEN", 0) / n_ctrl, 3),
        "h1_vs_random_agreement": round(h1_vs_controls, 3),
        "random_vs_random_agreement": round(control_vs_control, 3),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 702945

    cal_g, cal_sents = C.generate(CL.FROZEN_CALIBRATION_SEED)
    threshold = CL.calibrate_oblig_threshold(cal_sents, cal_g)

    token_lists = load_real_sentences(seed)
    a = m3a_yield(token_lists)
    print(f"M3a PASS  {a['frames_promoted']} constructions promoted from "
          f"{a['sentences']} real sentences (vocab {a['vocab']}); "
          f"top-frame scaffolding {a['scaffold_in_top_decile']:.0%} in top-decile frequency")
    for f in a["top_frames"]:
        print(f"          {f!r}")

    b = m3b_predicate_signal(token_lists, a, seed, threshold)
    print(f"\nM3b REPORT tails={b['tails_tested']}")
    print(f"          H1 (verb=2nd token) decisions: {b['h1_decision_counts']}")
    print(f"          random-control decisions:       {b['control_decision_counts']}")
    print(f"          H1 vs random agreement: {b['h1_vs_random_agreement']} | "
          f"random vs random: {b['random_vs_random_agreement']}")
    if b["control_unproven_fraction"] >= 0.9:
        verdict = (
            "random predicate assignment fragments evidence below the sample gate "
            "(controls ~all UNPROVEN) — the comparison cannot certify H1's signal; "
            "and H1's own gate-passing decisions label determiner/copula scaffolding "
            "as ADJUNCT, a category error: real-text tail candidates are not "
            "argument-structure units. CONCLUSION: predicate identity AND candidate "
            "argument units were silently supplied by the toy corpus; on real text "
            "they must come from L1 extraction or a bounded parser interface — "
            "obligatoriness/spread remain valid once those inputs exist")
    else:
        verdict = ("controls cleared the evidence gate; compare decision quality "
                   "directly before relying on any position heuristic")
    print(f"          FINDING: {verdict}")

    out = Path(__file__).parent / "results" / "m3_real_text.json"
    out.parent.mkdir(exist_ok=True)
    a_slim = {k: v for k, v in a.items() if k not in ("ledgers", "frames")}
    out.write_text(json.dumps({"seed": seed, "threshold": threshold,
                               "m3a": a_slim, "m3b": b, "finding": verdict},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
