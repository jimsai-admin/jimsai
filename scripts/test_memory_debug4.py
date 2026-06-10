"""
Debug memory write + recall - check full pipeline run
"""
import asyncio, os, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality

async def main():
    print("Initializing pipeline...")
    pipeline = JimsAIPipeline()
    print("Pipeline ready.\n")

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
    print(f"Write: conf={wr.confidence:.2f}, IR={wr.ir.target_ir}")
    print(f"Memory stats after write: {pipeline.memory.stats()}")
    
    # Check all signatures in all layers
    print(f"Sensory: {list(pipeline.memory.sensory.keys())}")
    print(f"Working: {list(pipeline.memory.working.keys())}")
    print(f"Episodic: {list(pipeline.memory.episodic.keys())}")
    print(f"Semantic: {list(pipeline.memory.semantic.keys())}")
    
    # Check session
    session = pipeline._load_session("test_user", "mem_test")
    print(f"Session: {session}")

asyncio.run(main())