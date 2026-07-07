"""Parser-free construction discovery (spec §3.1.2).

Mine n-grams (n=2..6; n=2 supplies the marker+filler tail candidates), mask one
position per n-gram to form candidate frames (fixed tokens + one wildcard),
promote a frame when it recurs >= MIN_FRAME_COUNT times with
>= MIN_FILLER_DIVERSITY distinct fillers. Evidence is stored in an
EvidenceLedger per candidate; every promotion decision is a pure function of
ledger contents (spec §3.1.1).

Row-15 guard: `assert_not_vacuous` refuses to run discovery tests on a corpus
whose slots lack filler diversity — such a test cannot exercise the
diversity-based mechanism at all and would pass/fail vacuously.
"""

from __future__ import annotations

from ledger import EvidenceLedger, Observation, confidence, count, filler_diversity

MIN_FRAME_COUNT = 5
MIN_FILLER_DIVERSITY = 3

Frame = tuple[str, ...]  # fixed tokens with exactly one "%" wildcard


class VacuousTestError(AssertionError):
    """Raised when a corpus structurally cannot exercise discovery (row 15)."""


def mine_frames(token_lists: list[list[str]], verbs_by_sentence: list[str] | None = None,
                nmin: int = 2, nmax: int = 6) -> dict[Frame, EvidenceLedger]:
    """Return ledgers for ALL candidates; promotion is decided by the caller
    via `promoted()` so acceptance stays a pure function of ledger contents."""
    ledgers: dict[Frame, EvidenceLedger] = {}
    for si, tokens in enumerate(token_lists):
        predicate = verbs_by_sentence[si] if verbs_by_sentence else "?"
        for n in range(nmin, min(nmax, len(tokens)) + 1):
            for start in range(len(tokens) - n + 1):
                gram = tokens[start:start + n]
                for wi in range(n):
                    frame = tuple(gram[:wi] + ["%"] + gram[wi + 1:])
                    position = "final" if start + n == len(tokens) - 1 else "medial"
                    ledgers.setdefault(frame, EvidenceLedger()).add_observation(
                        Observation(predicate, position, gram[wi]))
    return ledgers


def promoted(ledgers: dict[Frame, EvidenceLedger],
             min_count: int = MIN_FRAME_COUNT,
             min_diversity: int = MIN_FILLER_DIVERSITY,
             ) -> dict[Frame, float]:
    """Frame -> confidence, for frames meeting the promotion criteria."""
    return {
        frame: confidence(led)
        for frame, led in ledgers.items()
        if count(led) >= min_count and filler_diversity(led) >= min_diversity
    }


def expected_frames(grammar) -> set[Frame]:
    """The frames the generating grammar guarantees recur with diverse fillers
    (the recovery target for spec row 1)."""
    exp: set[Frame] = set()
    for verb in grammar.verbs_trans:
        exp.add(("%", verb, grammar.article))        # agent slot
        exp.add((verb, grammar.article, "%"))        # object slot
    for verb in grammar.verbs_ditrans:
        exp.add(("%", verb))                         # agent slot (bigram)
        exp.add((verb, "%", grammar.article))        # recipient slot
    return exp


def assert_not_vacuous(grammar, sentences, min_diversity: int = MIN_FILLER_DIVERSITY) -> None:
    """Row 15: a slot exercised by tests must have >= min_diversity distinct
    fillers in the corpus, otherwise diversity-based discovery cannot fire and
    the test is structurally vacuous. Raise, do not silently pass."""
    fillers_by_slot: dict[str, set[str]] = {}
    for s in sentences:
        for role, value in s.frame.items():
            if role in ("verb", "article"):
                continue
            fillers_by_slot.setdefault(role, set()).add(value)
    thin = {r: len(v) for r, v in fillers_by_slot.items() if len(v) < min_diversity}
    if thin:
        raise VacuousTestError(
            f"corpus slots below filler diversity {min_diversity}: {thin} — "
            "this test cannot exercise wildcard discovery (spec row 15)")
