"""ELE experiment corpus — seeded generative grammar with known ground truth.

Anti-hardcoding (CLL Rules 1-2, E-Rules): this module contains NO word lists.
Every vocabulary item is a nonce word generated from the seed at runtime; the
grammar (which verbs take which shapes, which tails are core arguments vs
adjuncts vs verb-tied distractors) is sampled per seed and returned as the
ground truth the discovery/classification mechanisms must RECOVER. A developer
cannot tune the system against this corpus because the corpus is different
every run.

Ground-truth tail classes (spec §3.1.3):
  CORE      — direct-object slot (article + filler): obligatoriness 1.0 for its
              verbs AND high cross-verb spread (the row-11 trap for spread-only).
  ADJUNCT   — location/time/manner marker phrases: spread >= 3, oblig well below
              threshold. The `preferred` manner adjunct co-occurs with one verb
              at ~0.92 by preference (the row-13 calibration edge case).
  VERB_TIED — a distractor marker phrase tied to exactly ONE verb at ~0.90
              (the row-12 negative control that broke spread_weighted).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

_CONS = "bdfgklmnprstvz"
_VOWS = "aeiou"

CORE = "CORE_ARGUMENT"
ADJUNCT = "ADJUNCT"
VERB_TIED = "VERB_TIED"


def _nonce(rng: random.Random, used: set[str], syllables: tuple[int, int] = (2, 3)) -> str:
    while True:
        n = rng.randint(*syllables)
        word = "".join(rng.choice(_CONS) + rng.choice(_VOWS) for _ in range(n))
        if word not in used:
            used.add(word)
            return word


@dataclass
class Grammar:
    verbs_trans: list[str]
    verbs_ditrans: list[str]
    agents: list[str]          # also used as recipients (people receive things)
    objects: list[str]
    adjectives: list[str]
    locations: list[str]
    manners: list[str]
    times: list[str]
    dist_fillers: list[str]
    article: str
    loc_mark: str
    man_mark: str
    time_mark: str
    dist_mark: str
    loc_suffix: str            # morphological locative for the row-14 regression
    preferred_verb: str        # ~0.92 manner collocation (row 13 edge case)
    tied_verb: str             # sole verb of the distractor phrase (row 12)
    truth_tails: dict[tuple[str, str], str] = field(default_factory=dict)
    categories: dict[str, str] = field(default_factory=dict)
    reserved_pairs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def all_verbs(self) -> list[str]:
        return self.verbs_trans + self.verbs_ditrans


@dataclass
class Sentence:
    tokens: list[str]
    verb: str
    frame: dict[str, str]              # role -> value (verb/article are DATA)
    core_roles: tuple[str, ...]        # ordered as realized
    adjunct_roles: tuple[str, ...]


def build_grammar(seed: int) -> Grammar:
    rng = random.Random(seed)
    used: set[str] = set()
    g = Grammar(
        verbs_trans=[_nonce(rng, used) for _ in range(4)],
        verbs_ditrans=[_nonce(rng, used) for _ in range(3)],
        agents=[_nonce(rng, used) for _ in range(8)],
        objects=[_nonce(rng, used) for _ in range(10)],
        adjectives=[_nonce(rng, used) for _ in range(6)],
        locations=[_nonce(rng, used) for _ in range(6)],
        manners=[_nonce(rng, used) for _ in range(5)],
        times=[_nonce(rng, used) for _ in range(5)],
        dist_fillers=[_nonce(rng, used) for _ in range(4)],
        article=_nonce(rng, used, (1, 1)),
        loc_mark=_nonce(rng, used, (1, 1)),
        man_mark=_nonce(rng, used, (1, 1)),
        time_mark=_nonce(rng, used, (1, 1)),
        dist_mark=_nonce(rng, used, (1, 1)),
        loc_suffix=_nonce(rng, used, (1, 1)),
        preferred_verb="",
        tied_verb="",
    )
    g.preferred_verb, g.tied_verb = rng.sample(g.verbs_trans, 2)
    g.truth_tails = {
        (g.article, "%"): CORE,        # row 11: determiners generalize — spread-only trap
        (g.loc_mark, "%"): ADJUNCT,
        (g.time_mark, "%"): ADJUNCT,
        (g.man_mark, "%"): ADJUNCT,    # row 13: 0.92-collocated with preferred_verb
        (g.dist_mark, "%"): VERB_TIED,  # row 12: tied to tied_verb only
    }
    for w in g.agents:
        g.categories[w] = "NOUN_AGENT"
    for w in g.objects:
        g.categories[w] = "NOUN_OBJECT"
    for w in g.all_verbs:
        g.categories[w] = "VERB"
    for w in g.adjectives:
        g.categories[w] = "ADJ"
    return g


def realize(g: Grammar, frame: dict[str, str], core_roles: tuple[str, ...],
            adjunct_roles: tuple[str, ...] = ()) -> list[str]:
    """The grammar's own deterministic realization — ground truth for renders."""
    tokens = [frame[r] for r in core_roles]
    marks = {"location": g.loc_mark, "manner": g.man_mark,
             "time": g.time_mark, "dist": g.dist_mark}
    for role in adjunct_roles:
        tokens += [marks[role], frame[role]]
    return tokens + ["."]


