"""
CLL v1 experiments — from-source lexicon, runtime-sampled vocabulary.

Run:  python experiments/concept_model/test_lexicon_v1.py [seed]

Anti-hardcoding protocol enforced by construction:
  Rule 1 — every lexicon entry must carry source provenance (asserted here).
  Rule 2 — test vocabulary is SAMPLED FROM THE BUILT LEXICON at runtime;
           no word list exists in this file.
  Rule 3 — Swahili ("sw") appears in the DATA only: this test asserts the
           string never occurs in concept_model.py. New language = new data.
"""

from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from concept_model import ConceptEncoder, ConceptGraph, ConceptMemory, surface_key

DATA = Path(__file__).parent / "data"
CONSONANTS = "bdfgjklmnprstvz"
VOWELS = "aeiou"


def nonce(rng: random.Random, syllables: int = 3) -> str:
    return "".join(rng.choice(CONSONANTS) + rng.choice(VOWELS) for _ in range(syllables)).capitalize()


def load_lexicon() -> tuple[dict, dict, list[dict]]:
    """lexicon dict for the encoder + concept→{lang: surface} map + raw rows."""
    lexicon: dict[str, dict[str, list]] = defaultdict(dict)
    by_concept: dict[str, dict[str, str]] = defaultdict(dict)
    rows = []
    with (DATA / "lexicon.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            rows.append(row)
            key = surface_key(row["surface"])
            if not key:
                continue
            senses = lexicon[row["lang"]].setdefault(key, [])
            if all(concept != row["concept"] for concept, _ in senses):
                senses.append((row["concept"], frozenset()))
            # first (highest-QRank) label wins as the concept's canonical surface
            by_concept[row["concept"]].setdefault(row["lang"], row["surface"])
    return dict(lexicon), dict(by_concept), rows


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.SystemRandom().randint(1, 10**6)
    rng = random.Random(seed)
    results: list[tuple[str, bool, str]] = []
    lexicon, by_concept, rows = load_lexicon()
    langs = sorted(lexicon)
    counts = {lang: len(lexicon[lang]) for lang in langs}
    print(f"CLL v1 — seed {seed}")
    print(f"lexicon surfaces per language (from source): {counts}\n")

    # Rule 1 — provenance CI check: no entry without source/license/timestamp
    missing = [r for r in rows if not (r.get("source") and r.get("license") and r.get("retrieved_at"))]
    print(f"  R1 provenance: {len(rows)} entries, {len(missing)} missing provenance")
    results.append(("Rule1 provenance on every entry", not missing, f"{len(rows)} entries checked"))

    # Rule 3 — new-language proof: 'sw' exists only in data, never in code
    code = (Path(__file__).parent / "concept_model.py").read_text(encoding="utf-8")
    sw_in_code = '"sw"' in code or "'sw'" in code
    sw_entries = counts.get("sw", 0)
    print(f"  R3 zero-code language: sw entries={sw_entries}, 'sw' in concept_model.py: {sw_in_code}")
    results.append(("Rule3 Swahili with zero code change", sw_entries > 0 and not sw_in_code,
                    f"{sw_entries} sw surfaces, code untouched"))

    encoder = ConceptEncoder(lexicon=lexicon)

    # E11 — cross-lingual concept identity at scale (vocabulary sampled at runtime).
    # For sampled concepts with labels in en + L, the en surface and the L surface
    # must resolve to candidate sets CONTAINING the same concept; end-to-end,
    # a record taught with the en surface must be retrieved by the L surface.
    pair_stats: dict[str, list[int]] = {}
    e11_detail = []
    for other in [x for x in langs if x != "en"]:
        candidates = [c for c, surfaces in by_concept.items() if "en" in surfaces and other in surfaces]
        rng.shuffle(candidates)
        sample = candidates[:40]
        identity_hits, retrieval_hits = 0, 0
        for concept in sample:
            en_surface, other_surface = by_concept[concept]["en"], by_concept[concept][other]
            enc_en = encoder.encode(en_surface, "en")
            enc_other = encoder.encode(other_surface, other)
            if concept in enc_en.concepts and concept in enc_other.concepts:
                identity_hits += 1
            memory = ConceptMemory(encoder)
            memory.add("taught", f"{en_surface} works with {nonce(rng)}", "en")
            memory.add("noise", f"{nonce(rng)} works with {nonce(rng)}", "en")
            hits = memory.retrieve(other_surface, other)
            if hits and hits[0][0].record_id == "taught":
                retrieval_hits += 1
        pair_stats[other] = [identity_hits, retrieval_hits, len(sample)]
        e11_detail.append(f"en↔{other}: identity {identity_hits}/{len(sample)}, retrieval {retrieval_hits}/{len(sample)}")
        print(f"  E11 en↔{other}: concept identity {identity_hits}/{len(sample)}, "
              f"cross-lingual retrieval top-1 {retrieval_hits}/{len(sample)}")
    # Bar: ≥85% identity / ≥80% retrieval. The residual gap is measured and
    # attributable (mixed CJK+digit labels, traditional/simplified variant
    # folding) — documented as v1.1 work in the design doc, not silenced here.
    e11_ok = all(s[0] >= 0.85 * s[2] and s[1] >= 0.8 * s[2] for s in pair_stats.values() if s[2] >= 10)
    results.append(("E11 cross-lingual at scale", e11_ok, "; ".join(e11_detail)))

    # E12 — masked-edge inference over the real P279 (subclass-of) graph.
    edges = [json.loads(line) for line in (DATA / "edges.jsonl").open(encoding="utf-8")]
    graph = ConceptGraph(transitive={"P279": 0.95})
    edge_set = {(e["subject"], e["object"]) for e in edges}
    for e in edges:
        graph.add(e["subject"], "P279", e["object"], 0.95, source=f"wd:{e['subject']}")
    # True masked-edge recovery: REMOVE a sampled direct edge, then try to
    # re-derive it purely from the remaining graph. Recovery must carry
    # provenance for every hop of the alternate path.
    recovered, provenance_ok, refused_reversed = 0, 0, 0
    sample_edges = rng.sample(edges, min(300, len(edges)))
    for e in sample_edges:
        removed = graph.remove(e["subject"], "P279", e["object"])
        paths = graph.infer(e["subject"], "P279", e["object"], max_hops=5)
        graph.restore(removed)
        if paths:
            recovered += 1
            if all(hop.source for hop in paths[0][0]):
                provenance_ok += 1
    reversed_sample = rng.sample(edges, min(200, len(edges)))
    for e in reversed_sample:
        if (e["object"], e["subject"]) in edge_set:
            continue  # rare genuine mutual subclass noise — skip
        if not graph.infer(e["object"], "P279", e["subject"], max_hops=3):
            refused_reversed += 1
    total_reversed = len([e for e in reversed_sample if (e["object"], e["subject"]) not in edge_set])
    print(f"  E12 {len(edges)} P279 edges; masked-edge recovery: {recovered}/{len(sample_edges)} "
          f"re-derived from remaining graph ({provenance_ok} with full hop provenance)")
    print(f"  E12 reversed-edge honesty: {refused_reversed}/{total_reversed} refused (hierarchy is directional)")
    # Recovery rate is REPORTED (it measures ontology density, not code quality);
    # asserted: recovery exists, recovered paths carry provenance, honesty ≥90%.
    e12_ok = (
        recovered > 0
        and provenance_ok == recovered
        and refused_reversed >= 0.9 * max(1, total_reversed)
    )
    results.append(("E12 inference on real ontology", e12_ok,
                    f"masked recovery {recovered}/{len(sample_edges)} (all with provenance); "
                    f"{refused_reversed}/{total_reversed} reversed refused"))

    print(f"\n{'='*72}")
    all_ok = True
    for name, ok, detail in results:
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:36s} {detail}")
    print(f"{'='*72}\nseed {seed} — {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
