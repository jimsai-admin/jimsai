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
    
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    async with httpx.AsyncClient(timeout=120) as client:
        # Test the same query as classifier
        query = "query: My name is Celestine."
        r = await client.post(
            f"{url}/embed",
            headers=headers,
            json={"texts": [query], "model": "multilingual-e5-small", "purpose": "query"}
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        print(f"Keys: {data.keys()}")
        print(f"Model: {data.get('model')}")
        print(f"Dimension: {data.get('dimension')}")
        print(f"Fallback: {data.get('fallback')}")
        vectors = data.get("vectors")
        if vectors:
            print(f"Vectors count: {len(vectors)}")
            if vectors[0]:
                print(f"First vector length: {len(vectors[0])}")
                non_zero = sum(1 for v in vectors[0] if v != 0.0)
                print(f"Non-zero count: {non_zero}")
                print(f"First 20: {vectors[0][:20]}")
                print(f"Last 20: {vectors[0][-20:]}")
        
        # Also test without "query:" prefix
        query2 = "My name is Celestine."
        r2 = await client.post(
            f"{url}/embed",
            headers=headers,
            json={"texts": [query2], "model": "multilingual-e5-small", "purpose": "query"}
        )
        data2 = r2.json()
        vectors2 = data2.get("vectors")
        if vectors2:
            print(f"\nWithout prefix - Non-zero count: {sum(1 for v in vectors2[0] if v != 0.0)}")
            print(f"First 20: {vectors2[0][:20]}")

asyncio.run(test())