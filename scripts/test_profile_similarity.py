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
    
    # Load prototypes first
    classifier._get_prototype_embeddings()
    profile_emb = classifier._get_profile_embedding()
    
    print(f"Profile embedding dim: {len(profile_emb)}, non-zero: {sum(1 for v in profile_emb if v != 0.0)}")
    
    queries = [
        ("My name is Celestine.", "English"),
        ("Je m'appelle Pierre.", "French"),
        ("Me llamo María.", "Spanish"),
        ("Orúkọ mi ni Adé.", "Yoruba"),
        ("اسمي أحمد.", "Arabic"),
        ("我的名字是小明。", "Chinese"),
    ]
    
    for query, lang in queries:
        query_emb = classifier._fetch_embedding("query: " + query)
        sim = cosine_similarity(query_emb, profile_emb)
        print(f'{lang}: profile_sim={sim:.4f}, threshold=0.70, is_profile={sim > 0.70}')

asyncio.run(test())