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
    
    # Check the API URL and token
    print(f"API URL: {classifier.api_url}")
    print(f"API Token: {classifier.api_token[:10]}...")
    
    # Test _fetch_embedding directly
    emb = classifier._fetch_embedding("query: My name is Celestine.")
    print(f"Embedding (first 10): {emb[:10]}")
    print(f"All zeros: {all(v == 0.0 for v in emb)}")
    
    # Now test classification
    intent, score = classifier.classify_intent("My name is Celestine.")
    is_profile = classifier.is_profile_query("My name is Celestine.")
    print(f"\nIntent: {intent}, Score: {score:.4f}, Is Profile: {is_profile}")

asyncio.run(test())