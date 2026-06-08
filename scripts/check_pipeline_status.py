"""Hit the backend's /v1/memory/stats which triggers pipeline hydration and shows state."""
import httpx, os
from dotenv import load_dotenv; load_dotenv()

r_auth = httpx.post("http://127.0.0.1:8000/v1/auth/signin",
    json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
          "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=15)
token = r_auth.json().get("access_token") or r_auth.json().get("token","")
headers = {"Authorization": f"Bearer {token}"}

# memory stats
r = httpx.get("http://127.0.0.1:8000/v1/memory/stats", headers=headers, timeout=10)
print("Memory stats:", r.json())

# Send a simple query and check the layer_results for hydration info
r2 = httpx.post("http://127.0.0.1:8000/v1/query",
    json={"user_id": "test_user", "query": "What is my name?", "modality": "text",
          "workspace_id": "test_ws", "thread_id": "diag_001", "return_trace": True},
    headers=headers, timeout=60)
data = r2.json()
print("\nResponse:", data.get("response","")[:100])
print("Sources:", data.get("sources",[]))
print("Confidence:", data.get("confidence"))

print("\nLayer results:")
for lr in data.get("layer_results", []):
    ldata = lr.get("data", {})
    hydrated = ldata.get("hydrated", ldata.get("hydrated_count", "?"))
    vec_avail = ldata.get("vectorize_available", "?")
    sb_avail = ldata.get("supabase_available", "?")
    layer = lr.get("layer","")
    activated = lr.get("activated", False)
    if "hydrat" in layer.lower() or "retriev" in layer.lower() or activated:
        print(f"  {layer}: activated={activated}  hydrated={hydrated}  vectorize={vec_avail}  supabase={sb_avail}")
