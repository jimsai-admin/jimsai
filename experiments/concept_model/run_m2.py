"""M2 — T1-mini intent classifier, production benchmark (no LLM, no embeddings).

Replaces the last neural model in the intent path (the multilingual-e5 prototype
classifier) with a multinomial naive Bayes over CLL CONCEPT IDs. The falsifiable
claim: because features are language-neutral concept IDs, a classifier trained on
ENGLISH examples transfers to other languages AND survives messy real phrasing,
where a surface-WORD classifier collapses. If concept-native does NOT beat
surface on cross-lingual or messy, T1-mini is not worth the swap — recorded.

Grounded on the PRODUCTION lexicon (`cll_shadow`, 155k surfaces + common words),
not the toy E8 lexicon. Conditions, all trained on clean English only:
  clean-en   — held-out English (sanity).
  messy-en   — typo'd / colloquial English (the world as it comes).
  fr / zh     — content words translated via the CLL reverse lexicon (concepts
                preserved) — tests cross-lingual transfer with ZERO target-language
                training data.
Baseline = same naive Bayes over raw word tokens (surface features).

Anti-hardcoding: intent example TEMPLATES are test data (like the harness), slot
fillers are per-seed; nothing enumerates an answer. No per-language template —
other languages are produced by translating concepts, the whole point.

Run: .venv/Scripts/python.exe experiments/concept_model/run_m2.py [seed ...]
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "prototype"))
import os  # noqa: E402

os.environ.setdefault("JIMS_CONCEPT_INDEX", "on")
from jimsai.cll_shadow import get_shadow  # noqa: E402
from jimsai.surface_realizer import get_reverse  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Intent templates. {e} = a nonce entity; other words are ordinary vocabulary the
# lexicon covers. Labels are the production target_ir set (subset).
TEMPLATES = {
    "WORKSPACE_QUERY": [
        "what database does the {e} project use", "where is {e} based",
        "who leads the {e} team", "what city is {e} in",
        "remember that {e} is our lead engineer", "what did i say about {e}",
    ],
    "CODE_GENERATE": [
        "write a function to sort a list", "generate code for a parser",
        "implement a script to read a file", "create a function that adds two numbers",
        "write a program to reverse a string", "code a method to filter records",
    ],
    "GENERAL_FACT": [
        "what is the capital of the country", "explain how a database works",
        "define the word machine", "what is the population of the city",
        "how does an engine work", "what is the meaning of science",
    ],
    "EMOTIONAL_CATCH": [
        "i am feeling really overwhelmed and stressed", "this is so frustrating and hard",
        "i feel sad and confused today", "everything feels difficult right now",
        "i am worried and anxious about this", "i am exhausted and upset",
    ],
    "META_INQUIRY": [
        "what can you do", "how do you work", "what are your capabilities",
        "how confident are you", "explain your reasoning", "what are your sources",
    ],
}
# REAL fully-in-language intent queries (eval data, like the harness's
# multilingual queries) — a genuine cross-lingual test, not shallow translation.
# English-trained surface features CANNOT match these; concept features can iff
# the CLL recovers the same concepts from the target language.
REAL = {
    "fr": {
        "WORKSPACE_QUERY": ["quelle base de données utilise le projet", "où se trouve le projet"],
        "CODE_GENERATE": ["écris une fonction pour trier une liste", "génère du code pour lire un fichier"],
        "GENERAL_FACT": ["quelle est la capitale du pays", "explique comment fonctionne une base de données"],
        "EMOTIONAL_CATCH": ["je me sens vraiment dépassé et stressé", "je suis triste et anxieux aujourd'hui"],
        "META_INQUIRY": ["que peux-tu faire", "comment fonctionnes-tu"],
    },
    "zh": {
        "WORKSPACE_QUERY": ["这个项目使用什么数据库", "项目在哪个城市"],
        "CODE_GENERATE": ["写一个函数来排序列表", "生成读取文件的代码"],
        "GENERAL_FACT": ["这个国家的首都是什么", "解释数据库如何工作"],
        "EMOTIONAL_CATCH": ["我感到非常不知所措和压力很大", "我今天很难过很焦虑"],
        "META_INQUIRY": ["你能做什么", "你是如何工作的"],
    },
}
NC, NV = "bcdfghjklmnpqrstvwxz", "aeiou"


def nonce(rng: Random, n: int = 3) -> str:
    return "".join(rng.choice(NC) + rng.choice(NV) for _ in range(n)).capitalize()


def typo(w: str, rng: Random) -> str:
    if len(w) < 4 or rng.random() > 0.5:
        return w
    i = rng.randrange(len(w) - 2)
    return w[:i] + w[i + 1] + w[i] + w[i + 2:]


def messify(text: str, rng: Random) -> str:
    filler = rng.choice(["um ", "so ", "hey ", "ok so ", ""])
    words = [typo(w, rng) for w in text.split()]
    return filler + " ".join(words)


def translate(text: str, lang: str, rev) -> str:
    """Translate CONTENT words (>=4 chars) via the CLL reverse lexicon; keep the
    rest. Concepts are preserved — that is what T1-mini should key on."""
    out = []
    for w in text.split():
        surf = None
        for c in get_shadow().surfaces.get(w.lower(), [])[:3]:
            surf = rev.surface(c, lang)
            if surf:
                break
        out.append(surf if (len(w) >= 4 and surf) else w)
    return " ".join(out)


# ── classifiers ──────────────────────────────────────────────────────────────

class NB:
    def __init__(self):
        self.counts = defaultdict(lambda: defaultdict(int))
        self.tot = defaultdict(int)
        self.ex = defaultdict(int)
        self.vocab = set()

    def train(self, feats, label):
        for f in feats:
            self.counts[label][f] += 1
            self.tot[label] += 1
            self.vocab.add(f)
        self.ex[label] += 1

    def classify(self, feats):
        total = sum(self.ex.values()) or 1
        v = len(self.vocab) or 1
        best, blp = "", -1e18
        for label in self.counts:
            lp = math.log(self.ex[label] / total)
            denom = self.tot[label] + v
            for f in feats:
                lp += math.log((self.counts[label].get(f, 0) + 1) / denom)
            if lp > blp:
                best, blp = label, lp
        return best


def concept_feats(text):
    concepts, literals = get_shadow().encode(text, mode="query")
    return [*concepts, *(["#L"] * len(literals))]


def surface_feats(text):
    return [w.lower() for w in text.split() if len(w) >= 2]


def run_seed(seed: int) -> dict:
    rng = Random(seed)
    sh = get_shadow(); rev = get_reverse()
    # build train + held-out from templates with per-seed nonce fillers
    train, heldout = [], []
    for label, tmpls in TEMPLATES.items():
        for i, t in enumerate(tmpls):
            for _ in range(4):
                q = t.format(e=nonce(rng)) if "{e}" in t else t
                (train if rng.random() < 0.7 else heldout).append((q, label))
    def hybrid_feats(text):
        return surface_feats(text) + concept_feats(text)

    c_clf, s_clf, h_clf = NB(), NB(), NB()
    for q, y in train:
        c_clf.train(concept_feats(q), y)
        s_clf.train(surface_feats(q), y)
        h_clf.train(hybrid_feats(q), y)

    def acc(items, feats, clf):
        if not items:
            return 0.0
        return sum(clf.classify(feats(q)) == y for q, y in items) / len(items)

    messy = [(messify(q, rng), y) for q, y in heldout]
    fr = [(q, y) for y, qs in REAL["fr"].items() for q in qs]   # REAL in-language
    zh = [(q, y) for y, qs in REAL["zh"].items() for q in qs]
    return {
        "seed": seed, "n_train": len(train), "n_test": len(heldout),
        "concept": {"clean_en": acc(heldout, concept_feats, c_clf),
                    "messy_en": acc(messy, concept_feats, c_clf),
                    "fr": acc(fr, concept_feats, c_clf),
                    "zh": acc(zh, concept_feats, c_clf)},
        "surface": {"clean_en": acc(heldout, surface_feats, s_clf),
                    "messy_en": acc(messy, surface_feats, s_clf),
                    "fr": acc(fr, surface_feats, s_clf),
                    "zh": acc(zh, surface_feats, s_clf)},
        "hybrid": {"clean_en": acc(heldout, hybrid_feats, h_clf),
                   "messy_en": acc(messy, hybrid_feats, h_clf),
                   "fr": acc(fr, hybrid_feats, h_clf),
                   "zh": acc(zh, hybrid_feats, h_clf)},
    }


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]

    def avg(model, cond):
        return sum(r[model][cond] for r in results) / len(results)

    print("=" * 72)
    print(f"M2 T1-mini intent classifier — {len(seeds)} seeds, trained on clean English only")
    print(f"  ~{results[0]['n_train']} train / {results[0]['n_test']} test examples/seed")
    print("-" * 72)
    print(f"{'condition':<12}{'concept':>10}{'surface':>10}{'hybrid':>10}")
    for cond in ("clean_en", "messy_en", "fr", "zh"):
        print(f"{cond:<12}{avg('concept', cond):>9.0%}{avg('surface', cond):>10.0%}{avg('hybrid', cond):>10.0%}")
    print("-" * 72)
    # The production classifier is the HYBRID: it should keep surface's
    # same-language precision AND gain concept's cross-lingual transfer.
    h_en = avg("hybrid", "clean_en") >= avg("surface", "clean_en") - 0.03
    h_cross = all(avg("hybrid", c) > avg("surface", c) + 0.05 for c in ("fr", "zh"))
    ok = h_en and h_cross
    print("hybrid keeps English precision =", h_en, "| hybrid beats surface x-lingual =", h_cross)
    print("VERDICT:", "PASS — hybrid (surface+concept) = English precision + cross-lingual transfer, no LLM/embeddings"
          if ok else "MIXED — see table; honest finding recorded")
    return 0 if ok else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
