"""
Web search adapter for the JimsAI pipeline (Lambda-boundary-safe).

Re-exports WebAugmentedRetrieval and WebSource from the world-knowledge service
so that pipeline.py can import them without a cross-package path.

The actual implementation lives in services/world-knowledge/web_retrieval.py.
When running inside Lambda the prototype package is bundled together, so we
copy-reference the key classes here for clean import.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WebSource:
    """A web source with provenance and freshness metadata."""

    url: str
    title: str
    snippet: str
    fetched_at: str
    freshness_ttl: int = 86400
    confidence: float = 0.85

    def is_fresh(self) -> bool:
        fetched = datetime.fromisoformat(self.fetched_at)
        return (datetime.now() - fetched).total_seconds() < self.freshness_ttl

    def to_signature(self) -> dict:
        return {
            "type": "web_source",
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "fetched_at": self.fetched_at,
            "freshness": self.is_fresh(),
            "confidence": self.confidence,
            "source_hash": hashlib.sha256(self.url.encode()).hexdigest(),
        }


class WebAugmentedRetrieval:
    """Fetch world knowledge from web with source tracking."""

    def __init__(self, workspace_id: str, max_results: int = 5) -> None:
        self.workspace_id = workspace_id
        self.max_results = max_results
        self._search_cache: dict[str, list[WebSource]] = {}

    async def search(self, query: str, refresh: bool = False) -> list[WebSource]:
        cache_key = hashlib.sha256(query.encode()).hexdigest()
        if not refresh and cache_key in self._search_cache:
            cached = self._search_cache[cache_key]
            if all(s.is_fresh() for s in cached):
                return cached
        sources = await self._perform_search(query)
        self._search_cache[cache_key] = sources
        return sources

    async def _perform_search(self, query: str) -> list[WebSource]:
        fetched_at = datetime.now().isoformat()

        # Try duckduckgo_search package first (richer results)
        try:
            from duckduckgo_search import DDGS  # type: ignore[import]
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=self.max_results)),
            )
            sources = [
                WebSource(
                    url=r.get("href", ""),
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    fetched_at=fetched_at,
                    confidence=0.85,
                )
                for r in results
                if r.get("href")
            ]
            logger.info("duckduckgo_search found %d results for: %s", len(sources), query)
            return sources[: self.max_results]
        except ImportError:
            pass  # fall through to urllib instant-answer path
        except Exception as exc:
            logger.warning("duckduckgo_search failed: %s — falling back to instant answer API", exc)

        # Fallback: DuckDuckGo instant answer API (no package needed)
        try:
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_redirect": "1", "t": "jimsai"}
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self._fetch_ddg_sync, full_url)
            if not response:
                return []
            sources: list[WebSource] = []
            if response.get("AbstractText") and response.get("AbstractURL"):
                sources.append(
                    WebSource(
                        url=response["AbstractURL"],
                        title=response.get("AbstractSource", "DuckDuckGo"),
                        snippet=response["AbstractText"],
                        fetched_at=fetched_at,
                        confidence=0.90,
                    )
                )
            for topic in response.get("RelatedTopics", []):
                if "FirstURL" in topic and "Text" in topic:
                    sources.append(
                        WebSource(
                            url=topic["FirstURL"],
                            title=topic.get("Name", "Related"),
                            snippet=topic["Text"],
                            fetched_at=fetched_at,
                            confidence=0.80,
                        )
                    )
                    if len(sources) >= self.max_results:
                        break
            logger.info("DDG instant answer found %d sources for: %s", len(sources), query)
            return sources[: self.max_results]
        except Exception as exc:
            logger.error("Web search failed for '%s': %s", query, exc)
            return []

    @staticmethod
    def _fetch_ddg_sync(url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "jimsai/2.0 (+https://github.com/jimsai/jimsai)"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.error("DDG API error: %s", exc)
            return None
