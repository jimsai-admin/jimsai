import os
os.environ["JIMS_INTENT_EMBEDDING_TIMEOUT"] = "60"
os.environ.pop('JIMS_CLASSIFICATION_SERVICE_URL', None)
os.environ.pop('JIMS_INTENT_SERVICE_URL', None)
os.environ.pop('JIMS_RENDERER_SERVICE_URL', None)
os.environ.pop('JIMS_REASONING_SERVICE_URL', None)

from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.semantic_compiler import SemanticCompilerRuntime
import asyncio

async def test():
    compiler = SemanticCompilerRuntime()
    classifier = compiler.classifier
    
    # Test the LLM path directly
    print(f"qwen_bridge: {classifier.qwen_bridge}")
    print(f"qwen_enabled: {classifier.qwen_bridge.qwen_enabled}")
    
    query = "My name is Celestine."
    result = await classifier.qwen_bridge.infer_intent(query, {"target_ir": "WORKSPACE_QUERY", "confidence": 0.3})
    print(f"LLM Result: {result}")
    
    # Now test the full classify_intent
    intent, score = classifier.classify_intent(query)
    print(f"Classify result: {intent}, {score}")

asyncio.run(test())