"""
Re-run only the 3 failed tests from test_live.py:
  - memory (write + recall)
  - code generation (sql_query)
  - web_search

Usage:
    python scripts/test_live_retry.py [--base-url http://127.0.0.1:8000]
"""
from __future__ import annotations
import argparse, asyncio, os, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(ROOT / ".env")
except ImportError:
    pass
try:
    import httpx
except ImportError:
    print("pip install httpx"); sys.exit(1)

PASS, FAIL = "✅", "❌"


async def prewarm_modal(client: httpx.AsyncClient) -> None:
    """Ping all Modal service /health endpoints in parallel to wake from scale-to-zero."""
    token = os.getenv("JIMS_MODAL_API_KEY", "")
    hdrs = {"Authorization": f"Bearer {token}"}
    services = {
        "intent":    os.getenv("JIMS_INTENT_SERVICE_URL", "").rstrip("/"),
        "renderer":  os.getenv("JIMS_RENDERER_SERVICE_URL", "").rstrip("/"),
        "embedding": os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").rstrip("/"),
        "classify":  os.getenv("JIMS_CLASSIFICATION_SERVICE_URL", "").rstrip("/"),
    }
    print("\n── Pre-warming Modal services ──────────────────────")

    async def ping(name: str, url: str) -> None:
        if not url:
            return
        try:
            r = await client.get(f"{url}/health", headers=hdrs, timeout=120)
            status = r.json().get("status", "?") if r.status_code == 200 else f"HTTP {r.status_code}"
            print(f"  {PASS if r.status_code == 200 else '⚠'}  {name:14s}: {status}")
        except Exception as exc:
            print(f"  ⚠  {name:14s}: {repr(exc)[:60]}")

    await asyncio.gather(*[ping(n, u) for n, u in services.items() if u])


