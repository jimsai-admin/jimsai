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
    print(f"Query embedding non-zero: {sum(1 for v in query_emb if v != 0.0)}")
    
    # Get all prototype embeddings
    prototypes = classifier._get_prototype_embeddings()
    print("\nPrototype similarities:")
    for intent, proto_emb in sorted(prototypes.items(), key=lambda x: -cosine_similarity(query_emb, x[1])):
        sim = cosine_similarity(query_emb, proto_emb)
        print(f"  {intent}: {sim:.4f}")
    
    # Check prototype texts
    print("\nPrototype texts:")
    for intent, text in classifier.ir_prototypes.items():
        print(f"  {intent}: {text[:100]}...")

asyncio.run(test())