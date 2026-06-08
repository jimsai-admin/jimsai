"""
Diagnose memory recall failure end-to-end:
1. Check supabase_postgres + vectorize statuses from the running pipeline
2. Test load_recent_signatures directly
3. Test lexical scoring for 'What is my name?' vs Celestine
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv()
import os, httpx

surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")

# 1. Check Supabase directly
print("── 1. Supabase direct REST ──────────────────────────")
r = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
    params={"select":"id,payload","order":"created_at.desc","limit":"20"}, timeout=10)
rows = r.json()
print(f"  Rows returned: {len(rows)}")
celestine_rows = [row for row in rows if "celestine" in str(row.get("payload",{})).lower()]
print(f"  Celestine rows: {len(celestine_rows)}")
for row in celestine_rows:
    p = row.get("payload",{})
    print(f"  id={row['id'][:16]}  ws={p.get('workspace_id')}  user={p.get('user_id')}  raw={p.get('raw_excerpt','')[:60]}")

# 2. Test lexical scoring
print("\n── 2. Lexical scoring simulation ────────────────────")
query = "What is my name?"
stop_terms = {"what", "how", "why", "the", "and", "for", "with", "about", "should"}
import re
terms = {t for t in re.findall(r"[\w\-.]+", query.lower()) if len(t) >= 3 and t not in stop_terms}
print(f"  Query terms for '{query}': {terms}")

for row in celestine_rows[:2]:
    p = row.get("payload",{})
    raw = (p.get("raw_excerpt") or "").lower()
    tags = " ".join(p.get("abstraction_tags") or []).lower()
    entities = " ".join(e.get("name","") for e in (p.get("structured") or {}).get("entities",[]) if isinstance(e, dict)).lower()
    relations = " ".join(f"{r.get('subject','')} {r.get('predicate','')} {r.get('object','')}"
                         for r in (p.get("structured") or {}).get("relations",[]) if isinstance(r, dict)).lower()
    haystack = f"{raw} {tags} {entities} {relations}"
    score = sum(1 for t in terms if t in haystack)
    print(f"  sig={row['id'][:16]}  score={score}  (threshold=1)")
    print(f"    raw: {raw[:80]}")
    print(f"    tags: {tags[:60]}")
    print(f"    entities: {entities[:60]}")
    for t in terms:
        print(f"    '{t}' in haystack: {t in haystack}")

# 3. Check Vectorize for these sigs
if celestine_rows:
    print("\n── 3. Vectorize index check ─────────────────────────")
    emb = celestine_rows[0]["payload"].get("latent_embedding",[])
    acct = os.getenv("CF_ACCOUNT_ID","")
    idx  = os.getenv("CF_VECTORIZE_INDEX","")
    tok  = os.getenv("CF_VECTORIZE_API_TOKEN") or os.getenv("CF_TOKEN","")
    vr = httpx.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/vectorize/v2/indexes/{idx}/query",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"vector": emb[:768], "topK": 5, "returnMetadata": "all"}, timeout=15)
    vdata = vr.json()
    matches = (vdata.get("result") or {}).get("matches",[])
    print(f"  Vectorize status: {vr.status_code}, matches: {len(matches)}")
    for m in matches[:5]:
        print(f"    score={m.get('score',0):.4f}  id={m.get('id','')[:16]}  ws={m.get('metadata',{}).get('workspace_id')}  user={m.get('metadata',{}).get('user_id')}")
