"""M0b — projection scaling benchmark (the spec's biggest untested assumption).

Measures, at ledger sizes 100 -> 100,000 events:
  - full view recomputation latency (p50/p95 over repeated runs)
  - single-cell query latency against the incremental materialized view
  - per-event incremental apply latency
  - peak memory of a full recomputation (tracemalloc)

Numbers are REPORTED and written to results/projection_bench.json; the M0b
pass criterion is that the curves are published and an incremental design
exists for anything super-linear — not that some magic constant is met.

Run: .venv/Scripts/python.exe experiments/ele/bench_projection.py [seed]
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

from projection import Event, IncrementalView, SemanticLedger, current_view


def synth_events(n: int, rng: random.Random) -> list[Event]:
    n_entities = max(10, n // 20)
    return [
        Event(
            entity=f"e{rng.randrange(n_entities)}",
            attribute=f"a{rng.randrange(10)}",
            value=f"v{rng.randrange(50)}",
            source=f"s{rng.randrange(20)}",
            trust=rng.random(),
            t=i,
            domain=rng.choice(("general", "work", "home")),
            kind="assert" if rng.random() > 0.05 else "retract",
        )
        for i in range(n)
    ]


def _pcts(samples: list[float]) -> tuple[float, float]:
    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return p50, p95


def bench(seed: int = 702945) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for size in (100, 1_000, 10_000, 100_000):
        events = synth_events(size, rng)
        ledger = SemanticLedger()
        inc = IncrementalView()

        apply_samples = []
        for e in events:
            ledger.append(e)
            t0 = time.perf_counter()
            inc.apply(e)
            apply_samples.append((time.perf_counter() - t0) * 1e6)

        reps = 20 if size <= 10_000 else 8
        full_samples = []
        for _ in range(reps):
            t0 = time.perf_counter()
            current_view(ledger, min_trust=0.2, policy="latest")
            full_samples.append((time.perf_counter() - t0) * 1000)

        query_samples = []
        keys = [(e.entity, e.attribute) for e in rng.sample(events, min(200, size))]
        for entity, attribute in keys:
            t0 = time.perf_counter()
            inc.get(entity, attribute)
            query_samples.append((time.perf_counter() - t0) * 1e6)

        tracemalloc.start()
        current_view(ledger, min_trust=0.2)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        f50, f95 = _pcts(full_samples)
        a50, a95 = _pcts(apply_samples)
        q50, q95 = _pcts(query_samples)
        rows.append({
            "events": size,
            "full_recompute_ms_p50": round(f50, 3),
            "full_recompute_ms_p95": round(f95, 3),
            "incremental_apply_us_p50": round(a50, 3),
            "incremental_apply_us_p95": round(a95, 3),
            "cell_query_us_p50": round(q50, 3),
            "cell_query_us_p95": round(q95, 3),
            "full_recompute_peak_mb": round(peak / 1e6, 2),
        })
    return rows


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 702945
    rows = bench(seed)
    out = Path(__file__).parent / "results" / "projection_bench.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"seed": seed, "rows": rows}, indent=2), encoding="utf-8")
    header = ("events", "full ms p50", "full ms p95", "apply us p50",
              "apply us p95", "query us p50", "query us p95", "peak MB")
    print(f"{'':>2}" + " | ".join(f"{h:>12}" for h in header))
    for r in rows:
        print("  " + " | ".join(f"{v:>12}" for v in r.values()))
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
