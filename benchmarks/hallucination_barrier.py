from __future__ import annotations

import asyncio

from prototype.jimsai.models import PipelineRequest
from prototype.jimsai.pipeline import JimsAIPipeline


async def main() -> None:
    pipeline = JimsAIPipeline()
    result = await pipeline.run(PipelineRequest(user_id="bench", query="Tell me about UnknownServiceZeta impacts"))
    unsupported_claims = [step for step in result.reasoning_chain if not step.sources and step.relation != "HEDGE"]
    print({
        "unsupported_claim_count": len(unsupported_claims),
        "explicit_gaps": result.gaps,
        "response": result.response,
    })


if __name__ == "__main__":
    asyncio.run(main())
