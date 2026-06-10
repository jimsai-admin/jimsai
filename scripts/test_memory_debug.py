"""
Debug memory write + recall - check what's in memory
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

    # 1. Write
    wr = await pipeline.run(PipelineRequest(
        user_id="test_user",
        query="My name is Celestine.",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    ))
    print(f"Write: conf={wr.confidence:.2f}, IR={wr.ir.target_ir}")
    print(f"Memory stats after write: {pipeline.memory.stats()}")

    # Check what signatures are in memory
    print(f"\nMemory store keys: {list(pipeline.memory._store.keys())[:10]}")
    
    # Check graph
    print(f"Graph nodes: {len(pipeline.graph.nodes)}")

    # Check session
    session = pipeline._load_session("test_user", "mem_test")
    print(f"Session: {session}")

    # 2. Recall immediately
    rr = await pipeline.run(PipelineRequest(
        user_id="test_user",
        query="What is my name?",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    ))
    print(f"\nRecall: conf={rr.confidence:.2f}, IR={rr.ir.target_ir}")
    print(f"Response: {rr.response[:200]}")
    print(f"Sources: {rr.sources}")
    print(f"Memory stats after recall: {pipeline.memory.stats()}")

asyncio.run(main())