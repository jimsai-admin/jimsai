"""Quick health check for all Modal services."""
import httpx, os
from dotenv import load_dotenv
load_dotenv()

token = os.getenv("JIMS_MODAL_API_KEY", "")
services = [
    ("embedding",       os.getenv("JIMS_EMBEDDING_SERVICE_URL", "")),
    ("classification",  os.getenv("JIMS_CLASSIFICATION_SERVICE_URL", "")),
    ("intent",          os.getenv("JIMS_INTENT_SERVICE_URL", "")),
    ("renderer",        os.getenv("JIMS_RENDERER_SERVICE_URL", "")),
    ("reasoning",       os.getenv("JIMS_REASONING_SERVICE_URL", "")),
]
headers = {"Authorization": f"Bearer {token}"}
for name, url in services:
    base = url.rstrip("/")
    try:
        r = httpx.get(base + "/health", headers=headers, timeout=60)
        status = r.json().get("status", "?") if r.status_code == 200 else f"HTTP {r.status_code}"
        print(f"  {name:16s}: {r.status_code}  {status}")
    except Exception as exc:
        print(f"  {name:16s}: ERROR  {exc}")
