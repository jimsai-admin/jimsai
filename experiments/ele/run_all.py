"""ELE + Projection experiment suite — reproduces spec §2 rows 1-15 (M0).

Run:  .venv/Scripts/python.exe experiments/ele/run_all.py [seed ...]
Default seeds: 702945 1 4242 999999 (same convention as the CLL runs).

Statuses:
  PASS   — asserted property held.
  FAIL   — asserted property broke (nonzero exit).
  REPORT — measured honestly, no direction asserted (rows 2, 3, 7): equal-budget
           comparisons and purity numbers are evidence, not gates.

Anti-hardcoding: all vocabulary is seed-generated nonce (corpus.py); the
OBLIG threshold is derived from the FROZEN calibration seed and applied to
fresh-seed test corpora (E-Rule 2); results are written to results/.
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bridge_cll as B
import classify as CL
import corpus as C
import discovery as D
import ledger as L
import neural_baseline as NB
import render as R
from projection import Event, IncrementalView, SemanticLedger, current_view

DEFAULT_SEEDS = [702945, 1, 4242, 999999]


class Suite:
    def __init__(self, seed: int):
        self.seed = seed
        self.rows: list[tuple[str, str, str]] = []
        self.failed = False

    def record(self, rid: str, status: str, detail: str) -> None:
        self.rows.append((rid, status, detail))
        if status == "FAIL":
            self.failed = True
        print(f"  {rid:<4} {status:<6} {detail}")

    def check(self, rid: str, fn) -> None:
        try:
            detail = fn()
            self.record(rid, "PASS", detail)
        except AssertionError as e:
            self.record(rid, "FAIL", str(e))

    def report(self, rid: str, fn) -> None:
        try:
            self.record(rid, "REPORT", fn())
        except AssertionError as e:
            self.record(rid, "FAIL", str(e))


def _kmeans_purity(words: list[str], features: np.ndarray, truth: dict[str, str],
                   k: int, seed: int) -> tuple[float, dict[str, float]]:
    rng = np.random.default_rng(seed)
    norms = np.linalg.norm(features, axis=1, keepdims=True)
    X = features / np.clip(norms, 1e-9, None)
    centers = X[rng.choice(len(X), k, replace=False)]
    assign = np.zeros(len(X), dtype=int)
    for _ in range(25):
        dists = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        assign = dists.argmin(axis=1)
        for c in range(k):
            members = X[assign == c]
            centers[c] = members.mean(axis=0) if len(members) else X[rng.integers(len(X))]
    total_majority = 0
    per_cluster: dict[str, float] = {}
    for c in range(k):
        labels = [truth[words[i]] for i in range(len(words)) if assign[i] == c]
        if not labels:
            continue
        best = max(set(labels), key=labels.count)
        purity = labels.count(best) / len(labels)
        total_majority += labels.count(best)
        per_cluster[f"c{c}:{best}"] = round(purity, 2)
    return total_majority / len(words), per_cluster


def run_seed(seed: int, oblig_threshold: float) -> Suite:
    suite = Suite(seed)
    print(f"\n=== seed {seed} (OBLIG_THRESHOLD={oblig_threshold}) ===")
    rng = random.Random(seed + 99)

    g, sentences = C.generate(seed)
    token_lists = [s.tokens for s in sentences]
    verbs = [s.verb for s in sentences]

    # R15 guard first: the corpus must be able to exercise discovery at all.
    def r15():
        D.assert_not_vacuous(g, sentences)
        degenerate = []
        for verb in g.verbs_trans:
            frame = {"agent": g.agents[0], "verb": verb, "article": g.article,
                     "object": g.objects[0]}
            core = ("agent", "verb", "article", "object")
            for _ in range(20):
                degenerate.append(C.Sentence(C.realize(g, frame, core), verb, frame, core, ()))
        try:
            D.assert_not_vacuous(g, degenerate)
            raise AssertionError("vacuous corpus was not rejected")
        except D.VacuousTestError:
            pass
        real_n = len(D.promoted(D.mine_frames(token_lists)))
        degen_n = len(D.promoted(D.mine_frames([s.tokens for s in degenerate])))
        assert degen_n < 0.1 * real_n, f"degenerate corpus promoted {degen_n} vs real {real_n}"
        return (f"vacuous corpus rejected by guard; degenerate promotes {degen_n} "
                f"frames vs {real_n} on real corpus")
    suite.check("R15", r15)

    ledgers = D.mine_frames(token_lists, verbs)
    frames = D.promoted(ledgers)

    def r1():
        expected = D.expected_frames(g)
        found = expected & set(frames)
        recovery = len(found) / len(expected)
        assert recovery >= 0.9, f"recovery {recovery:.2f} < 0.9 ({expected - found})"
        return f"construction recovery {len(found)}/{len(expected)} from raw n-grams"
    suite.check("R1", r1)

    def p0():
        tail_ledger = ledgers[(g.loc_mark, "%")]
        shuffled = L.EvidenceLedger(list(tail_ledger.observations))
        rng.shuffle(shuffled.observations)
        for fn in (L.count, L.filler_diversity, L.cross_predicate_spread,
                   L.predicate_counts, L.confidence):
            assert fn(tail_ledger) == fn(shuffled), f"{fn.__name__} order-dependent"
        shuffled_sents = list(sentences)
        rng.shuffle(shuffled_sents)
        for tail in g.truth_tails:
            a, _ = CL.classify(tail, sentences, oblig_threshold)
            b, _ = CL.classify(tail, shuffled_sents, oblig_threshold)
            assert a == b, f"classification of {tail} order-dependent"
        return "ledger metrics and decisions invariant under insertion order"
    suite.check("P0", p0)

    def r2():
        g2, sents2 = C.generate(seed, with_adjectives=True)
        vocab = sorted({t for s in sents2 for t in s.tokens})
        vid = {w: i for i, w in enumerate(vocab)}
        words = g2.agents + g2.objects + g2.all_verbs + g2.adjectives
        feats = np.zeros((len(words), 2 * len(vocab)))
        widx = {w: i for i, w in enumerate(words)}
        for s in sents2:
            for i, tok in enumerate(s.tokens):
                if tok in widx:
                    if i > 0:
                        feats[widx[tok], vid[s.tokens[i - 1]]] += 1
                    if i + 1 < len(s.tokens):
                        feats[widx[tok], len(vocab) + vid[s.tokens[i + 1]]] += 1
        overall, per = _kmeans_purity(words, feats, g2.categories, 4, seed)
        assert overall >= 0.6, f"clustering collapsed: purity {overall:.2f}"
        return f"distributional category purity {overall:.2f} {per} (leakage expected)"
    suite.report("R2", r2)

    split = int(0.8 * len(token_lists))
    lm = NB.lm_comparison(token_lists[:split], token_lists[split:], seed)

    def r3():
        return (f"equal-budget: ledger ppl {lm['ledger_ppl']} "
                f"({lm['ledger_constructions']} constructions) vs neural ppl "
                f"{lm['neural_ppl']} ({lm['neural_params']} params) — regime note: "
                "this grammar is near-trigram-deterministic; the original row-3 "
                "neural win was on natural-ish text")
    suite.report("R3", r3)

    def r4():
        assert lm["ledger_update_ms"] < lm["neural_retrain_s"] * 1000 / 100, (
            f"ledger update {lm['ledger_update_ms']}ms not ≪ retrain "
            f"{lm['neural_retrain_s']}s")
        return (f"ingest 100 new sentences: ledger {lm['ledger_update_ms']}ms vs "
                f"neural retrain {lm['neural_retrain_s']}s")
    suite.check("R4", r4)

    def r5():
        led = SemanticLedger()
        led.append(Event("findings", "class", "reptiles", "srcA", 0.9, 1))
        t0 = time.perf_counter()
        led.append(Event("findings", "class", "mammals", "srcB", 0.4, 2))
        latest = current_view(led, policy="latest")[("findings", "class")]
        correction_ms = (time.perf_counter() - t0) * 1000
        assert latest.value == "mammals" and latest.contradictions == ["reptiles"]
        assert len(latest.provenance) == 2 and len(led.events) == 2
        trusted = current_view(led, policy="highest_trust")[("findings", "class")]
        assert trusted.value == "reptiles", "policy is a view parameter, not a rewrite"
        inc = IncrementalView()
        led2 = SemanticLedger()
        r = random.Random(seed)
        for i in range(300):
            e = Event(f"e{r.randrange(20)}", f"a{r.randrange(5)}", f"v{r.randrange(9)}",
                      f"s{r.randrange(6)}", r.random(), i,
                      kind="assert" if r.random() > 0.1 else "retract")
            led2.append(e)
            inc.apply(e)
        full = current_view(led2)
        assert {k: (c.value, c.contradictions) for k, c in full.items()} == \
               {k: (c.value, c.contradictions) for k, c in inc.view().items()}, \
               "incremental view diverged from full recomputation"
        return (f"both truths retained; resolution is a projection parameter "
                f"(latest→mammals, trust→reptiles); correction visible in "
                f"{correction_ms:.2f}ms; incremental == full on 300 events")
    suite.check("R5", r5)

    clean = [s for s in sentences if "dist" not in s.adjunct_roles]
    pairs = [(s.frame, s.core_roles, s.adjunct_roles, s.tokens) for s in clean]
    renderer = R.Renderer.learn(pairs)
    combos = C.held_out_pairs(g, sentences, rng)

    def r6():
        halluc, mismatch = 0, 0
        for frame, core, truth in combos:
            out = renderer.render(frame, core)
            halluc += bool(renderer.hallucinated_tokens(out, frame))
            mismatch += out != truth
        assert halluc == 0 and mismatch == 0, f"halluc={halluc} mismatch={mismatch}"
        return f"{len(combos)}/{len(combos)} held-out compositional combos exact, 0 hallucinations"
    suite.check("R6", r6)

    def r7():
        vocab = NB._vocab(token_lists)
        no_adj = [s for s in clean if not s.adjunct_roles]
        nr = NB.TinyNeuralRenderer(vocab, seed)
        nr.train([s.frame for s in no_adj], [s.tokens for s in no_adj],
                 epochs=60, seed=seed)
        halluc, examples = 0, []
        for frame, _core, _truth in combos:
            out = nr.render(frame)
            bad = [t for t in out if t not in set(frame.values()) | {"."}]
            if bad:
                halluc += 1
                if len(examples) < 1:
                    examples.append(f"{bad[0]!r} in {' '.join(out)!r}")
        note = f" e.g. {examples[0]}" if examples else " (none this seed — existence claim is seed-dependent)"
        return (f"neural renderer ({nr.n_params} params): {halluc}/{len(combos)} "
                f"held-out renders contain unlicensed tokens;{note} "
                f"template renderer: 0 by construction")
    suite.report("R7", r7)

    def r8():
        holdout = g.verbs_ditrans[-1]
        sub = [(f, c, a, t) for (f, c, a, t) in pairs if f["verb"] != holdout]
        r8_renderer = R.Renderer.learn(sub)
        frame = {"agent": g.agents[0], "verb": holdout, "recipient": g.agents[1],
                 "article": g.article, "object": g.objects[0]}
        core = ("agent", "verb", "recipient", "article", "object")
        out = r8_renderer.render(frame, core)
        assert out == C.realize(g, frame, core), f"got {out}"
        return f"never-trained predicate {holdout!r} rendered via known ditransitive shape"
    suite.check("R8", r8)

    frame5 = {"agent": g.agents[2], "verb": g.verbs_trans[0], "article": g.article,
              "object": g.objects[1], "location": g.locations[0]}
    roles5 = ("agent", "verb", "article", "object", "location")

    def r9():
        try:
            renderer.render_monolithic(frame5, roles5)
            raise AssertionError("unseen 5-role shape did not raise GapReport")
        except R.GapReport:
            pass
        naive = renderer.render_nearest_naive(frame5, roles5)
        assert frame5["location"] not in naive, "naive fallback kept the location?"
        return ("unseen 5-role shape → typed GapReport; naive nearest-shape "
                f"fallback silently dropped {frame5['location']!r} — the failure "
                "the gap policy forbids")
    suite.check("R9", r9)

    def r10():
        out = renderer.render(frame5, roles5)
        truth = C.realize(g, frame5, ("agent", "verb", "article", "object"), ("location",))
        assert out == truth, f"{out} != {truth}"
        return "same 5-role frame renders correctly as known core + learned adjunct"
    suite.check("R10", r10)

    tails = {t: CL.classify(t, sentences, oblig_threshold) for t in g.truth_tails}

    def r11():
        obj_tail = (g.article, "%")
        stats = tails[obj_tail][1]
        assert stats["spread"] >= CL.SPREAD_THRESHOLD, "object slot lacks spread?"
        assert tails[obj_tail][0] == C.CORE, f"conjunctive said {tails[obj_tail][0]}"
        return (f"object slot spread={stats['spread']} — spread-only would accept "
                "it as adjunct (the row-11 trap); obligatoriness rejects it: CORE")
    suite.check("R11", r11)

    def r12():
        ranking = sorted(g.truth_tails, key=lambda t: -CL.spread_weighted(t, sentences))
        top = ranking[0]
        assert top == (g.dist_mark, "%"), f"distractor not #1 under spread_weighted: {ranking}"
        assert tails[top][0] == C.VERB_TIED, f"conjunctive said {tails[top][0]}"
        return ("verb-tied distractor ranks #1 under concentration-amplifying "
                "spread_weighted (the row-12 bug shape); conjunctive criteria: VERB_TIED")
    suite.check("R12", r12)

    def r13():
        man_tail = (g.man_mark, "%")
        decision, stats = tails[man_tail]
        peak = max(stats["obligatoriness"].values())
        loose, _ = CL.classify(man_tail, sentences, 0.90)
        assert loose == C.CORE, "0.90 threshold did not misclassify the edge case"
        assert decision == C.ADJUNCT, f"calibrated threshold said {decision}"
        assert 0.92 < oblig_threshold <= 1.0
        for tail, truth in g.truth_tails.items():
            assert tails[tail][0] == truth, f"{tail}: {tails[tail][0]} != {truth}"
        return (f"0.92-collocated adjunct (peak oblig {peak:.3f}): threshold 0.90 "
                f"→ CORE (misclassified); calibrated {oblig_threshold} → ADJUNCT; "
                "all 5 ground-truth tails classified correctly")
    suite.check("R13", r13)

    def r13b():
        two_verb = [s for s in sentences
                    if s.verb not in (g.preferred_verb,)
                    and not (s.verb in g.verbs_trans and "manner" in s.adjunct_roles)]
        early, _ = CL.classify((g.man_mark, "%"), two_verb, oblig_threshold)
        assert early in ("UNPROVEN", C.VERB_TIED), f"sparse adjunct accepted early: {early}"
        late, _ = CL.classify((g.man_mark, "%"), sentences, oblig_threshold)
        assert late == C.ADJUNCT
        return (f"adjunct with insufficient verb spread rejected ({early}); "
                "flips to ADJUNCT when more evidence arrives — no code change")
    suite.check("R13b", r13b)

    def r14():
        gm, morph_lists, truth = C.generate_morph(seed)
        candidates = CL.mine_suffixes(morph_lists)
        assert gm.loc_suffix in candidates, "true suffix not among mined candidates"
        buggy = CL.generalize_suffix(morph_lists, gm.loc_suffix, collapse=False)
        fixed = CL.generalize_suffix(morph_lists, gm.loc_suffix, collapse=True)
        bp, br = CL.precision_recall(buggy, truth)
        fp, fr = CL.precision_recall(fixed, truth)
        assert (bp, br) == (0.0, 0.0), f"buggy grouping unexpectedly scored {bp}/{br}"
        assert fr == 1.0 and fp >= 0.99, f"fixed grouping scored P{fp}/R{fr}"
        return (f"base-glued tail keys: P/R 0.0/0.0 regardless of algorithm "
                f"(the row-14 bug); collapsed key: P/R {fp:.2f}/{fr:.2f}")
    suite.check("R14", r14)

    def bridge():
        graph = B.ConceptGraph(transitive={"causes": 0.9})
        a, b_, c_node, d = g.agents[0], g.objects[0], g.objects[1], g.objects[2]
        amb = B.AmbiguitySet([
            B.CandidateFrame({"agent": a, "verb": "causes", "object": b_}, 0.8, "ele:c1"),
            B.CandidateFrame({"agent": a, "verb": "causes", "object": d}, 0.4, "ele:c2"),
        ])
        added = B.frames_to_graph(graph, amb)
        assert len(added) == 2, "ambiguity set must be recorded whole (recall-first)"
        graph.add(b_, "causes", c_node, 0.9, "ele:c3")
        paths = graph.infer(a, "causes", c_node)
        assert paths and paths[0][1] < 0.8, "multi-hop confidence must compound DOWN"
        e, f_, h = g.agents[1], g.agents[2], g.agents[3]
        graph.add(e, "chases", f_, 1.0, "ele:c4")
        graph.add(f_, "chases", h, 1.0, "ele:c5")
        assert graph.infer(e, "chases", h) == [], "non-composable predicate chained"
        assert graph.infer(e, "chases", f_), "single hop must still answer"
        audit = B.resolve_candidate(graph, amb.candidates[1])
        assert len(audit) == 1 and graph.infer(a, "causes", d) == []
        return ("ambiguity set recorded whole; multi-hop compounds down "
                f"({paths[0][1]}); non-composable refused; correction returned "
                "audit edges")
    suite.check("BRG", bridge)

    return suite


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp1252 console
    seeds = [int(a) for a in sys.argv[1:]] or DEFAULT_SEEDS

    cal_g, cal_sentences = C.generate(CL.FROZEN_CALIBRATION_SEED)
    oblig_threshold = CL.calibrate_oblig_threshold(cal_sentences, cal_g)
    print(f"OBLIG_THRESHOLD = {oblig_threshold} "
          f"(derived from frozen calibration seed {CL.FROZEN_CALIBRATION_SEED}, "
          "locked for all test seeds)")

    any_failed = False
    all_results = {}
    for seed in seeds:
        suite = run_seed(seed, oblig_threshold)
        any_failed |= suite.failed
        all_results[seed] = [(r, s, d) for r, s, d in suite.rows]

    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    (out / "run_results.json").write_text(
        json.dumps({"oblig_threshold": oblig_threshold, "seeds": all_results},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    n_pass = sum(1 for rows in all_results.values() for _, s, _ in rows if s == "PASS")
    n_fail = sum(1 for rows in all_results.values() for _, s, _ in rows if s == "FAIL")
    n_rep = sum(1 for rows in all_results.values() for _, s, _ in rows if s == "REPORT")
    print(f"\n{'FAILED' if any_failed else 'ALL PASS'}: "
          f"{n_pass} pass / {n_rep} report / {n_fail} fail across {len(seeds)} seeds")
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
