import os
os.environ["JIMS_GENERATION_TIMEOUT"] = "180"
os.environ["JIMS_LOCAL_INFERENCE_TIMEOUT"] = "180"

from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.model_bridge import QwenBridge
import asyncio

async def test():
    bridge = QwenBridge()
    print(f"qwen_enabled: {bridge.qwen_enabled}")
    
    query = "My name is Celestine."
    deterministic_ir = {"target_ir": "WORKSPACE_QUERY", "confidence": 0.3}
    
    result = await bridge.infer_intent(query, deterministic_ir)
    print(f"Result: {result}")

asyncio.run(test())