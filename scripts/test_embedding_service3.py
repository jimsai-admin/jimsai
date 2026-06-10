import os
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

import httpx
import asyncio
import math

async def test():
    url = os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").rstrip("/")
    token = os.getenv("JIMS_MODAL_API_KEY", "")
    
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    # Test with different prefixes and purposes
    tests = [
        ("passage: fetch retrieve download", "document"),
        ("query: fetch retrieve download", "query"),
        ("passage: zzzz qqqq unknown random", "document"),
        ("query: zzzz qqqq unknown random", "query"),
        ("My name is Celestine.", "query"),
        ("passage: My name is Celestine.", "document"),
    ]
    
    async with httpx.AsyncClient(timeout=120) as client:
        embeddings = {}
        for text, purpose in tests:
            r = await client.post(
                f"{url}/embed",
                headers=headers,
                json={"texts": [text], "model": "multilingual-e5-small", "purpose": purpose}
            )
            data = r.json()
            vectors = data.get("vectors")
            if vectors:
                emb = vectors[0]
                embeddings[f"{purpose}:{text[:30]}"] = emb
                non_zero = sum(1 for v in emb if v != 0.0)
                norm = math.sqrt(sum(v*v for v in emb))
                print(f"{purpose}: '{text[:40]}' -> norm={norm:.4f}, non_zero={non_zero}")
        
        # Compare all pairs
        def cosine_similarity(v1, v2):
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)
        
        print("\nAll pairwise similarities:")
        names = list(embeddings.keys())
        for i, name1 in enumerate(names):
            for name2 in names[i+1:]:
                sim = cosine_similarity(embeddings[name1], embeddings[name2])
                print(f"  {name1} <-> {name2}: {sim:.4f}")

asyncio.run(test())