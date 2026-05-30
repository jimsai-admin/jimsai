from __future__ import annotations

import argparse
import asyncio

from prototype.jimsai.models import PipelineRequest
from prototype.jimsai.pipeline import JimsAIPipeline


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local JIMS-AI deterministic prototype")
    parser.add_argument("query")
    args = parser.parse_args()
    pipeline = JimsAIPipeline()
    result = await pipeline.run(PipelineRequest(user_id="cli", query=args.query))
    print(result.response)


if __name__ == "__main__":
    asyncio.run(main())
