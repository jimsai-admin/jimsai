"""
Debug memory write + recall - check full pipeline run step by step
"""
import asyncio, os, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality

# Patch the learning layer to debug
original_learn = None

def debug_learn(self, signature):
    print(f"[DEBUG] learn called with signature: {signature.id}, confidence: {signature.confidence.score}")
    result = original_learn(self, signature)
    print(f"[DEBUG] Memory stats after learn: {self.memory.stats()}")
    return result

async def main():
    global original_learn
    from prototype.jimsai.runtime_layers import RealTimeLearningLayer
    original_learn = RealTimeLearningLayer.learn
    RealTimeLearningLayer.learn = debug_learn
    
    print("Initializing pipeline...")
    pipeline = JimsAIPipeline()
    print("Pipeline ready.\n")

    # Clear cache
    pipeline.result_cache.clear()
    print("Cache cleared.")
    
    # Check initial memory stats
    print(f"Initial memory stats: {pipeline.memory.stats()}")

    # Run through full pipeline
    request = PipelineRequest(
        user_id="test_user",
        query="My name is Celestine.",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    )
    
    wr = await pipeline.run(request)
    print(f"\nWrite: conf={wr.confidence:.2f}, IR={wr.ir.target_ir}")
    print(f"Final memory stats: {pipeline.memory.stats()}")
    
    # Check all signatures in all layers
    print(f"Sensory: {list(pipeline.memory.sensory.keys())}")
    print(f"Working: {list(pipeline.memory.working.keys())}")
    print(f"Episodic: {list(pipeline.memory.episodic.keys())}")
    print(f"Semantic: {list(pipeline.memory.semantic.keys())}")

asyncio.run(main())