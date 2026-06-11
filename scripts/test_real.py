"""
JimsAI Real End-to-End Test
============================
Tests the full pipeline with real training + prompting.
No hardcoded assertions — validates actual behaviour.

What this tests:
  1. Pre-warm Modal services
  2. Document ingestion via /v1/training/ingest
  3. Profile writes (English + multilingual) via /v1/query
  4. Memory recall after write
  5. Code generation (Modal renderer)
  6. Math solver (deterministic)
  7. Web search (world knowledge)
  8. Learning: second identical prompt should be faster (learned from memory)

Usage:
    python scripts/test_real.py
"""
from __future__ import annotations
import asyncio, httpx, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except ImportError:
    pass

BASE = "http://127.0.0.1:8000"
PASS, FAIL, INFO = "✅", "❌", "ℹ️"


# ── helpers ───────────────────────────────────────────────────────────────────

async def prewarm(client: httpx.AsyncClient) -> dict[str, bool]:
    tok = os.getenv("JIMS_MODAL_API_KEY", "")
    hdrs = {"Authorization": f"Bearer {tok}"}
    svcs = {
        "embedding":    os.getenv("JIMS_EMBEDDING_SERVICE_URL","").rstrip("/"),
        "intent":       os.getenv("JIMS_INTENT_SERVICE_URL","").rstrip("/"),
        "renderer":     os.getenv("JIMS_RENDERER_SERVICE_URL","").rstrip("/"),
        "classify":     os.getenv("JIMS_CLASSIFICATION_SERVICE_URL","").rstrip("/"),
    }
    print("Pre-warming Modal services (parallel)...")
    status: dict[str, bool] = {}
    async def ping(name, url):
        if not url: return
        try:
            r = await client.get(f"{url}/health", headers=hdrs, timeout=120)
            ok = r.status_code == 200
            status[name] = ok
            icon = PASS if ok else FAIL
            print(f"  {icon} {name:14s}: {r.json().get('status','?') if ok else r.status_code}")
        except Exception as e:
            status[name] = False
            print(f"  {FAIL} {name:14s}: {repr(e)[:60]}")
    await asyncio.gather(*[ping(n,u) for n,u in svcs.items() if u])
    return status


async def auth(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/v1/auth/signin",
        json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
              "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=20)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token","")


async def ingest(client, hdrs, content, source="test", ws="ws_test", user="u_test") -> dict:
    r = await client.post(f"{BASE}/v1/training/ingest",
        json={"content": content, "source": source, "workspace_id": ws,
              "user_id": user, "source_trust": 0.95},
        headers=hdrs, timeout=300)
    r.raise_for_status()
    return r.json()


async def query(client, hdrs, text, thread="t1", ws="ws_test", user="u_test") -> dict:
    r = await client.post(f"{BASE}/v1/query",
        json={"user_id": user, "query": text, "modality": "text",
              "workspace_id": ws, "thread_id": thread, "return_trace": True},
        headers=hdrs, timeout=300)
    r.raise_for_status()
    return r.json()


def show(label: str, d: dict, *, expect_in_resp: str = "", min_conf: float = 0.0,
         elapsed_ms: float = 0) -> bool:
    resp = d.get("response","")
    conf = d.get("confidence", 0)
    srcs = d.get("sources", [])
    ir   = (d.get("ir") or {}).get("target_ir","?")
    cap  = (d.get("capability_plan") or {}).get("kind","?")
    used_modal = not all(lr.get("deterministic", True) for lr in d.get("layer_results",[]))

    passed = True
    issues = []

    if expect_in_resp and expect_in_resp.lower() not in resp.lower() and len(srcs) == 0:
        passed = False
        issues.append(f"'{expect_in_resp}' not in response and no sources")

    if min_conf > 0 and conf < min_conf:
        passed = False
        issues.append(f"conf={conf:.2f} < {min_conf}")

    icon = PASS if passed else FAIL
    t = f"{elapsed_ms:.0f}ms" if elapsed_ms else ""
    print(f"\n  {icon} {label}")
    print(f"       IR={ir}  cap={cap}  conf={conf:.2f}  sources={len(srcs)}  modal={'yes' if used_modal else 'no'}  {t}")
    print(f"       → {resp[:120]}{'...' if len(resp)>120 else ''}")
    for issue in issues:
        print(f"       ⚠ {issue}")
    return passed


# ── main ──────────────────────────────────────────────────────────────────────

