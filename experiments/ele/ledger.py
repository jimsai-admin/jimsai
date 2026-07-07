"""Evidence Ledger — the ONLY mutable state (spec §3.1.1 invariant).

All behavioral metrics, confidence values, and acceptance decisions must be
derivable purely as a function of ledger contents, and recomputing from the
same ledger must produce identical results regardless of insertion order.
`run_all.py` P0 shuffles observations and asserts decision equality.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Observation:
    predicate: str            # the verb/head token co-occurring with this candidate
    attachment_position: str  # "final" | "medial"
    filler: str               # what filled the wildcard slot
    language: str = "nonce"
    timestamp: str = ""


@dataclass
class EvidenceLedger:
    observations: list[Observation] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def add_observation(self, obs: Observation) -> None:
        self.observations.append(obs)  # ONLY mutation allowed


# ── pure functions of ledger contents (no caching, no hidden state) ──

def count(ledger: EvidenceLedger) -> int:
    return len(ledger.observations)


def filler_diversity(ledger: EvidenceLedger) -> int:
    return len({o.filler for o in ledger.observations})


def predicate_counts(ledger: EvidenceLedger) -> dict[str, int]:
    return dict(sorted(Counter(o.predicate for o in ledger.observations).items()))


def cross_predicate_spread(ledger: EvidenceLedger) -> int:
    return len({o.predicate for o in ledger.observations})


def confidence(ledger: EvidenceLedger, k: float = 5.0) -> float:
    c = count(ledger)
    return c / (c + k)
