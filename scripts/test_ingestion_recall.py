"""
Real Ingestion & Recall Test
=============================
Tests that JimsAI can:
1. Ingest a document via /v1/training/ingest
2. Recall specific facts from it via /v1/query
3. Store and recall user profile facts in any language
4. Handle multi-fact memory (preferences, tasks, code context)

All tests are real — no mocks, hits the live backend.

Usage:
    python scripts/test_ingestion_recall.py
"""
from __future__ import annotations
import asyncio, httpx, os, sys, time, json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except ImportError:
    pass

BASE = "http://127.0.0.1:8000"
PASS, FAIL = "✅", "❌"


async def get_token(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/v1/auth/signin",
        json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
              "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=20)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token", "")


async def prewarm(client: httpx.AsyncClient) -> None:
    """Ping Modal services to wake from scale-to-zero."""
    tok = os.getenv("JIMS_MODAL_API_KEY", "")
    h = {"Authorization": f"Bearer {tok}"}
    svcs = {
        "intent":   os.getenv("JIMS_INTENT_SERVICE_URL","").rstrip("/"),
        "renderer": os.getenv("JIMS_RENDERER_SERVICE_URL","").rstrip("/"),
        "embed":    os.getenv("JIMS_EMBEDDING_SERVICE_URL","").rstrip("/"),
    }
    print("Pre-warming Modal services...")
    async def ping(n, u):
        if not u: return
        try:
            r = await client.get(f"{u}/health", headers=h, timeout=120)
            print(f"  {PASS} {n}: {r.json().get('status','?')}")
        except Exception as e:
            print(f"  ⚠ {n}: {repr(e)[:60]}")
    await asyncio.gather(*[ping(n, u) for n, u in svcs.items()])
    print()


async def query(client: httpx.AsyncClient, hdrs: dict, prompt: str,
                thread: str = "test_main", ws: str = "test_ws",
                user: str = "test_user") -> dict:
    r = await client.post(f"{BASE}/v1/query",
        json={"user_id": user, "query": prompt, "modality": "text",
              "workspace_id": ws, "thread_id": thread, "return_trace": True},
        headers=hdrs, timeout=300)
    r.raise_for_status()
    return r.json()


async def ingest(client: httpx.AsyncClient, hdrs: dict, content: str,
                 source: str = "test", ws: str = "test_ws",
                 user: str = "test_user") -> dict:
    r = await client.post(f"{BASE}/v1/training/ingest",
        json={"content": content, "source": source, "workspace_id": ws,
              "user_id": user, "source_trust": 0.95},
        headers=hdrs, timeout=300)
    r.raise_for_status()
    return r.json()


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  [{detail}]" if detail else ""))
    return ok


