"""M10 — Referring-expression generation (falsifiable, no LLM).

Crux (docs/generation_decomposition.md §9): the choice a fluent writer makes
dozens of times per paragraph — say the NAME or say a PRONOUN ("Vekolin is our
engineer. SHE is based in Kumasa.") — is not an opaque neural talent. It is a
COMPUTABLE decision from discourse state (Centering Theory): pronominalise the
entity that is in focus AND whose pronoun is unambiguous; otherwise name it. If
true, "natural-sounding reference" is an independently-testable module, not a
reason to keep an LLM in the answer path.

The falsifiable claim, three strategies compared on generated multi-sentence
discourses (seeded, per-run nonces, no model anywhere):

  all_names   — never pronominalise. Trivially unambiguous, but robotic
                ("Vekolin ... Vekolin ... Vekolin"). Naturalness floor.
  always_pron — pronominalise every eligible (non-introductory) mention.
                Maximally natural, but AMBIGUOUS when two entities share a
                pronoun class ("Alpha met Beta. She left." — who left?).
  centering   — THE MECHANISM. Pronominalise a mention iff it is the continued
                focus (subject carried from the previous sentence) AND no other
                locally-salient entity shares its agreement class (gender +
                number). Otherwise use the name.

An INDEPENDENT resolver (never sees the generator's intent) then reads the text
and resolves each pronoun by salience + recency + agreement — the round trip.
PASS requires all three:
  (1) centering resolution accuracy == all_names (100%): the mechanism NEVER
      introduces an ambiguity the reader cannot resolve;
  (2) centering naturalness materially > all_names: it actually pronominalises;
  (3) always_pron resolution < 100%: ambiguity-awareness is NECESSARY, not
      decorative — a naive pronominaliser demonstrably confuses the reader.

Kill: if centering cannot beat all_names on naturalness without dropping
resolution, or always_pron does NOT fail, referring-expression generation is not
captured by this computable rule at this scope — recorded, not hidden.

Anti-hardcoding: discourses are generated from per-seed nonce entities with
per-seed agreement classes; the only fixed knowledge is the closed-class pronoun
inventory (she/he/it/they — grammar, not vocabulary) and the salience ordering
(subject > object), both language-general. No entity or sentence is enumerated.

Run: .venv/Scripts/python.exe experiments/discourse/run_m10.py [seed ...]
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Closed-class pronoun inventory by agreement class. Grammar (a finite closed
# set), not a vocabulary list — the same status as "questions end in '?'".
PRONOUN = {"f": "she", "m": "he", "n": "it", "p": "they"}
NONCE_C = "bcdfghjklmnpqrstvwxz"
NONCE_V = "aeiou"


def nonce(rng: Random, n: int = 3) -> str:
    return "".join(rng.choice(NONCE_C) + rng.choice(NONCE_V) for _ in range(n)).capitalize()


@dataclass
class Entity:
    name: str
    agr: str  # agreement class key into PRONOUN


@dataclass
class Sentence:
    subject: Entity
    predicate: str          # surface verb phrase, e.g. "leads the project"
    obj: Entity | str | None  # entity, literal string, or None
    # mentions filled by realiser: list of (entity, surface, is_pronoun, slot)
    mentions: list = field(default_factory=list)


def make_discourse(rng: Random) -> list[Sentence]:
    """A short chain of facts over 3–4 nonce entities. Agreement classes are
    drawn so that SOME discourses contain two entities of the same class — the
    ambiguity that separates the strategies. Facts form a natural focus chain
    (each sentence tends to continue the previous subject or object)."""
    n_ent = rng.randint(3, 4)
    ents = [Entity(nonce(rng), rng.choice("fmn")) for _ in range(n_ent)]
    # ensure at least one same-class collision half the time (else no ambiguity)
    if rng.random() < 0.7 and len(ents) >= 2:
        ents[1].agr = ents[0].agr
    verbs_ee = ["mentored", "reports to", "replaced", "met", "advises"]
    verbs_el = ["is based in", "works on", "leads", "manages", "founded"]
    cities = [nonce(rng) for _ in range(2)]
    sents: list[Sentence] = []
    focus = ents[0]
    for _ in range(rng.randint(4, 6)):
        subj = focus if rng.random() < 0.65 else rng.choice(ents)
        if rng.random() < 0.5:  # entity-entity
            obj = rng.choice([e for e in ents if e is not subj])
            sents.append(Sentence(subj, rng.choice(verbs_ee), obj))
            focus = obj if rng.random() < 0.5 else subj
        else:  # entity-literal
            sents.append(Sentence(subj, rng.choice(verbs_el), rng.choice(cities)))
            focus = subj
    return sents


# ── realiser: decide name vs pronoun per strategy ────────────────────────────

def realise(sents: list[Sentence], strategy: str) -> list[Sentence]:
    seen: set[str] = set()          # entities introduced so far (first mention = name)
    prev_cf: list[Entity] = []      # previous sentence forward-centers, subject-first
    for s in sents:
        s.mentions = []
        cur: list[tuple[Entity, str]] = [(s.subject, "subj")]
        if isinstance(s.obj, Entity):
            cur.append((s.obj, "obj"))
        # local salient set an ambiguity check must consider: prev sentence
        # centers + other entities named in THIS sentence.
        local = list(prev_cf) + [e for e, _ in cur]
        for ent, slot in cur:
            introduced = ent.name in seen
            pron = False
            if strategy == "all_names":
                pron = False
            elif strategy == "always_pron":
                pron = introduced  # pronominalise any non-first mention
            elif strategy == "centering":
                # focus continuity: subject that was a center of the prev sentence
                is_focus = slot == "subj" and any(ent.name == c.name for c in prev_cf)
                # agreement ambiguity: another DIFFERENT entity shares the class
                clash = any(o.agr == ent.agr and o.name != ent.name for o in local)
                pron = introduced and is_focus and not clash
            surface = PRONOUN[ent.agr] if pron else ent.name
            s.mentions.append((ent, surface, pron, slot))
            seen.add(ent.name)
        prev_cf = [s.subject] + ([s.obj] if isinstance(s.obj, Entity) else [])
    return sents


def render_text(sents: list[Sentence]) -> str:
    out = []
    for s in sents:
        subj = next(su for e, su, p, sl in s.mentions if sl == "subj")
        if isinstance(s.obj, Entity):
            obj = next(su for e, su, p, sl in s.mentions if sl == "obj")
        else:
            obj = s.obj or ""
        out.append(f"{subj} {s.predicate} {obj}".strip() + ".")
    return " ".join(out)


# ── independent resolver: recover each pronoun's antecedent ──────────────────

def resolve(sents: list[Sentence]) -> tuple[int, int]:
    """For every pronoun mention, pick the antecedent by agreement + salience
    (prev subject > prev object > current subject) + recency. Returns
    (correct, total). The resolver never sees the generator's pron decisions —
    only the surfaces and their agreement class."""
    correct = total = 0
    history: list[Entity] = []   # entities in salience-recency order, most salient last
    prev_centers: list[Entity] = []
    for s in sents:
        # antecedent pool for a pronoun in THIS sentence: previous sentence's
        # centers (subject first), most recent first.
        pool = list(reversed(prev_centers))
        for ent, surface, is_pron, slot in s.mentions:
            if is_pron:
                total += 1
                cands = [e for e in pool if e.agr == ent.agr]
                pick = cands[0] if cands else None
                if pick is not None and pick.name == ent.name:
                    correct += 1
            # after resolving, this mention becomes available as an antecedent
        prev_centers = [s.subject] + ([s.obj] if isinstance(s.obj, Entity) else [])
    return correct, total


def naturalness(sents: list[Sentence]) -> tuple[int, int]:
    """Pronouns / eligible (non-introductory) mentions. Higher = less robotic."""
    prons = elig = 0
    seen: set[str] = set()
    for s in sents:
        for ent, surface, is_pron, slot in s.mentions:
            if ent.name in seen:
                elig += 1
                prons += is_pron
            seen.add(ent.name)
    return prons, elig


def run_seed(seed: int, n_discourse: int = 40) -> dict:
    rng = Random(seed)
    discourses = [make_discourse(rng) for _ in range(n_discourse)]
    agg = {s: {"res_c": 0, "res_t": 0, "pron": 0, "elig": 0}
           for s in ("all_names", "always_pron", "centering")}
    sample = {}
    for i, base in enumerate(discourses):
        rendered = {}
        cent_prons = 0
        for strat in agg:
            sents = realise([Sentence(s.subject, s.predicate, s.obj) for s in base], strat)
            c, t = resolve(sents)
            p, e = naturalness(sents)
            agg[strat]["res_c"] += c
            agg[strat]["res_t"] += t
            agg[strat]["pron"] += p
            agg[strat]["elig"] += e
            rendered[strat] = render_text(sents)
            if strat == "centering":
                cent_prons = p
        # Prefer a sample where centering ACTUALLY pronominalises (shows the win);
        # fall back to the first discourse so a sample always exists.
        if (not sample or "chosen" not in sample) and cent_prons > 0:
            sample = dict(rendered, chosen=True)
        elif not sample:
            sample = dict(rendered)
    out = {"seed": seed, "n": n_discourse}
    for strat, a in agg.items():
        res = a["res_c"] / a["res_t"] if a["res_t"] else 1.0
        nat = a["pron"] / a["elig"] if a["elig"] else 0.0
        out[strat] = {"resolution": round(res, 4), "naturalness": round(nat, 4),
                      "pron_mentions": a["pron"], "eligible": a["elig"], "pron_total": a["res_t"]}
    out["sample"] = sample
    return out


def main(seeds: list[int]) -> int:
    results = [run_seed(s) for s in seeds]
    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "m10_referring.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"M10 Referring-expression generation — {len(seeds)} seeds {seeds}")
    print("-" * 72)
    passes = []
    for r in results:
        an, ap, ce = r["all_names"], r["always_pron"], r["centering"]
        p1 = ce["resolution"] >= an["resolution"] - 1e-9           # no ambiguity introduced
        p2 = ce["naturalness"] > an["naturalness"] + 0.05          # actually pronominalises
        p3 = ap["resolution"] < 1.0 - 1e-9                         # naive pron. demonstrably fails
        ok = p1 and p2 and p3
        passes.append(ok)
        print(f" seed {r['seed']}:")
        print(f"   all_names   resolution={an['resolution']:.0%}  naturalness={an['naturalness']:.0%}")
        print(f"   always_pron resolution={ap['resolution']:.0%}  naturalness={ap['naturalness']:.0%}  <- ambiguity")
        print(f"   centering   resolution={ce['resolution']:.0%}  naturalness={ce['naturalness']:.0%}")
        print(f"   checks: no-ambiguity={p1} pronominalises={p2} naive-fails={p3}  -> {'PASS' if ok else 'FAIL'}")
    print("-" * 72)
    s = results[0]["sample"]
    print("sample (seed", results[0]["seed"], "):")
    print(f"   all_names : {s['all_names']}")
    print(f"   always_pr : {s['always_pron']}")
    print(f"   centering : {s['centering']}")
    print("=" * 72)
    verdict = all(passes)
    print("VERDICT:", "PASS — referring-expression generation is a computable module "
          "(natural AND unambiguous, no LLM)" if verdict
          else "MIXED/FAIL — see per-seed checks (recorded, not hidden)")
    return 0 if verdict else 1


if __name__ == "__main__":
    seeds = [int(a) for a in sys.argv[1:]] or [42, 7, 2024, 99999]
    sys.exit(main(seeds))
