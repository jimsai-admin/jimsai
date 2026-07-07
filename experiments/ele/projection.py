"""Projection Engine (spec §3.3) — views computed from an append-only ledger.

The semantic ledger is append-only: assertions, retractions, and quotations are
EVENTS; nothing is ever mutated or deleted. Every "current state" is a VIEW —
a pure function of (events, parameters). Changing the resolution policy or the
time cutoff recomputes the view; the ledger is untouched.

This also closes the spec's row-5 gap ("which of two contradictory entries is
current truth?"): resolution is a PROJECTION PARAMETER (latest-wins,
highest-trust, ...), never a destructive write — both entries stay in the
ledger and in the view's audit trail.

IncrementalView maintains the same view with O(1) per-event updates and must
stay provably equivalent to full recomputation (property-tested in run_all,
benchmarked in bench_projection for M0b).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Event:
    entity: str
    attribute: str
    value: str
    source: str
    trust: float
    t: int                       # logical timestamp
    domain: str = "general"
    kind: str = "assert"         # assert | retract | quote


@dataclass
class SemanticLedger:
    events: list[Event] = field(default_factory=list)

    def append(self, event: Event) -> None:
        self.events.append(event)   # ONLY mutation allowed


@dataclass
class ViewCell:
    value: str | None
    provenance: list[Event]          # every event that touched this cell
    contradictions: list[str]        # competing live values (audit, not erasure)


def _resolve(cands: list[Event], policy: str) -> Event:
    if policy == "latest":
        return max(cands, key=lambda e: (e.t, e.source))
    if policy == "highest_trust":
        return max(cands, key=lambda e: (e.trust, e.t, e.source))
    raise ValueError(f"unknown policy {policy!r}")


def current_view(ledger: SemanticLedger, at: int | None = None,
                 min_trust: float = 0.0, domain: str | None = None,
                 policy: str = "latest") -> dict[tuple[str, str], ViewCell]:
    """Full recomputation — pure function of (events, parameters)."""
    touched: dict[tuple[str, str], list[Event]] = {}
    for e in ledger.events:
        if at is not None and e.t > at:
            continue
        if e.trust < min_trust or (domain and e.domain != domain):
            continue
        if e.kind == "quote":       # quotations are evidence about speech, not truth
            continue
        touched.setdefault((e.entity, e.attribute), []).append(e)

    view: dict[tuple[str, str], ViewCell] = {}
    for key, evs in touched.items():
        retracted = {(e.value, e.source) for e in evs if e.kind == "retract"}
        live = [e for e in evs if e.kind == "assert" and (e.value, e.source) not in retracted]
        if not live:
            view[key] = ViewCell(None, evs, [])
            continue
        winner = _resolve(live, policy)
        others = sorted({e.value for e in live if e.value != winner.value})
        view[key] = ViewCell(winner.value, evs, others)
    return view


class IncrementalView:
    """Materialized view with O(1)-amortized per-event maintenance."""

    def __init__(self, min_trust: float = 0.0, domain: str | None = None,
                 policy: str = "latest"):
        self.min_trust = min_trust
        self.domain = domain
        self.policy = policy
        self._cells: dict[tuple[str, str], list[Event]] = {}

    def apply(self, e: Event) -> None:
        if e.trust < self.min_trust or (self.domain and e.domain != self.domain):
            return
        if e.kind == "quote":
            return
        self._cells.setdefault((e.entity, e.attribute), []).append(e)

    def view(self) -> dict[tuple[str, str], ViewCell]:
        out: dict[tuple[str, str], ViewCell] = {}
        for key, evs in self._cells.items():
            retracted = {(e.value, e.source) for e in evs if e.kind == "retract"}
            live = [e for e in evs if e.kind == "assert" and (e.value, e.source) not in retracted]
            if not live:
                out[key] = ViewCell(None, evs, [])
                continue
            winner = _resolve(live, self.policy)
            others = sorted({e.value for e in live if e.value != winner.value})
            out[key] = ViewCell(winner.value, evs, others)
        return out

    def get(self, entity: str, attribute: str) -> ViewCell | None:
        evs = self._cells.get((entity, attribute))
        if not evs:
            return None
        retracted = {(e.value, e.source) for e in evs if e.kind == "retract"}
        live = [e for e in evs if e.kind == "assert" and (e.value, e.source) not in retracted]
        if not live:
            return ViewCell(None, evs, [])
        winner = _resolve(live, self.policy)
        others = sorted({e.value for e in live if e.value != winner.value})
        return ViewCell(winner.value, evs, others)
