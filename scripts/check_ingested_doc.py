"""Check if the ingested document signature has entities/relations."""
import httpx, os
from dotenv import load_dotenv; load_dotenv()

surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")
r = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey":skey,"Authorization":f"Bearer {skey}"},
    params={"select":"id,payload","order":"created_at.desc","limit":"10"}, timeout=10)
rows = r.json()

# Find recently ingested doc
for row in rows[:5]:
    p = row.get("payload",{})
    raw = p.get("raw_excerpt","")[:80]
    s = p.get("structured",{})
    entities = s.get("entities",[])
    relations = s.get("relations",[])
    ws = p.get("workspace_id")
    src = p.get("metadata",{}).get("latent_embedding_source","?")
    dim = len(p.get("latent_embedding",[]))
    print(f"id={row['id'][:16]}  ws={ws}  src={src}  dim={dim}")
    print(f"  raw: {raw}")
    print(f"  entities: {[e.get('name') for e in entities[:5]]}")
    print(f"  relations: {[(r.get('subject'),r.get('predicate'),r.get('object')) for r in relations[:3]]}")
    print()
