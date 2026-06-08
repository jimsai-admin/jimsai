"""Inspect recent Supabase signatures to check embedding source and content."""
import httpx, os, json
from dotenv import load_dotenv; load_dotenv()

url = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
key = os.getenv("SUPABASE_SERVICE_KEY","")
r = httpx.get(
    f"{url}/rest/v1/signatures",
    headers={"apikey": key, "Authorization": f"Bearer {key}"},
    params={"select": "id,payload", "order": "created_at.desc", "limit": "15"},
    timeout=10,
)
rows = r.json()
print(f"\nTotal rows returned: {len(rows)}\n")
print(f"{'ID':16s}  {'EMB_SRC':18s}  {'DIM':4s}  {'PROVENANCE':35s}  RAW_EXCERPT")
print("-"*110)
for row in rows:
    p = row.get("payload") or {}
    meta = p.get("metadata") or {}
    emb = p.get("latent_embedding") or []
    raw = (p.get("raw_excerpt") or "")[:50]
    prov = (p.get("provenance") or "")[:35]
    src = meta.get("latent_embedding_source", "?")
    sid = row.get("id","")[:16]
    print(f"{sid:16s}  {src:18s}  {len(emb):4d}  {prov:35s}  {raw}")
