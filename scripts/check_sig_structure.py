"""Check the full structured content of the Celestine signature."""
import httpx, os, json
from dotenv import load_dotenv; load_dotenv()

surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")
r = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey":skey,"Authorization":f"Bearer {skey}"},
    params={"select":"id,payload","order":"created_at.desc","limit":"10"}, timeout=10)

rows = r.json()
celestine = next((row for row in rows if "celestine" in str(row.get("payload",{})).lower()), None)

if not celestine:
    print("Celestine not found")
else:
    p = celestine["payload"]
    s = p.get("structured", {})
    print(f"id: {celestine['id']}")
    print(f"raw_excerpt: {p.get('raw_excerpt','')}")
    print(f"workspace_id: {p.get('workspace_id')}")
    print(f"user_id: {p.get('user_id')}")
    print(f"abstraction_tags: {p.get('abstraction_tags',[])}") 
    print(f"entities: {s.get('entities',[])}")
    print(f"relations: {s.get('relations',[])}")
    print(f"embedding_source: {p.get('metadata',{}).get('latent_embedding_source')}")
    dim = len(p.get('latent_embedding',[]))
    print(f"embedding dim: {dim}")
