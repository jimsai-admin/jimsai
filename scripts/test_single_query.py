"""Send a single test query and print the IR."""
import httpx, os, json
from dotenv import load_dotenv; load_dotenv()

auth = httpx.post("http://127.0.0.1:8000/v1/auth/signin",
    json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
          "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=15)
token = auth.json().get("access_token") or auth.json().get("token","")
headers = {"Authorization": f"Bearer {token}"}

r = httpx.post("http://127.0.0.1:8000/v1/query",
    json={"user_id": "test_user", "query": "What is my name?",
          "modality": "text", "workspace_id": "test_ws",
          "thread_id": "test_ir_001", "return_trace": True},
    headers=headers, timeout=60)

data = r.json()
ir = data.get("ir", {})
print("target_ir:", ir.get("target_ir"))
print("scope profile_query:", ir.get("scope_constraints",{}).get("profile_query"))
print("confidence:", ir.get("confidence"))
print("response:", data.get("response","")[:100])
print("sources:", data.get("sources",[]))
