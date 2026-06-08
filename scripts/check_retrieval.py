"""Test retrieve_similar directly to diagnose why recall fails."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv()

import httpx, os

# Get the Celestine embedding from Supabase
surl = os.getenv("SUPABASE_URL","").replace("/rest/v1","").rstrip("/")
skey = os.getenv("SUPABASE_SERVICE_KEY","")
r = httpx.get(f"{surl}/rest/v1/signatures",
    headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
    params={"select": "id,payload", "order": "created_at.desc", "limit": "10"}, timeout=10)

celestine = next((row for row in r.json()
    if "celestine" in str(row.get("payload",{})).lower()), None)
if not celestine:
    print("Celestine not in Supabase"); sys.exit(1)

emb = celestine["payload"]["latent_embedding"]
print(f"Celestine embedding: {len(emb)}-dim")

# Now test retrieve_similar directly
from prototype.jimsai.provider_adapters import ProductionRuntime

prod = ProductionRuntime()
prod._ensure_initialized()

# Check adapter statuses
print("\nAdapter statuses:")
for name, status in prod.statuses.items():
    print(f"  {name:25s}: configured={status.configured} available={status.available}  {status.detail[:60]}")

# Try retrieve_similar
print("\nCalling retrieve_similar with Celestine's own embedding...")
results = prod.retrieve_similar(emb, limit=5, workspace_id="test_ws", user_id="test_user")
print(f"Results: {len(results)}")
for sig in results:
    raw = (sig.raw_excerpt or "")[:60]
    print(f"  {sig.id[:16]}  ws={sig.workspace_id}  {raw}")

# Try without workspace filter
print("\nWithout workspace filter...")
results2 = prod.retrieve_similar(emb, limit=5)
print(f"Results: {len(results2)}")
for sig in results2:
    raw = (sig.raw_excerpt or "")[:60]
    print(f"  {sig.id[:16]}  ws={sig.workspace_id}  user={sig.user_id}  {raw}")
