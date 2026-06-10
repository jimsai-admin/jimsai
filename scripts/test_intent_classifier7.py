import os
os.environ["JIMS_INTENT_EMBEDDING_TIMEOUT"] = "60"

from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio
import math

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    def cosine_similarity(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
    
    # Get query embedding
    query = "My name is Celestine."
    query_emb = classifier._fetch_embedding("query: " + query)
    print(f"Query norm: {math.sqrt(sum(v*v for v in query_emb)):.4f}")
    
    # Get all prototype embeddings and check norms
    prototypes = classifier._get_prototype_embeddings()
    print("\nPrototype norms:")
    for intent, proto_emb in prototypes.items():
        norm = math.sqrt(sum(v*v for v in proto_emb))
        non_zero = sum(1 for v in proto_emb if v != 0.0)
        print(f"  {intent}: norm={norm:.4f}, non_zero={non_zero}")
    
    # Check if prototypes are all similar to each other
    print("\nPrototype-to-prototype similarities:")
    intent_list = list(prototypes.keys())
    for i, intent1 in enumerate(intent_list):
        for intent2 in intent_list[i+1:]:
            sim = cosine_similarity(prototypes[intent1], prototypes[intent2])
            if sim > 0.5:
                print(f"  {intent1} <-> {intent2}: {sim:.4f}")

asyncio.run(test())