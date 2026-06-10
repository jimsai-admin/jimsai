import os
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

import httpx
import asyncio

async def test():
    url = os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").rstrip("/")
    token = os.getenv("JIMS_MODAL_API_KEY", "")
    
    print(f"URL: {url}")
    print(f"Token: {token[:10]}...")
    
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    # Test health
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(f"{url}/health", headers=headers)
            print(f"Health: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"Health check failed: {e}")
        
        # Test embed
        try:
            r = await client.post(
                f"{url}/embed",
                headers=headers,
                json={"texts": ["My name is Celestine."], "model": "multilingual-e5-small", "purpose": "query"}
            )
            print(f"Embed: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"Embed failed: {e}")

asyncio.run(test())