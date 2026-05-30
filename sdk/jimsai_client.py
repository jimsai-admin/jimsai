from __future__ import annotations

import httpx


class JimsAIClient:
    def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "sdk-user") -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id

    async def query(self, query: str, return_trace: bool = True) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/query",
                json={"user_id": self.user_id, "query": query, "return_trace": return_trace},
            )
            response.raise_for_status()
            return response.json()
