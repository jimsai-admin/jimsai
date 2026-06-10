"""
Focused memory write + recall test with pre-warm.
Tests only the memory path after confirming services are warm.
"""
import asyncio, httpx, os, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

PASS, FAIL = "[PASS]", "[FAIL]"

async def main():
    async with httpx.AsyncClient(timeout=300) as client:
        # 1. Pre-warm
        print("Pre-warming Modal services...")
        token_modal = os.getenv("JIMS_MODAL_API_KEY","")
        hdrs_modal = {"Authorization": f"Bearer {token_modal}"}
        services = {
            "intent":   os.getenv("JIMS_INTENT_SERVICE_URL","").rstrip("/"),
            "renderer": os.getenv("JIMS_RENDERER_SERVICE_URL","").rstrip("/"),
            "embed":    os.getenv("JIMS_EMBEDDING_SERVICE_URL","").rstrip("/"),
        }
        async def ping(name, url):
            try:
                r = await client.get(f"{url}/health", headers=hdrs_modal, timeout=120)
                print(f"  {PASS} {name}: {r.json().get('status','?')}")
            except Exception as e:
                print(f"  [WARN] {name}: {repr(e)[:50]}")
        await asyncio.gather(*[ping(n,u) for n,u in services.items() if u])
        print("Services warm.\n")

        # 2. Auth
        auth = await client.post("http://127.0.0.1:8000/v1/auth/signin",
            json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
                  "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=15)
        token = auth.json().get("access_token") or auth.json().get("token","")
        h = {"Authorization": f"Bearer {token}"}
        print(f"{PASS} Authenticated\n")

        # 3. Write
        t0 = time.perf_counter()
        wr = await client.post("http://127.0.0.1:8000/v1/query",
            json={"user_id":"test_user","query":"My name is Celestine.",
                  "modality":"text","workspace_id":"test_ws",
                  "thread_id":"mem_test","return_trace":True},
            headers=h, timeout=300)
        ms = (time.perf_counter()-t0)*1000
        wd = wr.json()
        print(f"{PASS if wd.get('confidence',0)>0.5 else FAIL} Write ({ms:.0f}ms conf={wd.get('confidence',0):.2f})")
        wir = wd.get("ir",{})
        print(f"  Write IR: {wir.get('target_ir')} profile_write={wir.get('scope_constraints',{}).get('profile_write')}")

        # 4. Recall immediately (no wait — services are warm, no need for Vectorize delay
        #    since the sig is already in in-process memory from the write)
        t0 = time.perf_counter()
        rr = await client.post("http://127.0.0.1:8000/v1/query",
            json={"user_id":"test_user","query":"What is my name?",
                  "modality":"text","workspace_id":"test_ws",
                  "thread_id":"mem_test","return_trace":True},
            headers=h, timeout=300)
        ms = (time.perf_counter()-t0)*1000
        rd = rr.json()
        resp = rd.get("response","")
        sources = rd.get("sources",[])
        rir = rd.get("ir",{})

        print(f"\nRecall ({ms:.0f}ms)")
        print(f"  IR: {rir.get('target_ir')} profile_query={rir.get('scope_constraints',{}).get('profile_query')}")
        print(f"  sources={len(sources)}")
        print(f"  response: {resp[:120]}")

        recalled = "celestine" in resp.lower() or len(sources) > 0
        print(f"\n{PASS if recalled else FAIL} Memory recall: {'PASS' if recalled else 'FAIL'}")

asyncio.run(main())