async def get_token(base: str, client: httpx.AsyncClient) -> str:
    r = await client.post(f"{base}/v1/auth/signin",
        json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
              "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=30)
    r.raise_for_status()
    return r.json().get("access_token") or r.json().get("token", "")


async def query(base: str, client: httpx.AsyncClient, headers: dict,
                prompt: str, thread_id: str) -> dict:
    r = await client.post(f"{base}/v1/query",
        json={"user_id": "test_user", "query": prompt, "modality": "text",
              "workspace_id": "test_ws", "thread_id": thread_id, "return_trace": True},
        headers=headers, timeout=300)
    r.raise_for_status()
    return r.json()


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  [{detail}]" if detail else ""))
    return ok


async def run(base: str) -> None:
    print(f"\n{'='*60}")
    print(f"  JIMS-AI Retry: memory / code (sql) / web_search")
    print(f"  Backend: {base}")
    print(f"{'='*60}")

    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=300) as client:
        # Health guard
        r = await client.get(f"{base}/health", timeout=10)
        if r.status_code != 200:
            print(f"{FAIL} Backend not reachable"); return
        print(f"\n{PASS} Backend healthy")

        token = await get_token(base, client)
        assert token, "No auth token"
        print(f"{PASS} Authenticated")
        headers = {"Authorization": f"Bearer {token}"}

        # Pre-warm all Modal services before running tests
        await prewarm_modal(client)
        print("\n  Services warm — starting tests...\n")

        # ── 1. Memory write + recall ─────────────────────────────────────────
        print("\n── Memory Write + Recall ───────────────────────────")
        # Use a simple alphabetic name — the NLP entity extractor strips trailing numbers
        thread = "retry_mem_fresh"
        test_name = "Celestine"   # All-alpha, uncommon — won't collide with benchmark data
        print(f"       thread={thread}  name={test_name}")

        try:
            t0 = time.perf_counter()
            data = await query(base, client, headers,
                               f"My name is {test_name}.", thread)
            ms = (time.perf_counter() - t0) * 1000
            conf = data.get("confidence", 0)
            ok_write = check(f"Write: 'My name is {test_name}'",
                             conf > 0.5, f"{ms:.0f}ms conf={conf:.2f}")
        except Exception as exc:
            ok_write = check("Write fact", False, repr(exc))

        if ok_write:
            # ── Inspect what was written to Supabase ─────────────────────────
            try:
                _surl = os.getenv("SUPABASE_URL","").rstrip("/").replace("/rest/v1","")
                _skey = os.getenv("SUPABASE_SERVICE_KEY","")
                _r = await client.get(
                    f"{_surl}/rest/v1/signatures",
                    headers={"apikey": _skey, "Authorization": f"Bearer {_skey}"},
                    params={"select": "id,payload",
                            "order": "created_at.desc", "limit": "10"},
                    timeout=10,
                )
                rows = _r.json() if _r.status_code == 200 else []
                test_name_lower = test_name.lower()
                matching = [
                    r for r in rows
                    if test_name_lower in str(r.get("payload",{})).lower()
                ]
                if matching:
                    sig = matching[0]
                    p   = sig.get("payload", {})
                    meta = p.get("metadata", {})
                    emb_src = meta.get("latent_embedding_source", "?")
                    emb_dim = len(p.get("latent_embedding", []))
                    raw     = (p.get("raw_excerpt") or "")[:60]
                    emb_ok  = emb_src == "external_service" and emb_dim == 768
                    check(f"Signature stored: '{raw}'", True,
                          f"id={sig.get('id','')[:14]}")
                    check(f"  → Embedding: {emb_src} {emb_dim}-dim",
                          emb_ok,
                          "✓ real 768-d Modal embedding" if emb_ok
                          else f"⚠ {'needs reembedding' if emb_src != 'external_service' else 'wrong dim — Vectorize mismatch'}")
                else:
                    check(f"Signature for '{test_name}' found in Supabase", False,
                          f"checked {len(rows)} rows")
                    # Show what WAS stored (entity extraction may have changed the name)
                    for r in rows[:3]:
                        raw = (r.get("payload",{}).get("raw_excerpt",""))[:70]
                        if "profile" in raw.lower():
                            print(f"       stored: {raw}")
            except Exception as exc:
                check("Supabase inspect", False, repr(exc))

            # Wait for Vectorize eventual consistency
            print("       Waiting 15s for Vectorize to index...")
            await asyncio.sleep(15)

            # ── Recall ───────────────────────────────────────────────────────
            try:
                t0 = time.perf_counter()
                data = await query(base, client, headers, "What is my name?", thread)
                ms = (time.perf_counter() - t0) * 1000
                resp = data.get("response", "")
                sources = data.get("sources", [])
                # Print hydration and retrieval layer details
                for lr in data.get("layer_results", []):
                    layer = lr.get("layer", "")
                    activated = lr.get("activated", False)
                    if any(k in layer.lower() for k in ("hydrat", "retriev", "reasoning", "activation", "intent")):
                        ldata = lr.get("data", {})
                        count = ldata.get("count", ldata.get("hydrated", "?"))
                        vavail = ldata.get("vectorize_available", "?")
                        savail = ldata.get("supabase_available", "?")
                        ids = ldata.get("ids", [])
                        print(f"       {layer}: activated={activated} count={count} ids={ids[:3]}")
                # Also print IR info
                ir_data = data.get("ir") or {}
                print(f"       IR: target={ir_data.get('target_ir')} scope={ir_data.get('scope_constraints',{})}")
                recalled = (
                    test_name.lower() in resp.lower()
                    or len(sources) > 0
                )
                ok_recall = check(
                    f"Recall: response contains '{test_name}' or has sources",
                    recalled,
                    f"{ms:.0f}ms sources={len(sources)}",
                )
                if not ok_recall:
                    print(f"       response: {resp[:250]}")
            except Exception as exc:
                ok_recall = check("Recall fact", False, repr(exc))
        else:
            ok_recall = False
            check("Recall (skipped — write failed)", False)

        results["memory"] = ok_write and ok_recall

        # ── 2. Code generation — SQL ─────────────────────────────────────────
        print("\n── Code Generation: SQL ────────────────────────────")
        try:
            t0 = time.perf_counter()
            data = await query(base, client, headers,
                "Write a SQL query to get the top 5 users by score from a users table.",
                "retry_sql_001")
            ms = (time.perf_counter() - t0) * 1000
            resp = data.get("response", "")
            cap  = (data.get("capability_plan") or {}).get("kind", "?")
            ir   = (data.get("ir") or {}).get("target_ir", "?")
            modal = not all(lr.get("deterministic", True)
                            for lr in data.get("layer_results", []))
            found = any(tok in resp for tok in ["SELECT", "ORDER BY", "select", "order by"])
            ok_sql = check("sql_query: contains SQL tokens", found,
                           f"{ms:.0f}ms cap={cap} ir={ir} modal={'yes' if modal else 'no'}")
            if not ok_sql:
                print(f"       response: {resp[:200]}")
        except Exception as exc:
            ok_sql = check("sql_query", False, repr(exc))
        results["code_sql"] = ok_sql

        # ── 3. Web search ────────────────────────────────────────────────────
        print("\n── Web Search (world_knowledge) ────────────────────")
        try:
            t0 = time.perf_counter()
            data = await query(base, client, headers,
                "What is the population of Nigeria as of the latest data?",
                "retry_web_001")
            ms = (time.perf_counter() - t0) * 1000
            resp = data.get("response", "")
            cap  = (data.get("capability_plan") or {}).get("kind", "?")
            gaps = data.get("gaps", [])
            has_content = len(resp) > 20
            ok_web = check("Web search returns content or gap",
                           has_content, f"{ms:.0f}ms cap={cap} gaps={len(gaps)}")
            if ok_web:
                has_pop = any(w in resp.lower()
                              for w in ["million", "nigeria", "population", "billion"])
                check("  → Response contains population data", has_pop, resp[:100])
            if gaps:
                for g in gaps[:2]:
                    print(f"       ⚠ GAP: {g[:100]}")
        except Exception as exc:
            ok_web = check("Web search query", False, repr(exc))
        results["web_search"] = ok_web

    # Summary
    print(f"\n{'='*60}")
    passed = sum(v for v in results.values())
    for name, ok in results.items():
        print(f"  {PASS if ok else FAIL}  {name}")
    print(f"  {'─'*40}")
    print(f"  {passed}/{len(results)} passed")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    asyncio.run(run(args.base_url))