def _alloc(rng: random.Random, n: int, fraction: float) -> set[int]:
    """Exact-count allocation so critical proportions (0.92, 0.90) are stable."""
    return set(rng.sample(range(n), round(n * fraction)))


def generate(seed: int, n_per_verb: int = 120, with_adjectives: bool = False,
             ) -> tuple[Grammar, list[Sentence]]:
    g = build_grammar(seed)
    rng = random.Random(seed + 1)
    # Reserve (agent, object) pairs BEFORE generation: the row-6 held-out
    # compositional combos must never co-occur in training, by construction.
    all_pairs = [(a, o) for a in g.agents for o in g.objects]
    g.reserved_pairs = rng.sample(all_pairs, 15)
    reserved = set(g.reserved_pairs)
    sentences: list[Sentence] = []

    for verb in g.all_verbs:
        ditrans = verb in g.verbs_ditrans
        loc_idx = _alloc(rng, n_per_verb, 0.30)
        time_idx = _alloc(rng, n_per_verb, 0.25)
        if verb == g.preferred_verb:
            man_idx = _alloc(rng, n_per_verb, 0.92)   # row 13: preference, not requirement
        elif verb in g.verbs_trans and verb != g.tied_verb:
            man_idx = _alloc(rng, n_per_verb, 0.05)   # gives manner spread >= 3
        else:
            man_idx = set()
        dist_idx = _alloc(rng, n_per_verb, 0.90) if verb == g.tied_verb else set()

        for i in range(n_per_verb):
            while True:
                agent, obj = rng.choice(g.agents), rng.choice(g.objects)
                if (agent, obj) not in reserved:
                    break
            frame = {"agent": agent, "verb": verb, "article": g.article, "object": obj}
            if ditrans:
                recipient = rng.choice(g.agents)
                while recipient == agent:   # distinct values keep template induction exact
                    recipient = rng.choice(g.agents)
                frame["recipient"] = recipient
                core: tuple[str, ...] = ("agent", "verb", "recipient", "article", "object")
            else:
                core = ("agent", "verb", "article", "object")
            adjuncts: list[str] = []
            if i in loc_idx:
                frame["location"] = rng.choice(g.locations)
                adjuncts.append("location")
            if i in time_idx:
                frame["time"] = rng.choice(g.times)
                adjuncts.append("time")
            if i in man_idx:
                frame["manner"] = rng.choice(g.manners)
                adjuncts.append("manner")
            if i in dist_idx:
                frame["dist"] = rng.choice(g.dist_fillers)
                adjuncts.append("dist")
            tokens = realize(g, frame, core, tuple(adjuncts))
            if with_adjectives and rng.random() < 0.30:
                adj = rng.choice(g.adjectives)
                pos = tokens.index(frame["object"])
                tokens = tokens[:pos] + [adj] + tokens[pos:]
            sentences.append(Sentence(tokens, verb, frame, core, tuple(adjuncts)))

    rng.shuffle(sentences)
    return g, sentences


def generate_morph(seed: int, n: int = 80) -> tuple[Grammar, list[list[str]], set[str]]:
    """Row-14 corpus: locative expressed morphologically (location+suffix as one
    token). Returns (grammar, token lists, truth set of suffixed location tokens)."""
    g = build_grammar(seed)
    rng = random.Random(seed + 7)
    token_lists: list[list[str]] = []
    truth: set[str] = set()
    for _ in range(n):
        verb = rng.choice(g.verbs_trans)
        loc_tok = rng.choice(g.locations) + g.loc_suffix
        truth.add(loc_tok)
        token_lists.append([rng.choice(g.agents), verb, g.article,
                            rng.choice(g.objects), loc_tok, "."])
    return g, token_lists, truth


def held_out_pairs(g: Grammar, sentences: list[Sentence], rng: random.Random,
                   n: int = 30) -> list[tuple[dict[str, str], tuple[str, ...], list[str]]]:
    """Row-6 held-out COMPOSITIONAL combos: the reserved (agent, object) pairs,
    guaranteed absent from training by construction (checked anyway)."""
    seen = {(s.frame["agent"], s.frame["object"]) for s in sentences}
    leaked = seen & set(g.reserved_pairs)
    if leaked:
        raise AssertionError(f"reserved pairs leaked into training: {leaked}")
    combos = []
    for agent, obj in g.reserved_pairs:
        for verb in g.verbs_trans:
            frame = {"agent": agent, "verb": verb, "article": g.article, "object": obj}
            core = ("agent", "verb", "article", "object")
            combos.append((frame, core, realize(g, frame, core)))
    rng.shuffle(combos)
    return combos[:n]
