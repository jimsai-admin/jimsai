import httpx, os
from dotenv import load_dotenv; load_dotenv()
auth = httpx.post("http://127.0.0.1:8000/v1/auth/signin",
    json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
          "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=15)
token = auth.json().get("access_token") or auth.json().get("token","")
h = {"Authorization": f"Bearer {token}"}
r = httpx.get("http://127.0.0.1:8000/v1/memory/stats", headers=h, timeout=10)
print("Memory stats:", r.json())
