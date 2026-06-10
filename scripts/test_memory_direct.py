"""
Direct memory write + recall test using the pipeline directly.
Tests only the memory path without HTTP server overhead.
"""
import asyncio, os, time
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

from prototype.jimsai.pipeline import JimsAIPipeline
from prototype.jimsai.models import PipelineRequest, Modality

PASS, FAIL = "[PASS]", "[FAIL]"

async def main():
    print("Initializing pipeline...")
    pipeline = JimsAIPipeline()
    print("Pipeline ready.\n")

    # 1. Write
    t0 = time.perf_counter()
    wr = await pipeline.run(PipelineRequest(
        user_id="test_user",
        query="My name is Celestine.",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    ))
    ms = (time.perf_counter()-t0)*1000
    print(f"{PASS if wr.confidence > 0.5 else FAIL} Write ({ms:.0f}ms conf={wr.confidence:.2f})")
    print(f"  Write IR: {wr.ir.target_ir} profile_write={wr.ir.scope_constraints.get('profile_write')}")

    # 2. Recall immediately
    t0 = time.perf_counter()
    rr = await pipeline.run(PipelineRequest(
        user_id="test_user",
        query="What is my name?",
        modality=Modality.TEXT,
        workspace_id="test_ws",
        thread_id="mem_test",
        return_trace=True
    ))
    ms = (time.perf_counter()-t0)*1000
    resp = rr.response
    sources = rr.sources
    
    print(f"\nRecall ({ms:.0f}ms)")
    print(f"  IR: {rr.ir.target_ir} profile_query={rr.ir.scope_constraints.get('profile_query')}")
    print(f"  sources={len(sources)}")
    print(f"  response: {resp[:120]}")

    recalled = "celestine" in resp.lower() or len(sources) > 0
    print(f"\n{PASS if recalled else FAIL} Memory recall: {'PASS' if recalled else 'FAIL'}")

asyncio.run(main())