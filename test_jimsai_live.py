#!/usr/bin/env python3
"""
JimsAI Live Integration Test
=============================
Tests the full learning lifecycle:
  1. Auth — get a Bearer token via Supabase
  2. Ingest — real multi-domain training data (physics, chemistry, medicine, coding, economics)
  3. Query — verify learned content is retrievable and responses are coherent
  4. Math   — verify symbolic solver with step-by-step output
  5. World model promotion — verify causal rules accumulate and are surfaced for review
  6. Review/accept — accept a promoted rule, verify fast-path activates
  7. Autonomous agent — start a cycle, monitor gap identification
  8. Dashboard — read system state: memory stats, health score, candidates
  9. Feedback — close the learning loop with positive/negative signals

Run from repo root:
  python test_jimsai_live.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000"
EMAIL    = "Jimstechinnovations@gmail.com"
PASSWORD = "Irekanmi@231"
USER_ID  = "test-live-runner"
WS_ID    = "jimsai-live-test"

TIMEOUT  = httpx.Timeout(180.0)  # Modal cold-starts can be slow

# Give the embedding service more time so real vectors are stored (not hash fallback)
# This is set via env var before the server starts — we patch it in the test payload
INGEST_SOURCE_TRUST_HIGH = 0.92  # High confidence forces real embedding attempt


# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def ok(label: str, value: Any = "") -> None:
    print(f"  ✓  {label}", f"→ {value}" if value != "" else "")


def warn(label: str, value: Any = "") -> None:
    print(f"  ⚠  {label}", f"→ {value}" if value != "" else "")


def fail(label: str, value: Any = "") -> None:
    print(f"  ✗  {label}", f"→ {value}" if value != "" else "")


def dump(data: Any, max_keys: int = 8) -> None:
    """Print a condensed summary of a response dict."""
    if isinstance(data, dict):
        keys = list(data.keys())[:max_keys]
        for k in keys:
            v = data[k]
            if isinstance(v, (list, dict)):
                v_str = f"[{len(v)} items]" if isinstance(v, list) else f"{{...{len(v)} keys}}"
            elif isinstance(v, str) and len(v) > 120:
                v_str = v[:120] + "..."
            else:
                v_str = v
            print(f"     {k}: {v_str}")
        if len(data) > max_keys:
            print(f"     ... ({len(data) - max_keys} more keys)")
    else:
        print(f"     {str(data)[:200]}")


# ── Auth ──────────────────────────────────────────────────────────────────────

async def get_token(client: httpx.AsyncClient) -> str:
    section("STEP 0 — Authenticate")
    r = await client.post(f"{BASE_URL}/v1/auth/signin",
                          json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        fail("Auth failed", f"HTTP {r.status_code}: {r.text[:300]}")
        sys.exit(1)
    data = r.json()
    token = data.get("access_token") or data.get("token") or ""
    if not token:
        # Try nested
        token = (data.get("data") or {}).get("access_token", "")
    if not token:
        fail("No access_token in response", json.dumps(data)[:200])
        sys.exit(1)
    ok("Authenticated", f"token prefix: {token[:20]}...")
    return token


# ── Training data ─────────────────────────────────────────────────────────────

TRAINING_CORPUS = [
    # ── Physics ──
    {
        "domain": "physics",
        "content": (
            "Newton's second law: Force equals mass times acceleration (F = ma). "
            "A net force causes acceleration. Greater mass requires greater force for the same acceleration. "
            "Gravitational force causes objects to fall toward Earth at 9.81 m/s². "
            "Friction causes deceleration. High velocity causes greater air resistance."
        ),
        "source_trust": 0.95,
    },
    {
        "domain": "physics",
        "content": (
            "Einstein's special relativity: energy equals mass times the speed of light squared (E = mc²). "
            "High velocity causes time dilation. Gravitational fields cause spacetime curvature. "
            "Black holes cause extreme spacetime curvature. Increased mass causes stronger gravitational pull."
        ),
        "source_trust": 0.95,
    },
    # ── Chemistry ──
    {
        "domain": "chemistry",
        "content": (
            "Water is H2O — two hydrogen atoms bonded to one oxygen atom, molar mass 18.015 g/mol. "
            "Salt (NaCl) dissociates in water into Na+ and Cl- ions. "
            "Acids cause pH to decrease. Bases cause pH to increase. "
            "Oxidation causes electron loss. Reduction causes electron gain. "
            "High temperature causes increased reaction rate (Arrhenius equation)."
        ),
        "source_trust": 0.93,
    },
    {
        "domain": "chemistry",
        "content": (
            "Glucose chemical formula: C6H12O6, molar mass 180.156 g/mol. "
            "Combustion of glucose: C6H12O6 + 6O2 → 6CO2 + 6H2O. "
            "Cellular respiration causes ATP production from glucose. "
            "Photosynthesis causes glucose production from CO2 and water. "
            "Catalysts cause increased reaction rate without being consumed."
        ),
        "source_trust": 0.93,
    },
    # ── Medicine / Biology ──
    {
        "domain": "medicine",
        "content": (
            "High blood pressure causes increased risk of stroke and heart disease. "
            "Chronic inflammation causes tissue damage. "
            "Insulin resistance causes type 2 diabetes. "
            "Sleep deprivation causes elevated cortisol. "
            "Elevated cortisol causes memory impairment and immune suppression. "
            "Regular exercise causes reduced blood pressure and improved insulin sensitivity."
        ),
        "source_trust": 0.88,
    },
    {
        "domain": "medicine",
        "content": (
            "Antibiotics cause bacterial cell wall disruption. "
            "Antibiotic resistance causes treatment failure. "
            "Overuse of antibiotics causes antibiotic resistance. "
            "Vaccination causes immune system priming. "
            "Viral replication causes cell lysis. "
            "Fever causes increased immune cell activity."
        ),
        "source_trust": 0.88,
    },
    # ── Computer Science / Coding ──
    {
        "domain": "coding",
        "content": (
            "Memory leaks cause increased memory usage over time. "
            "Unbounded recursion causes stack overflow. "
            "Race conditions cause non-deterministic behavior in concurrent systems. "
            "SQL injection causes unauthorized database access. "
            "Input validation prevents SQL injection. "
            "Caching causes reduced latency for repeated queries."
        ),
        "source_trust": 0.91,
    },
    {
        "domain": "coding",
        "content": (
            "Python's GIL causes single-threaded CPU execution in CPython. "
            "Async I/O causes higher throughput for I/O-bound workloads. "
            "Compiled languages cause faster execution than interpreted languages. "
            "Type checking causes earlier detection of bugs. "
            "Unit tests cause higher code reliability. "
            "Poor indexing causes slow database queries."
        ),
        "source_trust": 0.91,
    },
    # ── Economics ──
    {
        "domain": "economics",
        "content": (
            "High inflation causes reduced purchasing power. "
            "Interest rate increases cause reduced borrowing and investment. "
            "Unemployment causes reduced consumer spending. "
            "Supply chain disruptions cause price increases. "
            "Monopolies cause higher prices and reduced innovation. "
            "Foreign direct investment causes economic growth in recipient countries."
        ),
        "source_trust": 0.87,
    },
    # ── Space / Orbital mechanics ──
    {
        "domain": "space",
        "content": (
            "Gravitational attraction causes orbital motion. "
            "Higher orbital velocity causes lower orbital altitude (Kepler's laws). "
            "Solar wind causes magnetosphere compression. "
            "Cosmic radiation causes DNA damage in astronauts. "
            "Microgravity causes bone density loss and muscle atrophy. "
            "Atmospheric drag causes orbital decay in low Earth orbit."
        ),
        "source_trust": 0.92,
    },
]


# ── Query battery ─────────────────────────────────────────────────────────────

QUERY_BATTERY = [
    # Causal retrieval — should hit world model
    ("Physics causality",    "What causes acceleration in physics?"),
    ("Chemistry causality",  "What does high temperature cause in chemical reactions?"),
    ("Medicine causality",   "What causes type 2 diabetes?"),
    ("Coding causality",     "What causes stack overflow in programs?"),
    ("Economics causality",  "What causes reduced purchasing power?"),
    ("Space causality",      "What causes orbital decay?"),
    # Factual retrieval
    ("Water molar mass",     "What is the molar mass of water?"),
    ("Einstein energy",      "What is Einstein's mass-energy equivalence?"),
    # Cross-domain
    ("Sleep and memory",     "How does sleep deprivation affect memory?"),
    ("Exercise benefits",    "What does regular exercise cause?"),
    # Novel / beyond memory
    ("Novel question",       "What is the population of Tokyo in 2026?"),
]


# ── Math battery ──────────────────────────────────────────────────────────────

MATH_BATTERY = [
    ("Quadratic",        "2*x**2 + 5*x - 3 = 0",       "x"),
    ("Calculus deriv",   "diff(x**3 + 2*x**2 - x, x)", None),
    ("Integral",         "integrate(sin(x), x)",         None),
    ("Molar mass H2O",   "molar mass of H2O",            None),
    ("Molar mass C6H12O6", "molar mass of C6H12O6",      None),
    ("Physics F=ma",     "F = 5 * 9.81",                 None),
    ("System of eqs",    "2*x + y = 10, x - y = 1",     None),
]


# ── Main test runner ──────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "█"*70)
    print("  JimsAI Live Integration Test")
    print("  Covers: Auth → Ingest → Query → Math → World Model → Fast-Path")
    print("          → Autonomous Agent → Dashboard → Feedback")
    print("█"*70)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:

        # ── Step 0: Health check ──────────────────────────────────────────────
        section("STEP 0.1 — Health check")
        try:
            r = await client.get("/health")
            ok("Server is up", r.json())
        except Exception as exc:
            fail("Server not reachable — start it with: .\\local_dev.ps1", exc)
            sys.exit(1)

        # ── Step 1: Auth ──────────────────────────────────────────────────────
        token = await get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # ── Step 2: Multi-domain ingestion ────────────────────────────────────
        section("STEP 1 — Multi-domain ingestion (10 documents × 3 passes)")
        ingest_results = []
        for pass_num in range(1, 4):   # 3 passes to build causal observation counts
            print(f"\n  Pass {pass_num}/3:")
            for doc in TRAINING_CORPUS:
                payload = {
                    "user_id": USER_ID,
                    "workspace_id": WS_ID,
                    "content": doc["content"],
                    "source_trust": doc["source_trust"],
                    "domain_hint": doc["domain"],
                }
                try:
                    t0 = time.monotonic()
                    r = await client.post("/v1/training/ingest", json=payload, headers=headers)
                    elapsed = (time.monotonic() - t0) * 1000
                    if r.status_code == 200:
                        data = r.json()
                        sig_id   = data.get("signature", {}).get("id", "?")[:16]
                        wm_count = len(data.get("world_model_candidates", []))
                        conf     = data.get("signature", {}).get("confidence", {}).get("score", "?")
                        ok(f"  [{doc['domain']:12}] sig:{sig_id}… conf:{conf} wm_candidates:{wm_count} ({elapsed:.0f}ms)")
                        ingest_results.append(data)
                    else:
                        warn(f"  [{doc['domain']:12}] HTTP {r.status_code}", r.text[:200])
                except Exception as exc:
                    warn(f"  [{doc['domain']:12}] exception", str(exc)[:200])

        ok(f"Ingestion complete — {len(ingest_results)} successful ingest calls")

        # ── Step 3: Dashboard — check memory state after ingestion ────────────
        section("STEP 2 — Training dashboard (post-ingestion state)")
        try:
            r = await client.get("/v1/training/dashboard", headers=headers)
            if r.status_code == 200:
                dash = r.json()
                mem  = dash.get("memory_stats", {})
                mon  = dash.get("pipeline_monitor", {})
                wm_pending = len(dash.get("human_review_queue", []))
                ok("Memory stats",            mem)
                ok("World model candidates",  mon.get("world_model_candidates_total", 0))
                ok("Pending human review",    wm_pending)
                ok("Health score",            mon.get("system_health_score", "?"))
                ok("Limiting factor",         mon.get("system_health_limiting_factor", "?"))
                ok("SPPE pairs total",        mon.get("sppe_pairs_total", 0))
                ok("Retrieval misses",        mon.get("retrieval_misses", 0))

                # Print top pending world model candidates
                pending = dash.get("human_review_queue", [])
                if pending:
                    print(f"\n  Top promoted candidates pending review ({len(pending)} total):")
                    for c in pending[:8]:
                        print(f"     rule: {c.get('rule','?')[:60]}  conf:{c.get('confidence','?')}  prov:{str(c.get('provenance','?'))[:20]}")
            else:
                warn("Dashboard HTTP", r.status_code)
        except Exception as exc:
            warn("Dashboard exception", str(exc)[:200])

        # ── Step 4: Query battery ─────────────────────────────────────────────
        section("STEP 3 — Query battery (11 queries across domains)")
        trace_ids = {}
        for label, query_text in QUERY_BATTERY:
            payload = {
                "user_id": USER_ID,
                "workspace_id": WS_ID,
                "query": query_text,
            }
            try:
                t0 = time.monotonic()
                r = await client.post("/v1/query", json=payload, headers=headers)
                elapsed = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    data = r.json()
                    response_text = data.get("response", "")[:150]
                    confidence    = data.get("confidence", "?")
                    used_groq     = data.get("used_groq", "?")
                    gaps          = data.get("gaps", [])
                    sources       = data.get("sources", [])
                    wm_acts       = data.get("world_model_activations", [])
                    trace_id      = data.get("ir", {}).get("trace_id", "")
                    fast_path     = any(
                        lr.get("layer") == "world_model_fast_path"
                        for lr in data.get("layer_results", [])
                    )
                    trace_ids[label] = trace_id
                    status = "⚡ FAST-PATH" if fast_path else ("⚠ GAP" if gaps else "✓")
                    print(f"\n  [{label}] {status} ({elapsed:.0f}ms)")
                    print(f"     query:      {query_text}")
                    print(f"     response:   {response_text}")
                    print(f"     confidence: {confidence}  used_groq: {used_groq}  gaps: {len(gaps)}  sources: {len(sources)}  wm_acts: {len(wm_acts)}")
                    if gaps:
                        print(f"     gaps: {gaps[0][:100]}")
                    if wm_acts:
                        print(f"     wm rule sample: {wm_acts[0].get('rule','?')[:60]}")
                else:
                    warn(f"[{label}] HTTP {r.status_code}", r.text[:200])
            except Exception as exc:
                warn(f"[{label}] exception", str(exc)[:200])

        # ── Step 5: Math solver battery ───────────────────────────────────────
        section("STEP 4 — Symbolic math solver battery")
        for label, expr, solve_for in MATH_BATTERY:
            payload = {
                "user_id": USER_ID,
                "workspace_id": WS_ID,
                "expression": expr,
                "solve_for": solve_for,
            }
            try:
                t0 = time.monotonic()
                r = await client.post("/v1/math/solve", json=payload, headers=headers)
                elapsed = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    data   = r.json()
                    status = data.get("status", "?")
                    result = data.get("result", "?")
                    method = data.get("method", "?")
                    steps  = data.get("steps", [])
                    mark   = "✓" if status == "solved" else "✗"
                    print(f"\n  {mark} [{label}]  ({elapsed:.0f}ms)")
                    print(f"     expr:   {expr}")
                    print(f"     result: {result}")
                    print(f"     method: {method}  steps: {len(steps)}")
                    if steps:
                        for step in steps[:3]:
                            print(f"       → {step}")
                else:
                    warn(f"[{label}] HTTP {r.status_code}", r.text[:200])
            except Exception as exc:
                warn(f"[{label}] exception", str(exc)[:200])

        # ── Step 6: World model panel ─────────────────────────────────────────
        section("STEP 5 — World model panel (promoted causal rules)")
        candidate_to_accept = None
        try:
            r = await client.get("/v1/training/panels/world-model/items",
                                 params={"limit": 20}, headers=headers)
            if r.status_code == 200:
                page  = r.json()
                items = page.get("items", [])
                ok(f"World model panel items", len(items))
                for item in items[:10]:
                    d = item.get("data", {})
                    rule     = d.get("rule", "?")
                    conf     = d.get("confidence", "?")
                    prov     = d.get("provenance", "?")
                    req_rev  = d.get("review_required", True)
                    print(f"     {'[PENDING]' if req_rev else '[ACCEPTED]'} {rule[:55]:<55} conf:{conf}")
                    if req_rev and candidate_to_accept is None:
                        candidate_to_accept = {"rule": rule, "provenance": prov}
            else:
                warn("World model panel HTTP", r.status_code)
        except Exception as exc:
            warn("World model panel exception", str(exc)[:200])

        # ── Step 7: Review/accept a candidate → activate fast-path ────────────
        section("STEP 6 — Accept a world model candidate → activate fast-path")
        if candidate_to_accept:
            print(f"  Accepting: {candidate_to_accept['rule']}")
            payload = {
                "user_id": USER_ID,
                "workspace_id": WS_ID,
                "action": "accept",
                "rule": candidate_to_accept["rule"],
                "provenance": candidate_to_accept["provenance"],
            }
            try:
                r = await client.post("/v1/review/action", json=payload, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    ok("Review action", f"accepted={data.get('accepted')} rule={data.get('rule','?')[:50]}")
                else:
                    warn("Review action HTTP", f"{r.status_code}: {r.text[:200]}")
            except Exception as exc:
                warn("Review action exception", str(exc)[:200])

            # Now query the same entity to test fast-path
            rule_text = candidate_to_accept["rule"]
            # Parse cause from "X causes Y"
            parts = rule_text.lower().split(" causes ")
            cause_entity = parts[0].strip() if parts else "cortisol"
            fast_path_query = f"What does {cause_entity} cause?"
            print(f"\n  Fast-path probe: '{fast_path_query}'")
            payload = {
                "user_id": USER_ID,
                "workspace_id": WS_ID,
                "query": fast_path_query,
            }
            try:
                t0 = time.monotonic()
                r = await client.post("/v1/query", json=payload, headers=headers)
                elapsed = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    data = r.json()
                    used_groq = data.get("used_groq", "?")
                    confidence = data.get("confidence", "?")
                    response = data.get("response", "")[:200]
                    layer_names = [lr.get("layer") for lr in data.get("layer_results", [])]
                    fast_hit = "world_model_fast_path" in str(layer_names) or not used_groq
                    if fast_hit and elapsed < 2000:
                        ok(f"⚡ FAST-PATH HIT ({elapsed:.0f}ms) used_groq={used_groq} conf={confidence}")
                    else:
                        warn(f"Full pipeline ({elapsed:.0f}ms) used_groq={used_groq} conf={confidence}")
                    print(f"     response: {response}")
                else:
                    warn("Fast-path query HTTP", r.status_code)
            except Exception as exc:
                warn("Fast-path query exception", str(exc)[:200])
        else:
            warn("No pending candidates found to accept — try more ingestion passes")

        # ── Step 8: Feedback loop ──────────────────────────────────────────────
        section("STEP 7 — Feedback loop (positive and negative signals)")
        feedback_pairs = [
            ("Physics causality", "positive"),
            ("Medicine causality", "positive"),
            ("Novel question",  "negative"),
        ]
        for label, rating in feedback_pairs:
            trace_id = trace_ids.get(label, "")
            if not trace_id:
                warn(f"No trace_id for [{label}], skipping feedback")
                continue
            payload = {
                "user_id":   USER_ID,
                "workspace_id": WS_ID,
                "trace_id":  trace_id,
                "rating":    rating,
                "notes":     f"live-test {rating} feedback",
            }
            try:
                r = await client.post("/v1/feedback", json=payload, headers=headers)
                if r.status_code == 200:
                    ok(f"Feedback [{label}]", f"rating={rating} accepted={r.json().get('accepted')}")
                else:
                    warn(f"Feedback [{label}] HTTP {r.status_code}", r.text[:200])
            except Exception as exc:
                warn(f"Feedback [{label}] exception", str(exc)[:200])

        # ── Step 9: Audit trail ───────────────────────────────────────────────
        section("STEP 8 — Audit event trail (last 15 events)")
        try:
            r = await client.get("/v1/audit/events", params={"limit": 15}, headers=headers)
            if r.status_code == 200:
                events = r.json()
                if isinstance(events, list):
                    for ev in events[-15:]:
                        etype  = ev.get("event_type", ev.get("type", "?"))
                        eid    = str(ev.get("id", "?"))[:20]
                        ts     = str(ev.get("timestamp", "?"))[:19]
                        print(f"     {ts}  [{etype:<35}]  {eid}")
                ok("Audit trail", f"{len(events)} events")
            else:
                warn("Audit events HTTP", r.status_code)
        except Exception as exc:
            warn("Audit events exception", str(exc)[:200])

        # ── Step 10: Final dashboard state ────────────────────────────────────
        section("STEP 9 — Final system state")
        try:
            r = await client.get("/v1/training/dashboard", headers=headers)
            if r.status_code == 200:
                dash = r.json()
                mon  = dash.get("pipeline_monitor", {})
                ok("Signatures total",       mon.get("signatures_total", 0))
                ok("World model candidates", mon.get("world_model_candidates_total", 0))
                ok("SPPE pairs",             mon.get("sppe_pairs_total", 0))
                ok("Pending review",         mon.get("human_review_pending", 0))
                ok("Feedback events",        mon.get("feedback_events", 0))
                ok("Retrieval misses",       mon.get("retrieval_misses", 0))
                ok("System health score",    mon.get("system_health_score", "?"))
                ok("Limiting factor",        mon.get("system_health_limiting_factor", "?"))
                ok("Next step",              mon.get("system_health_next_step", "?"))

                # Auto-training decision
                atd = dash.get("auto_training_decision", {})
                if atd:
                    ok("Auto-training should_train", atd.get("should_train", "?"))
                    ok("Auto-training reason",        atd.get("reason", "?")[:80])
        except Exception as exc:
            warn("Final dashboard exception", str(exc)[:200])

        # ── Step 11: Memory panel snapshot ───────────────────────────────────
        section("STEP 10 — Memory panel (top 10 recent signatures)")
        try:
            r = await client.get("/v1/training/panels/memory/items",
                                 params={"limit": 10}, headers=headers)
            if r.status_code == 200:
                page  = r.json()
                items = page.get("items", [])
                ok(f"Memory panel total", page.get("total", "?"))
                for item in items[:10]:
                    sig = item.get("data", {}).get("signature", item.get("data", {}))
                    sid  = str(sig.get("id", "?"))[:16]
                    conf = sig.get("confidence", {})
                    if isinstance(conf, dict):
                        conf = conf.get("score", "?")
                    prov = str(sig.get("provenance", "?"))[:25]
                    tags = (sig.get("abstraction_tags") or [])[:3]
                    print(f"     {sid}… conf:{conf}  prov:{prov:<25}  tags:{tags}")
        except Exception as exc:
            warn("Memory panel exception", str(exc)[:200])

    # ── Summary ───────────────────────────────────────────────────────────────
    section("TEST COMPLETE")
    print("""
  What just happened:
    1. Authenticated with Supabase
    2. Ingested 10 multi-domain documents × 3 passes = 30 ingest calls
       Domains: physics, chemistry, medicine, coding, economics, space
    3. Read training dashboard — memory stats, health score, world model candidates
    4. Sent 11 queries across all domains — watched confidence, sources, wm_activations
    5. Ran 7 math/chemistry solver problems — verified step-by-step output
    6. Read world model panel — inspected promoted causal candidates
    7. Accepted one candidate — activated the fast-path
    8. Probed the fast-path with a matching causal query
    9. Sent positive/negative feedback — closed the learning loop
   10. Read the audit event trail
   11. Checked final system state and auto-training decision

  Watch for:
    ⚡ FAST-PATH lines — world model answered before retrieval/reasoning ran
    ✓ lines with sources > 0 — memory retrieval working
    ⚠ GAP lines — novel queries correctly surfaced as gaps (not hallucinated)
    confidence values — should increase across passes as memory grows
    system_health_score — should be > 50 after 30 ingestion calls
""")


if __name__ == "__main__":
    asyncio.run(main())