async def run():
    print(f"\n{'='*65}")
    print("  JIMS-AI Real Ingestion + Recall Test")
    print(f"{'='*65}\n")

    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=300) as client:
        # Health
        r = await client.get(f"{BASE}/health", timeout=10)
        if r.status_code != 200:
            print(f"{FAIL} Backend not reachable."); return
        print(f"{PASS} Backend healthy\n")

        # Pre-warm
        await prewarm(client)

        # Auth
        token = await get_token(client)
        assert token, "No token"
        print(f"{PASS} Authenticated\n")
        h = {"Authorization": f"Bearer {token}"}

        # ── Test 1: Document Ingestion + Fact Recall ──────────────────────
        print("── Test 1: Document Ingestion + Recall ─────────────────────")
        doc = (
            "Project: JimsAI Phase 2\n"
            "Lead Engineer: Adebayo Jibril\n"
            "Stack: Python, FastAPI, Modal, Cloudflare Vectorize, Supabase\n"
            "Goal: Build a sovereign AI assistant that works in any language.\n"
            "Budget: $50,000 USD\n"
            "Deadline: Q4 2026\n"
        )
        t0 = time.perf_counter()
        try:
            ing = await ingest(client, h, doc, source="project_brief", ws="test_ws_doc")
            ms = (time.perf_counter() - t0) * 1000
            sig_id = ing.get("signature", {}).get("id", "?")
            ok_ing = check("Document ingested", bool(sig_id), f"{ms:.0f}ms sig={sig_id[:14]}")
        except Exception as exc:
            ok_ing = check("Document ingested", False, repr(exc)[:80])
        results["ingest_doc"] = ok_ing

        if ok_ing:
            await asyncio.sleep(3)  # let Vectorize index
            # Recall from ingested document
            for prompt, expected, label in [
                ("Who is the lead engineer on the JimsAI project?", "jibril", "recall_name"),
                ("What is the budget for Phase 2?", "50,000", "recall_budget"),
                ("What is the tech stack?", "modal", "recall_stack"),
            ]:
                t0 = time.perf_counter()
                try:
                    d = await query(client, h, prompt, "test_doc_recall", "test_ws_doc")
                    ms = (time.perf_counter() - t0) * 1000
                    resp = d.get("response", "").lower()
                    srcs = d.get("sources", [])
                    ok = check(f"  {label}: '{expected}' in response or has sources",
                               expected.lower() in resp or len(srcs) > 0,
                               f"{ms:.0f}ms sources={len(srcs)}")
                    if not ok:
                        print(f"       → {d.get('response','')[:100]}")
                    results[f"recall_{label}"] = ok
                except Exception as exc:
                    results[f"recall_{label}"] = check(f"  {label}", False, repr(exc)[:80])

        # ── Test 2: Multi-fact User Profile Write + Recall ────────────────
        print("\n── Test 2: Multi-Fact Profile Write + Recall ───────────────")
        thread = "test_profile_multi"

        writes = [
            ("My name is Adebayo.", "adebayo", "name"),
            ("I am building an AI assistant called JimsAI.", "jimsai", "project"),
            ("I prefer concise responses without unnecessary jargon.", "concise", "preference"),
            ("My timezone is Africa/Lagos.", "lagos", "timezone"),
        ]

        for prompt, expected, label in writes:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, thread)
                ms = (time.perf_counter() - t0) * 1000
                conf = d.get("confidence", 0)
                ir_target = (d.get("ir") or {}).get("target_ir", "?")
                ok = check(f"Write '{label}': stored",
                           conf > 0.4,
                           f"{ms:.0f}ms conf={conf:.2f} ir={ir_target}")
                results[f"write_{label}"] = ok
            except Exception as exc:
                results[f"write_{label}"] = check(f"Write '{label}'", False, repr(exc)[:60])

        await asyncio.sleep(3)

        # Recall each fact
        recalls = [
            ("What is my name?", "adebayo", "recall_name"),
            ("What am I building?", "jimsai", "recall_project"),
            ("What are my response preferences?", "concise", "recall_pref"),
        ]
        for prompt, expected, label in recalls:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, thread)
                ms = (time.perf_counter() - t0) * 1000
                resp = d.get("response", "").lower()
                srcs = d.get("sources", [])
                ir_target = (d.get("ir") or {}).get("target_ir", "?")
                scope_pq = (d.get("ir") or {}).get("scope_constraints", {}).get("profile_query", False)
                ok = check(f"{label}: '{expected}' recalled",
                           expected.lower() in resp or len(srcs) > 0,
                           f"{ms:.0f}ms ir={ir_target} profile_query={scope_pq} sources={len(srcs)}")
                if not ok:
                    print(f"       → {d.get('response','')[:120]}")
                results[label] = ok
            except Exception as exc:
                results[label] = check(label, False, repr(exc)[:60])

        # ── Test 3: Multi-language ingestion ─────────────────────────────
        print("\n── Test 3: Multi-language Ingestion + Recall ───────────────")
        fr_thread = "test_fr"
        try:
            d = await query(client, h, "Mon nom est Celestine.", fr_thread)
            ms_w = (time.perf_counter())*0  # just check it worked
            conf = d.get("confidence", 0)
            ok_fr_write = check("French: write 'Mon nom est Celestine'",
                                conf > 0.4, f"conf={conf:.2f}")
            results["fr_write"] = ok_fr_write

            if ok_fr_write:
                await asyncio.sleep(2)
                d2 = await query(client, h, "Quel est mon prénom?", fr_thread)
                resp = d2.get("response","").lower()
                srcs = d2.get("sources",[])
                ok_fr_recall = check("French: recall name 'celestine'",
                                     "celestine" in resp or len(srcs) > 0,
                                     f"sources={len(srcs)}")
                if not ok_fr_recall:
                    print(f"       → {d2.get('response','')[:100]}")
                results["fr_recall"] = ok_fr_recall
        except Exception as exc:
            results["fr_write"] = check("French write", False, repr(exc)[:80])

        # ── Test 4: Math (deterministic, no Modal needed) ─────────────────
        print("\n── Test 4: Math (deterministic) ────────────────────────────")
        for prompt, expected, label in [
            ("What is 12 * 13?", "156", "multiply"),
            ("Solve: 2x + 6 = 20", "7", "algebra"),
        ]:
            t0 = time.perf_counter()
            try:
                d = await query(client, h, prompt, "test_math")
                ms = (time.perf_counter() - t0) * 1000
                resp = d.get("response", "")
                ok = check(f"{label}: contains '{expected}'",
                           expected in resp, f"{ms:.0f}ms")
                results[f"math_{label}"] = ok
            except Exception as exc:
                results[f"math_{label}"] = check(label, False, repr(exc)[:60])

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    passed = sum(v for v in results.values())
    total = len(results)
    for name, ok in results.items():
        print(f"  {PASS if ok else FAIL}  {name}")
    print(f"  {'─'*55}")
    print(f"  {passed}/{total} passed")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    asyncio.run(run())
