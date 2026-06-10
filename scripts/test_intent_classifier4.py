import os
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    # Test _fetch_embedding directly
    emb = classifier._fetch_embedding("query: My name is Celestine.")
    print(f"Embedding length: {len(emb)}")
    print(f"Non-zero count: {sum(1 for v in emb if v != 0.0)}")
    print(f"First 20: {emb[:20]}")
    print(f"Last 20: {emb[-20:]}")
    
    # Test profile embedding
    profile_emb = classifier._get_profile_embedding()
    print(f"\nProfile embedding length: {len(profile_emb)}")
    print(f"Non-zero count: {sum(1 for v in profile_emb if v != 0.0)}")
    print(f"First 20: {profile_emb[:20]}")
    
    # Test cosine similarity manually
    import math
    def cosine_similarity(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
    
    sim = cosine_similarity(emb, profile_emb)
    print(f"\nCosine similarity with profile: {sim:.4f}")
    print(f"Threshold: 0.70")
    print(f"Is profile query: {sim > 0.70}")
    
    # Check all prototype embeddings
    print("\nPrototype similarities:")
    prototypes = classifier._get_prototype_embeddings()
    for intent, proto_emb in prototypes.items():
        sim = cosine_similarity(emb, proto_emb)
        print(f"  {intent}: {sim:.4f}")

asyncio.run(test())