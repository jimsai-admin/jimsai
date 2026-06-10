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
    
    # Test prototype texts
    prototypes = {
        "FETCH_DOCUMENT": "fetch retrieve download upload attach file document export save read open import load",
        "WORKSPACE_QUERY": "workspace database db affects changed impact query what happens if codebase relation dependency effect consequence causation",
        "OP_ESCAPE_TO_SANDBOX": "zzzz qqqq unknown random nonsense xxxx yyyy wwww vvvv",
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        embeddings = {}
        for name, text in prototypes.items():
            r = await client.post(
                f"{url}/embed",
                headers=headers,
                json={"texts": ["passage: " + text], "model": "multilingual-e5-small", "purpose": "document"}
            )
            data = r.json()
            vectors = data.get("vectors")
            if vectors:
                emb = vectors[0]
                embeddings[name] = emb
                non_zero = sum(1 for v in emb if v != 0.0)
                norm = math.sqrt(sum(v*v for v in emb))
                print(f"{name}: norm={norm:.4f}, non_zero={non_zero}")
                print(f"  First 10: {emb[:10]}")
        
        # Compare
        def cosine_similarity(v1, v2):
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot / (norm1 * norm2)
        
        print("\nSimilarities:")
        names = list(embeddings.keys())
        for i, name1 in enumerate(names):
            for name2 in names[i+1:]:
                sim = cosine_similarity(embeddings[name1], embeddings[name2])
                print(f"  {name1} <-> {name2}: {sim:.4f}")

asyncio.run(test())