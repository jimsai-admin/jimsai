from __future__ import annotations

import asyncio
import time

from prototype.jimsai.models import PipelineRequest
from prototype.jimsai.pipeline import JimsAIPipeline


async def main() -> None:
    pipeline = JimsAIPipeline()
    query = "What services are affected if UserModel.id changes?"
    start = time.perf_counter()
    first = await pipeline.run(PipelineRequest(user_id="bench", query=query))
    second = await pipeline.run(PipelineRequest(user_id="bench", query=query))
    elapsed_ms = (time.perf_counter() - start) * 1000
    print({
        "deterministic_response": first.response == second.response,
        "deterministic_ir": first.ir.target_ir == second.ir.target_ir,
        "latency_ms_total_two_runs": round(elapsed_ms, 3),
        "sources": first.sources,
        "gaps": first.gaps,
    })


if __name__ == "__main__":
    asyncio.run(main())
