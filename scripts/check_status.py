"""Check production adapter statuses via the pipeline dashboard endpoint."""
import httpx, os, json
from dotenv import load_dotenv; load_dotenv()

# Auth
r = httpx.post("http://127.0.0.1:8000/v1/auth/signin",
    json={"email": os.getenv("JIMS_BENCHMARK_EMAIL"),
          "password": os.getenv("JIMS_BENCHMARK_PASSWORD")}, timeout=15)
token = r.json().get("access_token") or r.json().get("token","")
headers = {"Authorization": f"Bearer {token}"}

# Dashboard
r2 = httpx.get("http://127.0.0.1:8000/v1/training/dashboard",
    headers=headers, timeout=30)
data = r2.json()

prod = data.get("production_readiness", {})
print("\nAdapter statuses:")
for k, v in sorted(prod.items()):
    if "available" in k or "configured" in k or "detail" in k:
        print(f"  {k:40s}: {v}")

# Also directly test retrieve_similar via a manual Supabase + Vectorize call
print("\n\nDirect Vectorize test for Celestine signature:")
surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")
sr = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
    params={"select":"id,payload","order":"created_at.desc","limit":"10"}, timeout=10)
rows = sr.json()
celestine = next((r for r in rows if "celestine" in str(r.get("payload",{})).lower()), None)
if celestine:
    print(f"  Found in Supabase: {celestine['id'][:16]}  ws={celestine['payload'].get('workspace_id')}  user={celestine['payload'].get('user_id')}")
    emb = celestine["payload"].get("latent_embedding",[])
    
    # Simulate retrieve_similar with workspace_id=test_ws user_id=test_user
    acct = os.getenv("CF_ACCOUNT_ID","")
    idx = os.getenv("CF_VECTORIZE_INDEX","")
    tok = os.getenv("CF_VECTORIZE_API_TOKEN") or os.getenv("CF_TOKEN","")
    vr = httpx.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/vectorize/v2/indexes/{idx}/query",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"vector": emb[:768], "topK": 5, "returnMetadata": "all"}, timeout=15)
    matches = (vr.json().get("result") or {}).get("matches",[])
    print(f"  Vectorize self-query matches: {len(matches)}")
    for m in matches[:3]:
        print(f"    score={m.get('score',0):.4f}  id={m.get('id','')[:16]}  ws={m.get('metadata',{}).get('workspace_id')}")
else:
    print("  Celestine NOT found in Supabase")
    print("  Recent raw_excerpts:", [(r.get("payload",{}).get("raw_excerpt",""))[:50] for r in rows[:5]])
