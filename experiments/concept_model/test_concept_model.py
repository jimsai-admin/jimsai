"""
CNL v0 experiments — generative, seeded, no fixed expected strings.

Run:  python experiments/concept_model/test_concept_model.py [seed]

Same anti-hardcoding rules as benchmarks/genuine_eval.py: entities/values are
fresh nonces each run; assertions are properties, not strings.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import time

from concept_model import (
    ConceptEncoder,
    ConceptMemory,
    ConceptGraph,
    Detection,
    MockPerceptionInterface,
    TinyIntentClassifier,
    realize,
)

CONSONANTS = "bdfgjklmnprstvz"
VOWELS = "aeiou"


def nonce(rng: random.Random, syllables: int = 3, suffix: str = "") -> str:
    return "".join(rng.choice(CONSONANTS) + rng.choice(VOWELS) for _ in range(syllables)).capitalize() + suffix


FACT_FAMILIES = [
    {
        "name": "project_database",
        "statement": "The {e} project uses {v} as its primary database.",
        "queries": {
            "fr": "Quelle base de données le projet {e} utilise-t-il ?",
            "yo": "Kí ni database tí iṣẹ́ akanṣe {e} ń lò?",
            "zh": "{e} 项目使用什么数据库？",
        },
    },
    {
        "name": "person_city",
        "statement": "{e} is our lead engineer and she is based in the city of {v}.",
        "queries": {
            "fr": "Dans quelle ville se trouve {e} ?",
            "yo": "Ìlú wo ni {e} wà?",
            "zh": "{e} 在哪个城市？",
        },
    },
    {
        "name": "device_codename",
        "statement": "Our next hardware device is codenamed {v}, replacing the {e} line.",
        "queries": {
            "fr": "Quel est le nom de code de l'appareil qui remplace la gamme {e} ?",
            "yo": "Kí ni orúkọ ẹ̀rọ tí yóò rọ́pò {e}?",
            "zh": "取代 {e} 系列的设备代号是什么？",
        },
    },
]


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.SystemRandom().randint(1, 10**6)
    rng = random.Random(seed)
    print(f"CNL v0 experiments — seed {seed}\n")
    results: list[tuple[str, bool, str]] = []

    memory = ConceptMemory()
    facts = []
    for fam in FACT_FAMILIES:
        e, v = nonce(rng), nonce(rng, 2, "X")
        facts.append({"fam": fam, "e": e, "v": v})
        memory.add(f"fact_{fam['name']}", fam["statement"].format(e=e, v=v), "en")
    # Distractor corpus so IDF has something to weigh
    memory.add("d1", "My dog is big.", "en")
    memory.add("d2", "My father bought me a dog when I lost my cat.", "en")
    memory.add("d3", "My cat is small.", "en")

    # E1 — cross-lingual recall: fr/yo/zh queries must hit the taught record top-1
    e1_pass, e1_total = 0, 0
    for f in facts:
        for lang, template in f["fam"]["queries"].items():
            e1_total += 1
            hits = memory.retrieve(template.format(e=f["e"]), lang)
            top = hits[0][0].record_id if hits else "NONE"
            ok = top == f"fact_{f['fam']['name']}"
            e1_pass += ok
            marker = "ok " if ok else "MISS"
            print(f"  E1 {marker} [{lang}] {f['fam']['name']}: top={top}"
                  + (f" shared={hits[0][2]}" if hits else ""))
    results.append(("E1 cross-lingual recall", e1_pass == e1_total, f"{e1_pass}/{e1_total} top-1"))

    # E2 — gap honesty: ghost entity queries must return NOTHING
    e2_pass, e2_total = 0, 0
    for f in facts:
        e2_total += 1
        ghost = nonce(rng, 4)
        lang, template = rng.choice(list(f["fam"]["queries"].items()))
        hits = memory.retrieve(template.format(e=ghost), lang)
        ok = len(hits) == 0
        e2_pass += ok
        print(f"  E2 {'ok ' if ok else 'LEAK'} ghost '{ghost}' [{lang}]: {len(hits)} results"
              + (f" (leaked {hits[0][0].record_id})" if hits else ""))
    results.append(("E2 gap honesty", e2_pass == e2_total, f"{e2_pass}/{e2_total} empty"))

    # E3 — polysemy: context voting must pick different senses of "bank"
    encoder = ConceptEncoder()
    fin = encoder.encode("I deposited money at the bank", "en")
    riv = encoder.encode("We sat on the bank of the river", "en")
    fin_ok = "C:bank_finance" in fin.concepts and "C:riverbank" not in fin.concepts
    riv_ok = "C:riverbank" in riv.concepts and "C:bank_finance" not in riv.concepts
    print(f"  E3 money-context → {[c for c in fin.concepts if 'bank' in c]}")
    print(f"  E3 river-context → {[c for c in riv.concepts if 'bank' in c or 'river' in c]}")
    results.append(("E3 polysemy voting", fin_ok and riv_ok, "both senses resolved by context"))

    # E4 — graph intersection: d2 reachable from d1 via C:dog; C:dog outweighs C:my
    related = memory.related("d1")
    related_ids = [r.record_id for r, _, _ in related]
    d2_link = next(((s, keys) for r, s, keys in related if r.record_id == "d2"), None)
    idf_dog = memory._idf("C:dog")
    idf_my = memory._idf("C:my")
    e4_ok = d2_link is not None and "C:dog" in d2_link[1] and idf_dog > idf_my
    print(f"  E4 related(d1) = {related_ids}; d2 via {d2_link[1] if d2_link else '—'}; "
          f"idf(C:dog)={idf_dog:.3f} > idf(C:my)={idf_my:.3f}: {idf_dog > idf_my}")
    results.append(("E4 graph intersection", e4_ok, "d2 linked via C:dog, IDF-damped C:my"))

    # E5 — order sensitivity (honesty check): concept SETS cannot distinguish
    # "dog bites man" from "man bites dog" — sequences differ, sets tie.
    a = memory.add("e5a", "The dog bites the man.", "en")
    b = memory.add("e5b", "The man bites the dog.", "en")
    set_tie = a.concepts == b.concepts
    seq_differs = a.sequence != b.sequence
    print(f"  E5 concept sets identical: {set_tie}; sequences differ: {seq_differs}"
          f" → relations required for role disambiguation (documented limitation)")
    results.append(("E5 order limitation confirmed", set_tie and seq_differs, "sets tie, sequences differ"))

    # E6 — cross-modal, cross-lingual: an image ingested once is retrievable by
    # text queries in any language; weak detections are filtered; provenance
    # points at the region.
    perception = MockPerceptionInterface(min_confidence=0.5)
    img = memory.add_media(
        "img_1",
        [
            Detection("C:dog", 0.93, "12,40,220,180"),
            Detection("C:river", 0.81, "0,150,640,90"),
            Detection("C:cat", 0.22, "500,10,40,30"),  # below threshold — must not index
        ],
        modality="image",
        perception=perception,
    )
    hits_en = memory.retrieve("a dog by the river", "en")
    hits_yo = memory.retrieve("ajá", "yo")
    hits_zh = memory.retrieve("狗", "zh")
    top_en = hits_en[0][0].record_id if hits_en else "NONE"
    in_yo = any(r.record_id == "img_1" for r, _, _ in hits_yo)
    in_zh = any(r.record_id == "img_1" for r, _, _ in hits_zh)
    weak_filtered = "C:cat" not in img.concepts
    prov = img.provenance.get("C:dog", {})
    e6_ok = top_en == "img_1" and in_yo and in_zh and weak_filtered and prov.get("region") == "12,40,220,180"
    print(f"  E6 en query top={top_en}; yo 'ajá' hits image: {in_yo}; zh '狗' hits image: {in_zh}")
    print(f"  E6 weak detection (C:cat @0.22) filtered: {weak_filtered}; C:dog provenance region={prov.get('region')}")
    results.append(("E6 cross-modal grounding", e6_ok, "image found via en/yo/zh text; provenance kept"))

    # E7 — correction is a graph edit, not retraining: relabel dog→fox (novel
    # concept, not in any lexicon) and retrieval follows immediately.
    memory.correct_media_concept("img_1", "C:dog", "C:fox")
    # Dog-only query: the image must stop matching on C:dog specifically.
    # (A river query still matching is CORRECT — the image still shows a river.)
    after = memory.retrieve("the dog", "en")
    dog_gone = not any(r.record_id == "img_1" for r, _, _ in after)
    river_still = any(r.record_id == "img_1" for r, _, _ in memory.retrieve("the river", "en"))
    fox_prov = memory.records["img_1"].provenance.get("C:fox", {})
    e7_ok = dog_gone and river_still and fox_prov.get("corrected_from") == "C:dog"
    print(f"  E7 after correction: dog query no longer matches img_1: {dog_gone}; "
          f"river query still matches: {river_still}; "
          f"C:fox provenance corrected_from={fox_prov.get('corrected_from')}")
    results.append(("E7 correction as graph edit", e7_ok, "relabel updates index instantly, audit trail kept"))

    # E8 — T1-mini: intent classifier TRAINED ON ENGLISH ONLY must generalize to
    # fr/yo/zh and to chaotic English, because features are concept IDs.
    clf = TinyIntentClassifier()
    train_templates = {
        "memory_store": [
            "The {e} project uses {v} as its primary database.",
            "{e} is our lead engineer and she is based in the city of {v}.",
            "Our next hardware device is codenamed {v}, replacing the {e} line.",
            "My dog {e} is big.",
        ],
        "memory_recall": [
            "What database does the {e} project use?",
            "Which city is {e} based in?",
            "What is the codename of the device replacing the {e} line?",
            "Who is the lead engineer of {e}?",
        ],
        "creative_text": [
            "Write a poem about {e}.",
            "Write me a story about the {e} project.",
            "Please write a story about a dog in {e}.",
        ],
    }
    for label, templates in train_templates.items():
        for template in templates:
            for _ in range(8):
                text = template.format(e=nonce(rng), v=nonce(rng, 2, "X"))
                clf.train(encoder.encode(text, "en"), label)

    test_cases = [  # (lang, text template, expected label) — NOT seen in training
        ("fr", "Quelle base de données le projet {e} utilise-t-il ?", "memory_recall"),
        ("fr", "Dans quelle ville se trouve {e} ?", "memory_recall"),
        ("fr", "Écris un poème sur {e}.", "creative_text"),
        ("yo", "Kí ni database tí iṣẹ́ akanṣe {e} ń lò?", "memory_recall"),
        ("yo", "Ìlú wo ni {e} wà?", "memory_recall"),
        ("yo", "Kọ ewì nípa {e}.", "creative_text"),
        ("zh", "{e} 项目使用什么数据库？", "memory_recall"),
        ("zh", "{e} 在哪个城市？", "memory_recall"),
        ("zh", "写一首关于 {e} 的诗。", "creative_text"),
        ("en", "yo quick q -- waht database does teh {e} project use pls??", "memory_recall"),
        ("en", "ok so basically um my dog {e} is big lol", "memory_store"),
        ("en", "pls write a poem about {e} thx", "creative_text"),
    ]
    e8_pass = 0
    timings = []
    for lang, template, expected in test_cases:
        text = template.format(e=nonce(rng))
        enc = encoder.encode(text, lang)
        t0 = time.perf_counter()
        label, margin = clf.classify(enc)
        timings.append(time.perf_counter() - t0)
        ok = label == expected
        e8_pass += ok
        if not ok:
            print(f"  E8 MISS [{lang}] '{text}' → {label} (wanted {expected})")
    us = sum(timings) / len(timings) * 1e6
    print(f"  E8 trained en-only: {e8_pass}/{len(test_cases)} correct across fr/yo/zh/chaotic-en; "
          f"classify latency ≈ {us:.0f}µs/query")
    results.append(("E8 T1-mini cross-lingual", e8_pass >= int(0.9 * len(test_cases)),
                    f"{e8_pass}/{len(test_cases)}, ~{us:.0f}µs (vs seconds for a 1.7B LLM call)"))

    # E9 — T2-mini realization: one concept claim voiced in 4 languages from the
    # reverse lexicon (derived data). Knowledge-free: it can only say what it is handed.
    f0 = facts[0]  # project/database fact taught in E1
    claim = [f"L:{f0['e'].lower()}", "C:project", "C:use", f"L:{f0['v'].lower()}", "C:database"]
    e9_ok = True
    for lang, must_contain in [("en", "database"), ("fr", "base de donnees"), ("zh", "数据库"), ("yo", "database")]:
        surface = realize(claim, lang)
        ok = must_contain in surface.lower() and f0["e"].lower() in surface.lower() and f0["v"].lower() in surface.lower()
        e9_ok &= ok
        print(f"  E9 [{lang}] {surface}")
    results.append(("E9 T2-mini realization", e9_ok, "same claim voiced in 4 languages from derived reverse-lexicon"))

    # E10 — bounded multi-hop inference with refusal: knowledge never stated in
    # one place must be inferable WITH provenance — and non-composable relations
    # must refuse, where an LLM would happily guess.
    graph = ConceptGraph(transitive={"causes": 0.9})
    chain = [f"C:{nonce(rng).lower()}" for _ in range(4)]  # X1→X2→X3→X4, taught pairwise
    for i in range(len(chain) - 1):
        graph.add(chain[i], "causes", chain[i + 1], 0.9, source=f"rec_{i}")
    paths = graph.infer(chain[0], "causes", chain[-1])
    hop_ok = bool(paths) and len(paths[0][0]) == 3
    conf_ok = bool(paths) and paths[0][1] < 0.9  # joint confidence decays, never inflates
    prov_ok = bool(paths) and [e.source for e in paths[0][0]] == ["rec_0", "rec_1", "rec_2"]
    ghost_paths = graph.infer(chain[0], "causes", f"C:{nonce(rng, 4).lower()}")
    gap_ok = not ghost_paths
    graph.add("C:a1", "chases", "C:b1", 0.95, "r_a")
    graph.add("C:b1", "chases", "C:c1", 0.95, "r_b")
    refuse_ok = not graph.infer("C:a1", "chases", "C:c1") and bool(graph.infer("C:a1", "chases", "C:b1"))
    e10_ok = hop_ok and conf_ok and prov_ok and gap_ok and refuse_ok
    print(f"  E10 3-hop causal chain inferred: {hop_ok}; joint conf {paths[0][1] if paths else '—'}"
          f" (< single-hop 0.9): {conf_ok}; provenance all hops: {prov_ok}")
    print(f"  E10 unknown target → no path (gap): {gap_ok}; "
          f"non-transitive 'chases' 2-hop REFUSED while 1-hop answers: {refuse_ok}")
    results.append(("E10 inference + refusal", e10_ok,
                    "multi-hop with provenance & decay; composition refused for non-transitive predicate"))

    print(f"\n{'='*64}")
    all_ok = True
    for name, ok, detail in results:
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name:32s} {detail}")
    print(f"{'='*64}\nseed {seed} — {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
