"""Check if the embedding classifier is using real embeddings or hash fallback."""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import _FallbackClassifier

clf = _FallbackClassifier()
print("api_url:", clf.api_url)
print("api_token set:", bool(clf.api_token))

# Get prototype embeddings
protos = clf._get_prototype_embeddings()
print(f"\nuse_hash_fallback: {clf._use_hash_fallback}")
print(f"prototype count: {len(protos)}")

if protos:
    dims = [len(v) for v in protos.values()]
    print(f"embedding dims: {set(dims)}")
    
    # Check pairwise similarities
    import math
    def cos(v1, v2):
        dot = sum(a*b for a,b in zip(v1,v2))
        n1 = math.sqrt(sum(a*a for a in v1)) or 1
        n2 = math.sqrt(sum(b*b for b in v2)) or 1
        return dot/(n1*n2)
    
    embs = list(protos.items())
    print("\nSample pairwise similarities:")
    for i in range(min(3, len(embs))):
        for j in range(i+1, min(4, len(embs))):
            n1, e1 = embs[i]
            n2, e2 = embs[j]
            sim = cos(e1, e2)
            print(f"  {n1[:20]:20s} vs {n2[:20]:20s}: {sim:.4f}")

# Test classification
test_queries = [
    "My name is Celestine.",
    "What is my name?",
    "What is the derivative of x^3?",
    "Je m'appelle Kofi.",
    "ما اسمي؟",
]
print("\nClassification test:")
for q in test_queries:
    ir, conf, is_mem = clf.classify_intent_with_memory_check(q)
    print(f"  '{q[:35]:35s}' → {ir:20s} conf={conf:.3f} memory={is_mem}")
