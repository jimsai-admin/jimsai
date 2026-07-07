"""M4b — the constrained-decode realizer (the T2 endgame mechanism).

The Independence Policy (docs/jimsai_llm_free_architecture.md §2.6) removes
LLM fallback. Fluency beyond templates must therefore come from an IN-HOUSE
organ that cannot invent. This experiment proves the mechanism:

  A small neural realizer decodes over a CONTENT-LICENSED LATTICE — at every
  decode position, the only legal tokens are (a) closed-class tokens derived
  from the training distribution (never a hand list), (b) the frame's content
  values and their morphologically-mined variants, (c) end punctuation.
  The model chooses function words, agreement, and inflection; it CANNOT emit
  an entity, number, or claim the frame does not license. Zero invention is a
  property of the decode space, not of training quality.

Fluency phenomena the templates cannot decide (they would need the answer
precomputed upstream as frame data): article AGREEMENT with noun class and
number, and plural MORPHOLOGY on the object. The realizer must learn both
from (frame -> sentence) pairs alone.

Checks:
  F1  zero invention by construction: at an UNDERTRAINED checkpoint the
      unconstrained twin (same weights) emits unlicensed content tokens; the
      constrained decode of the very same weights emits ZERO (asserted).
  F2  agreement fluency: on held-out compositional (agent, object) x number
      frames, the trained realizer picks the correct article form and plural
      inflection (asserted >= 0.9; exact numbers reported).
  F3  new language = data only: a second grammar (fresh function words,
      different word order — order is grammar DATA) meets F1+F2 with the
      identical class; no per-language branch exists in this file.
  F4  division of labor (report): templates handle composition with article
      as precomputed frame data; the realizer moves that decision into a
      learned, still-capacity-starved organ — the honest split, not a rival.

Anti-hardcoding: all vocabulary nonce per seed; closed-class tokens derived
distributionally (high frequency AND never observed as a frame value);
suffixes mined from data (classify.mine_suffixes pattern), never named.

Run: .venv/Scripts/python.exe experiments/ele/realizer.py [seed]
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus as C

N_SENTENCES = 500
PLURAL_P = 0.35
HELD_OUT_PAIRS = 12


# ── agreement grammar (built on the nonce vocab of corpus.build_grammar) ──

@dataclass
class AgrGrammar:
    agents: list[str]
    objects: list[str]
    verbs: list[str]
    noun_class: dict[str, str]            # object -> "A" | "B"
    articles: dict[tuple[str, str], str]  # (class, number) -> article form
    pl_suffix: str
    order: tuple[str, ...]                # word order is grammar DATA
    reserved: list[tuple[str, str]] = field(default_factory=list)

    def object_surface(self, obj: str, number: str) -> str:
        return obj + (self.pl_suffix if number == "pl" else "")

    def realize(self, frame: dict[str, str]) -> list[str]:
        cls = self.noun_class[frame["object"]]
        art = self.articles[(cls, frame["number"])]
        surf = {"agent": frame["agent"], "verb": frame["verb"], "article": art,
                "object": self.object_surface(frame["object"], frame["number"])}
        return [surf[r] for r in self.order] + ["."]


def build_agr_grammar(seed: int, order: tuple[str, ...]) -> AgrGrammar:
    base = C.build_grammar(seed)
    rng = random.Random(seed + 11)
    used = set(base.agents + base.objects + base.all_verbs)
    def nonce(s=(1, 1)):
        return C._nonce(rng, used, s)
    g = AgrGrammar(
        agents=base.agents,
        objects=base.objects,
        verbs=base.verbs_trans,
        noun_class={o: rng.choice("AB") for o in base.objects},
        articles={(c, n): nonce() for c in "AB" for n in ("sg", "pl")},
        pl_suffix=nonce(),
        order=order,
    )
    pairs = [(a, o) for a in g.agents for o in g.objects]
    g.reserved = rng.sample(pairs, HELD_OUT_PAIRS)
    return g


def generate_agr(g: AgrGrammar, seed: int, n: int = N_SENTENCES
                 ) -> list[tuple[dict[str, str], list[str]]]:
    rng = random.Random(seed + 13)
    reserved = set(g.reserved)
    pairs = []
    for _ in range(n):
        while True:
            agent, obj = rng.choice(g.agents), rng.choice(g.objects)
            if (agent, obj) not in reserved:
                break
        frame = {"agent": agent, "verb": rng.choice(g.verbs), "object": obj,
                 "number": "pl" if rng.random() < PLURAL_P else "sg"}
        pairs.append((frame, g.realize(frame)))
    return pairs


# ── the licensed lattice (all derived from data) ──

def mine_suffixes_from_pairs(pairs) -> set[str]:
    """Suffix candidates: trailing substrings that turn one observed content
    value into another observed surface token, across >= 3 distinct stems."""
    values = {v for f, _ in pairs for k, v in f.items() if k != "number"}
    surfaces = {t for _, toks in pairs for t in toks}
    stems: dict[str, set[str]] = {}
    for s in surfaces:
        for v in values:
            if s != v and s.startswith(v):
                stems.setdefault(s[len(v):], set()).add(v)
    return {sfx for sfx, st in stems.items() if len(st) >= 3}


def closed_class_tokens(pairs, suffixes: set[str]) -> set[str]:
    """Function words, distributionally and frequency-free: a token is
    closed-class iff it NEVER appears as a frame value AND is not a
    (value + mined suffix) morphological variant of one. Articles qualify at
    ANY frequency (rare class x number forms included); inflected content
    forms are excluded — they must be licensed per-frame. (A frequency bar
    was tried first and failed: unbalanced noun classes pushed rare plural
    articles below it, masking the correct form out of the lattice.)"""
    tokens = {t for _, toks in pairs for t in toks}
    values = {v for f, _ in pairs for k, v in f.items() if k != "number"}
    variants = {v + sfx for v in values for sfx in suffixes}
    return {t for t in tokens if t not in values and t not in variants} | {"."}


def licensed_tokens(frame: dict[str, str], closed: set[str],
                    suffixes: set[str]) -> set[str]:
    content = {v for k, v in frame.items() if k != "number"}
    variants = {v + sfx for v in content for sfx in suffixes}
    return closed | content | variants


# ── the realizer (same MLP family as R7's baseline, plus constrained decode) ──

class ConstrainedRealizer:
    ROLES = ("agent", "verb", "object")

    def __init__(self, vocab: dict[str, int], seed: int, hidden: int = 64,
                 max_len: int = 6):
        V = len(vocab)
        self.vocab, self.inv = vocab, {i: w for w, i in vocab.items()}
        self.max_len = max_len
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, 0.1, (len(self.ROLES) * V + 1, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, 0.1, (hidden, max_len * V))
        self.b2 = np.zeros(max_len * V)

    @property
    def n_params(self) -> int:
        return sum(a.size for a in (self.W1, self.b1, self.W2, self.b2))

    def _encode(self, frames) -> np.ndarray:
        V = len(self.vocab)
        X = np.zeros((len(frames), len(self.ROLES) * V + 1))
        for i, f in enumerate(frames):
            for r, role in enumerate(self.ROLES):
                X[i, r * V + self.vocab[f[role]]] = 1.0
            X[i, -1] = 1.0 if f["number"] == "pl" else 0.0
        return X

    def train(self, pairs, epochs: int, lr: float = 0.5, seed: int = 0) -> None:
        V = len(self.vocab)
        X = self._encode([f for f, _ in pairs])
        Y = np.full((len(pairs), self.max_len), self.vocab["."])
        for i, (_, toks) in enumerate(pairs):
            for j, t in enumerate(toks[: self.max_len]):
                Y[i, j] = self.vocab[t]
        rng = np.random.default_rng(seed)
        for _ in range(epochs):
            idx = rng.permutation(len(X))
            Xb, Yb = X[idx], Y[idx]
            h = np.tanh(Xb @ self.W1 + self.b1)
            logits = (h @ self.W2 + self.b2).reshape(len(Xb), self.max_len, V)
            logits -= logits.max(axis=2, keepdims=True)
            p = np.exp(logits)
            p /= p.sum(axis=2, keepdims=True)
            d = p
            for pos in range(self.max_len):
                d[np.arange(len(Yb)), pos, Yb[:, pos]] -= 1
            d = d.reshape(len(Xb), -1) / len(Xb)
            self.W2 -= lr * (h.T @ d)
            self.b2 -= lr * d.sum(0)
            dh = d @ self.W2.T * (1 - h ** 2)
            self.W1 -= lr * (Xb.T @ dh)
            self.b1 -= lr * dh.sum(0)

    def _logits(self, frame) -> np.ndarray:
        X = self._encode([frame])
        h = np.tanh(X @ self.W1 + self.b1)
        return (h @ self.W2 + self.b2).reshape(self.max_len, len(self.vocab))

    def render_unconstrained(self, frame) -> list[str]:
        out = []
        for row in self._logits(frame):
            tok = self.inv[int(row.argmax())]
            out.append(tok)
            if tok == ".":
                break
        return out

    def render(self, frame, closed: set[str], suffixes: set[str]) -> list[str]:
        """Constrained decode: unlicensed tokens are masked to -inf. The model
        cannot invent content REGARDLESS of how badly it is trained."""
        licensed = licensed_tokens(frame, closed, suffixes)
        mask = np.full(len(self.vocab), -np.inf)
        for t in licensed:
            if t in self.vocab:
                mask[self.vocab[t]] = 0.0
        out = []
        for row in self._logits(frame):
            tok = self.inv[int((row + mask).argmax())]
            out.append(tok)
            if tok == ".":
                break
        return out


# ── evaluation ──

def held_out_frames(g: AgrGrammar) -> list[tuple[dict[str, str], list[str]]]:
    rng = random.Random(0xE1E)
    frames = []
    for agent, obj in g.reserved:
        for number in ("sg", "pl"):
            f = {"agent": agent, "verb": rng.choice(g.verbs), "object": obj,
                 "number": number}
            frames.append((f, g.realize(f)))
    return frames


def unlicensed(out, frame, closed, suffixes) -> list[str]:
    lic = licensed_tokens(frame, closed, suffixes)
    return [t for t in out if t not in lic]


def agreement_ok(out: list[str], g: AgrGrammar, frame: dict[str, str]) -> bool:
    cls = g.noun_class[frame["object"]]
    want_art = g.articles[(cls, frame["number"])]
    want_obj = g.object_surface(frame["object"], frame["number"])
    return want_art in out and want_obj in out


def evaluate_language(name: str, g: AgrGrammar, seed: int) -> dict:
    pairs = generate_agr(g, seed)
    vocab_tokens = sorted({t for _, toks in pairs for t in toks}
                          | {v for f, _ in pairs for k, v in f.items() if k != "number"})
    vocab = {w: i for i, w in enumerate(vocab_tokens)}
    suffixes = mine_suffixes_from_pairs(pairs)
    closed = closed_class_tokens(pairs, suffixes)
    held = held_out_frames(g)

    # F1 — undertrained checkpoint: same weights, two decodes.
    young = ConstrainedRealizer(vocab, seed)
    young.train(pairs, epochs=12, seed=seed)
    halluc_unc = sum(bool(unlicensed(young.render_unconstrained(f), f, closed, suffixes))
                     for f, _ in held)
    halluc_con = sum(bool(unlicensed(young.render(f, closed, suffixes), f, closed, suffixes))
                     for f, _ in held)
    assert halluc_con == 0, f"{name}: constrained decode emitted unlicensed tokens"

    # F2 — trained realizer: agreement + exact match on held-out combos.
    # Train to convergence ON TRAINING DATA (held-out and lattice untouched):
    # the property under test is capability existence, not a fixed epoch count.
    model = ConstrainedRealizer(vocab, seed)
    for chunk in range(12):
        model.train(pairs, epochs=100, lr=0.5 if chunk < 6 else 0.2, seed=seed + chunk)
        train_exact = sum(model.render(f, closed, suffixes) == t
                          for f, t in pairs[:200]) / 200
        if train_exact >= 0.995:
            break
    agree = exact = 0
    for f, truth in held:
        out = model.render(f, closed, suffixes)
        assert not unlicensed(out, f, closed, suffixes)
        agree += agreement_ok(out, g, f)
        exact += out == truth
    agree_rate, exact_rate = agree / len(held), exact / len(held)
    assert agree_rate >= 0.9, f"{name}: agreement {agree_rate:.2f} < 0.9"

    return {
        "language": name,
        "order": list(g.order),
        "params": model.n_params,
        "closed_class_derived": sorted(closed),
        "suffixes_mined": sorted(suffixes),
        "undertrained_unconstrained_hallucinating": f"{halluc_unc}/{len(held)}",
        "undertrained_constrained_hallucinating": f"{halluc_con}/{len(held)}",
        "heldout_agreement": round(agree_rate, 3),
        "heldout_exact_match": round(exact_rate, 3),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 702945

    # F3: two "languages" — fresh function words, different word order (DATA).
    lang_a = build_agr_grammar(seed, order=("agent", "verb", "article", "object"))
    lang_b = build_agr_grammar(seed + 1000, order=("agent", "article", "object", "verb"))

    results = []
    for name, g in (("svo", lang_a), ("sov", lang_b)):
        r = evaluate_language(name, g, seed)
        results.append(r)
        print(f"F1 PASS [{name}] undertrained twin: unconstrained hallucinated on "
              f"{r['undertrained_unconstrained_hallucinating']} held-out frames; "
              f"constrained (same weights): {r['undertrained_constrained_hallucinating']}")
        print(f"F2 PASS [{name}] held-out agreement {r['heldout_agreement']:.0%}, "
              f"exact match {r['heldout_exact_match']:.0%} "
              f"({r['params']} params; closed class {r['closed_class_derived']}, "
              f"suffixes {r['suffixes_mined']})")
    print("F3 PASS  second language (new function words, SOV order) met F1+F2 "
          "with the identical class — word order is grammar data, no language "
          "branch in this file")
    print("F4 NOTE  division of labor: templates compose with agreement decided "
          "upstream as frame data; the realizer LEARNS the agreement decision "
          "while the lattice keeps invention impossible")

    out = Path(__file__).parent / "results" / "m4b_realizer.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"seed": seed, "results": results}, indent=2,
                              ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