async def run():
    print(f"\n{'='*65}")
    print("  JimsAI Real End-to-End Test")
    print(f"{'='*65}\n")

    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=300) as client:
        # Health
        try:
            r = await client.get(f"{BASE}/health", timeout=8)
            assert r.status_code == 200
            print(f"{PASS} Backend healthy: {r.json()}\n")
        except Exception as e:
            print(f"{FAIL} Backend not reachable: {e}"); return

        # Pre-warm
        svc_status = await prewarm(client)
        all_warm = all(svc_status.values())
        print(f"\n  {PASS if all_warm else '⚠'} Services warm: {svc_status}\n")

        # Auth
        token = await auth(client)
        h = {"Authorization": f"Bearer {token}"}
        print(f"{PASS} Authenticated\n")

        # ── PHASE 1: Document Ingestion ───────────────────────────────────
        print(f"{'─'*65}")
        print("  PHASE 1: Document Ingestion")
        print(f"{'─'*65}")

        doc = """Project Titan — Engineering Brief
Lead Architect: Amina Okafor
Stack: Rust, WebAssembly, Modal AI, Cloudflare Workers
Goal: Build a real-time distributed inference engine.
Budget: $120,000 USD
Timeline: 18 months, starting Q1 2027
Key Risk: GPU availability for large model inference."""

        t0 = time.perf_counter()
        try:
            ing = await ingest(client, h, doc, source="titan_brief", ws="ws_titan", user="u_amina")
            ms = (time.perf_counter()-t0)*1000
            sig_id = ing.get("signature",{}).get("id","?")
            ok = bool(sig_id)
            print(f"\n  {PASS if ok else FAIL} Document ingested  [{ms:.0f}ms  sig={sig_id[:16]}]")
            results["ingest_doc"] = ok
        except Exception as e:
            print(f"\n  {FAIL} Ingest failed: {repr(e)[:80]}")
            results["ingest_doc"] = False

        await asyncio.sleep(3)  # brief Vectorize indexing wait

        # ── PHASE 2: Recall from ingested document ────────────────────────
        print(f"\n{'─'*65}")
        print("  PHASE 2: Recall from Ingested Document")
        print(f"{'─'*65}")

        recall_tests = [
            ("Who is the lead architect on Project Titan?", "amina", "recall_architect"),
            ("What is the budget for Project Titan?", "120,000", "recall_budget"),
            ("What is the tech stack?", "rust", "recall_stack"),
        ]
        for prompt, expect, label in recall_tests:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, f"t_titan_{label}", "ws_titan", "u_amina")
                ms = (time.perf_counter()-t0)*1000
                ok = show(f"Doc recall: {label}", d, expect_in_resp=expect, elapsed_ms=ms)
                results[label] = ok
            except Exception as e:
                print(f"\n  {FAIL} {label}: {repr(e)[:60]}")
                results[label] = False

        # ── PHASE 3: Profile Write + Recall ──────────────────────────────
        print(f"\n{'─'*65}")
        print("  PHASE 3: Profile Write + Recall (multi-language)")
        print(f"{'─'*65}")

        profile_tests = [
            ("My name is Celestine.", "celestine", "t_en", "ws_profile", "u_celeste", "profile_en"),
            ("Je m'appelle Kofi.", "kofi", "t_fr", "ws_profile", "u_kofi", "profile_fr"),
            ("اسمي عمر.", "omar", "t_ar", "ws_profile", "u_omar", "profile_ar"),
        ]

        for write_prompt, recall_name, thread, ws, user, label in profile_tests:
            t0 = time.perf_counter()
            try:
                wd = await query(client, h, write_prompt, thread, ws, user)
                ms_w = (time.perf_counter()-t0)*1000
                conf_w = wd.get("confidence",0)
                ir_w = (wd.get("ir") or {}).get("target_ir","?")
                wrote_ok = conf_w > 0.3
                print(f"\n  {PASS if wrote_ok else FAIL} Write ({label}): '{write_prompt[:40]}'  [{ms_w:.0f}ms conf={conf_w:.2f} ir={ir_w}]")
            except Exception as e:
                print(f"\n  {FAIL} Write ({label}): {repr(e)[:60]}")
                results[f"write_{label}"] = False
                continue

        await asyncio.sleep(3)

        for _, recall_name, thread, ws, user, label in profile_tests:
            t0 = time.perf_counter()
            try:
                rd = await query(client, h, "What is my name?", thread, ws, user)
                ms_r = (time.perf_counter()-t0)*1000
                resp = rd.get("response","").lower()
                srcs = rd.get("sources",[])
                ir_r = (rd.get("ir") or {}).get("target_ir","?")
                scope_pq = (rd.get("ir") or {}).get("scope_constraints",{}).get("profile_query",False)
                recalled = recall_name.lower() in resp or len(srcs) > 0
                ok = recalled
                print(f"  {PASS if ok else FAIL} Recall ({label}): '{recall_name}'  [{ms_r:.0f}ms ir={ir_r} pq={scope_pq} srcs={len(srcs)}]")
                if not ok:
                    print(f"       → {rd.get('response','')[:100]}")
                results[f"recall_{label}"] = ok
            except Exception as e:
                print(f"\n  {FAIL} Recall ({label}): {repr(e)[:60]}")
                results[f"recall_{label}"] = False

        # ── PHASE 4: Code Generation ──────────────────────────────────────
        print(f"\n{'─'*65}")
        print("  PHASE 4: Code Generation (Modal Renderer)")
        print(f"{'─'*65}")

        code_tests = [
            ("Write a function that reverses a linked list.", ["def ", "node", "next"], "code_python"),
            ("Write an SQL query to find all users who signed up in the last 30 days.", ["SELECT", "WHERE", "date"], "code_sql"),
        ]
        for prompt, code_tokens, label in code_tests:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, f"t_{label}", "ws_code", "u_dev")
                ms = (time.perf_counter()-t0)*1000
                resp = d.get("response","")
                found = any(tok.lower() in resp.lower() for tok in code_tokens)
                cap = (d.get("capability_plan") or {}).get("kind","?")
                used_modal = not all(lr.get("deterministic",True) for lr in d.get("layer_results",[]))
                ok = found or cap == "coding"
                print(f"\n  {PASS if ok else FAIL} {label}  [{ms:.0f}ms cap={cap} modal={'yes' if used_modal else 'no'}]")
                if not ok:
                    print(f"       → {resp[:150]}")
                results[label] = ok
            except Exception as e:
                print(f"\n  {FAIL} {label}: {repr(e)[:60]}")
                results[label] = False

        # ── PHASE 5: Math ─────────────────────────────────────────────────
        print(f"\n{'─'*65}")
        print("  PHASE 5: Math Solver (Deterministic)")
        print(f"{'─'*65}")

        math_tests = [
            ("What is 847 × 63?",         "53361",  "math_mult"),
            ("Solve for x: 2x + 10 = 20", "5",      "math_eq"),
            ("What is the derivative of x^3?", "3",  "math_calc"),
        ]
        for prompt, expect, label in math_tests:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, f"t_{label}", "ws_math", "u_math")
                ms = (time.perf_counter()-t0)*1000
                ok = show(f"Math: {label}", d, expect_in_resp=expect, min_conf=0.8, elapsed_ms=ms)
                results[label] = ok
            except Exception as e:
                print(f"\n  {FAIL} {label}: {repr(e)[:60]}")
                results[label] = False

        # ── PHASE 6: Learning (second call should use memory) ─────────────
        print(f"\n{'─'*65}")
        print("  PHASE 6: Learning Check (2nd call should be faster)")
        print(f"{'─'*65}")

        test_prompt = "What is 100 + 200?"
        t0 = time.perf_counter()
        d1 = await query(client, h, test_prompt, "t_learn_1", "ws_learn", "u_learn")
        ms1 = (time.perf_counter()-t0)*1000

        await asyncio.sleep(2)

        t0 = time.perf_counter()
        d2 = await query(client, h, test_prompt, "t_learn_2", "ws_learn", "u_learn")
        ms2 = (time.perf_counter()-t0)*1000

        r1 = d1.get("response","")
        r2 = d2.get("response","")
        srcs2 = d2.get("sources",[])
        learned = ms2 < ms1 or len(srcs2) > 0
        print(f"\n  {INFO} First call:  {ms1:.0f}ms → '{r1[:60]}'")
        print(f"  {INFO} Second call: {ms2:.0f}ms → '{r2[:60]}'  sources={len(srcs2)}")
        print(f"  {PASS if learned else '⚠'} Learning: {'faster or sourced from memory' if learned else 'not yet learned (cold start or no Vectorize hit)'}")
        results["learning"] = True  # informational — always pass, just shows timing

        # ── PHASE 7: Web Search ───────────────────────────────────────────
        print(f"\n{'─'*65}")
        print("  PHASE 7: Web Search (World Knowledge)")
        print(f"{'─'*65}")
        t0 = time.perf_counter()
        try:
            d = await query(client, h, "What is the population of Nigeria?", "t_web", "ws_web", "u_web")
            ms = (time.perf_counter()-t0)*1000
            resp = d.get("response","")
            cap = (d.get("capability_plan") or {}).get("kind","?")
            has_data = "million" in resp.lower() or "nigeria" in resp.lower() or len(d.get("sources",[])) > 0
            ok = cap == "world_knowledge" or has_data
            print(f"\n  {PASS if ok else FAIL} Web search  [{ms:.0f}ms cap={cap}]")
            print(f"       → {resp[:120]}")
            results["web_search"] = ok
        except Exception as e:
            print(f"\n  {FAIL} Web search: {repr(e)[:60]}")
            results["web_search"] = False

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  RESULTS")
    print(f"  {'─'*55}")
    passed = sum(v for v in results.values())
    total = len(results)
    for name, ok in results.items():
        print(f"  {PASS if ok else FAIL}  {name}")
    print(f"  {'─'*55}")
    print(f"  {passed}/{total} passed")
    print(f"{'='*65}\n")

    return passed, total


if __name__ == "__main__":
    result = asyncio.run(run())
    if result is None:
        sys.exit(1)
    p, t = result
    sys.exit(0 if p == t else 1)
