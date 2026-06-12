"""Measure actual latency of individual embed calls vs batch."""
import httpx, os, time
from dotenv import load_dotenv; load_dotenv()

url = os.getenv("JIMS_EMBEDDING_SERVICE_URL","").rstrip("/") + "/embed"
tok = os.getenv("JIMS_MODAL_API_KEY","")
hdrs = {"Authorization": f"Bearer {tok}"}

texts = ["My name is Celestine.", "What is my name?", "derivative of x^3"]

print("Single-text embed calls:")
for text in texts:
    t0 = time.perf_counter()
    r = httpx.post(url, json={"texts": [text], "model": "multilingual-e5-small", "purpose": "query"},
                   headers=hdrs, timeout=30)
    ms = (time.perf_counter()-t0)*1000
    dim = len(r.json().get("vectors",[["??"]])[0]) if r.status_code==200 else "ERR"
    print(f"  {ms:6.0f}ms  dim={dim}  '{text[:40]}'")

print("\nBatch embed (10 texts at once):")
batch = [f"text {i} about topic {i}" for i in range(10)]
t0 = time.perf_counter()
r = httpx.post(url, json={"texts": batch, "model": "multilingual-e5-small", "purpose": "document"},
               headers=hdrs, timeout=30)
ms = (time.perf_counter()-t0)*1000
dims = [len(v) for v in r.json().get("vectors",[])] if r.status_code==200 else []
print(f"  {ms:6.0f}ms  {len(dims)} vectors  dims={set(dims)}")
