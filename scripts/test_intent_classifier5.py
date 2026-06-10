import os
os.environ["JIMS_INTENT_EMBEDDING_TIMEOUT"] = "60"

from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    # Test classification (this will trigger quality check)
    intent, score = classifier.classify_intent("My name is Celestine.")
    is_profile = classifier.is_profile_query("My name is Celestine.")
    print(f"Intent: {intent}, Score: {score:.4f}, Is Profile: {is_profile}")
    
    # Test multilingual
    print("\n--- Multilingual ---")
    queries = [
        ("My name is Celestine.", "English"),
        ("Je m'appelle Pierre.", "French"),
        ("Me llamo María.", "Spanish"),
        ("Orúkọ mi ni Adé.", "Yoruba"),
        ("اسمي أحمد.", "Arabic"),
        ("我的名字是小明。", "Chinese"),
    ]
    
    for query, lang in queries:
        intent, score = classifier.classify_intent(query)
        is_profile = classifier.is_profile_query(query)
        print(f'{lang}: intent={intent}, score={score:.4f}, is_profile={is_profile}')

asyncio.run(test())