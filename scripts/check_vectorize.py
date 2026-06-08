"""Query Vectorize directly for the Celestine profile signature."""
import httpx, os, json
from dotenv import load_dotenv; load_dotenv()

# First get the signature embedding from Supabase
surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")
r = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
    params={"select": "id,payload", "order": "created_at.desc", "limit": "10"},
    timeout=10)
rows = r.json()

# Find Celestine
celestine = next((row for row in rows
    if "celestine" in str(row.get("payload",{})).lower()), None)

if not celestine:
    print("Celestine signature not found in Supabase!")
    print("Recent provenances:", [(r.get("payload",{}).get("provenance",""))[:40] for r in rows[:5]])
else:
    p = celestine.get("payload", {})
    sig_id = celestine.get("id","")
    emb = p.get("latent_embedding", [])
    meta = p.get("metadata", {})
    print(f"Found Celestine sig: {sig_id}")
    print(f"Embedding source: {meta.get('latent_embedding_source')}  dim={len(emb)}")
    print(f"workspace_id: {p.get('workspace_id')}  user_id: {p.get('user_id')}")

    if not emb:
        print("No embedding vector!")
    else:
        # Query Vectorize with this exact vector
        acct = os.getenv("CF_ACCOUNT_ID","")
        idx  = os.getenv("CF_VECTORIZE_INDEX","")
        tok  = os.getenv("CF_VECTORIZE_API_TOKEN") or os.getenv("CF_TOKEN","")
        url  = f"https://api.cloudflare.com/client/v4/accounts/{acct}/vectorize/v2/indexes/{idx}/query"
        resp = httpx.post(url,
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
            json={"vector": emb[:768], "topK": 5, "returnMetadata": "all"},
            timeout=15)
        data = resp.json()
        matches = (data.get("result") or {}).get("matches", [])
        print(f"\nVectorize query status: {resp.status_code}")
        print(f"Matches returned: {len(matches)}")
        for m in matches:
            print(f"  id={m.get('id','')[:16]}  score={m.get('score',0):.4f}  meta={m.get('metadata',{})}")

        # Also search by ID directly
        print(f"\nChecking if sig_id '{sig_id}' is in Vectorize matches...")
        found = any(m.get("id") == sig_id for m in matches)
        print(f"  Self-match (same vector): {'YES' if found else 'NO — Vectorize may not have indexed it yet'}")
