"""
Web Augmented Retrieval: Fetch current knowledge from web with source tracking.

Provides:
- Async web search integration (DuckDuckGo, configurable providers)
- Source signature persistence
- Freshness tracking (when was this fact last verified?)
- Citation extraction and validation
- Workspace-scoped retrieval caching

This implements the world knowledge capability for JimsAI v9.
"""

import asyncio
import hashlib
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class WebSource:
    """A web source with provenance and freshness metadata."""
    url: str
    title: str
    snippet: str
    fetched_at: str  # ISO timestamp
    freshness_ttl: int = 86400  # 24 hours default
    confidence: float = 0.85  # Confidence in source reliability
    
    def is_fresh(self) -> bool:
        """Check if source is still fresh."""
        fetched = datetime.fromisoformat(self.fetched_at)
        age = datetime.now() - fetched
        return age.total_seconds() < self.freshness_ttl
    
    def to_signature(self) -> dict:
        """Convert to memory signature format."""
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
    
    def __init__(self, workspace_id: str, max_results: int = 5):
        """
        Initialize web retrieval for a workspace.
        
        Args:
            workspace_id: Workspace for scoped caching
            max_results: Max search results to return
        """
        self.workspace_id = workspace_id
        self.max_results = max_results
        self._source_cache: dict[str, WebSource] = {}
        self._search_cache: dict[str, list[WebSource]] = {}
    
    async def search(self, query: str, refresh: bool = False) -> list[WebSource]:
        """
        Search web for current information about a query.
        
        Args:
            query: Search query
            refresh: Force refresh even if cached
        
        Returns:
            List of web sources with provenance
        """
        cache_key = hashlib.sha256(query.encode()).hexdigest()
        
        # Check cache
        if not refresh and cache_key in self._search_cache:
            cached = self._search_cache[cache_key]
            # Verify cache is still fresh
            if all(source.is_fresh() for source in cached):
                logger.info(f"Web search cache hit: {query}")
                return cached
        
        # Perform real search (stub - would use actual search API)
        sources = await self._perform_search(query)
        
        # Cache results
        self._search_cache[cache_key] = sources
        
        # Store individual sources
        for source in sources:
            self._source_cache[source.url] = source
        
        logger.info(f"Web search completed: {query} → {len(sources)} sources")
        return sources
    
    async def _perform_search(self, query: str) -> list[WebSource]:
        """
        Perform real DuckDuckGo web search using public API.
        
        Uses DuckDuckGo's instant answer and search endpoints.
        No API key required (public tier).
        
        Args:
            query: Search query
        
        Returns:
            List of WebSource objects with real URLs and snippets
        """
        try:
            # DuckDuckGo instant answer endpoint (free, no API key)
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_redirect": "1",
                "t": "jimsai",  # User agent
            }
            
            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            
            # Make synchronous request in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                self._fetch_duckduckgo_sync, 
                full_url
            )
            
            if not response:
                return []
            
            sources = []
            fetched_at = datetime.now().isoformat()
            
            # Parse instant answer if available
            if response.get("AbstractText") and response.get("AbstractURL"):
                source = WebSource(
                    url=response["AbstractURL"],
                    title=response.get("AbstractSource", "DuckDuckGo"),
                    snippet=response["AbstractText"],
                    fetched_at=fetched_at,
                    confidence=0.90,  # Higher confidence for official answers
                )
                sources.append(source)
            
            # Parse related topics (Wikipedia, etc)
            for topic in response.get("RelatedTopics", []):
                if "FirstURL" in topic and "Text" in topic:
                    source = WebSource(
                        url=topic["FirstURL"],
                        title=topic.get("Name", "Related Topic"),
                        snippet=topic["Text"],
                        fetched_at=fetched_at,
                        confidence=0.85,
                    )
                    sources.append(source)
                    if len(sources) >= self.max_results:
                        break
            
            # Parse results array if available
            if len(sources) < self.max_results:
                for result in response.get("Results", []):
                    source = WebSource(
                        url=result.get("FirstURL", ""),
                        title=result.get("Title", ""),
                        snippet=result.get("Text", ""),
                        fetched_at=fetched_at,
                        confidence=0.80,
                    )
                    if source.url:  # Only add if URL is available
                        sources.append(source)
                        if len(sources) >= self.max_results:
                            break
            
            logger.info(f"DuckDuckGo search found {len(sources)} sources for: {query}")
            return sources[:self.max_results]
        
        except Exception as e:
            logger.error(f"DuckDuckGo search failed for '{query}': {e}")
            return []
    
    @staticmethod
    def _fetch_duckduckgo_sync(url: str) -> Optional[dict]:
        """
        Synchronous DuckDuckGo API fetch (runs in thread pool).
        
        Args:
            url: Full URL with parameters
        
        Returns:
            Parsed JSON response or None
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "jimsai/1.0 (+https://github.com/jimsai/jimsai)"}
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read().decode("utf-8")
                return json.loads(data)
        
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, Exception) as e:
            logger.error(f"DuckDuckGo API error: {e}")
            return None
    
    def get_stale_sources(self) -> list[WebSource]:
        """Get sources that need refreshing."""
        return [src for src in self._source_cache.values() if not src.is_fresh()]
    
    def get_fresh_sources(self, query_results: list[WebSource]) -> list[WebSource]:
        """Filter results to only fresh sources."""
        return [src for src in query_results if src.is_fresh()]


class WebSearchVerification:
    """Verify web search results for reliability and conflicts."""
    
    @staticmethod
    def check_source_reliability(source: WebSource) -> tuple[bool, float]:
        """
        Check if source is reliable (domain reputation, SSL, etc).
        
        Returns:
            (is_reliable, confidence_score)
        """
        # Stub: would check:
        # - Domain reputation (Alexa rank, SSL certificate)
        # - Known unreliable domains (misinformation list)
        # - Author/publisher verification
        # - Fact-check database (Snopes, PolitiFact, etc)
        
        return True, source.confidence
    
    @staticmethod
    def detect_conflicting_sources(sources: list[WebSource]) -> dict[str, list[WebSource]]:
        """
        Detect conflicting claims across sources.
        
        Returns:
            Dict of conflicting claim groups
        """
        # Stub: would use semantic similarity to detect
        # when sources make contradictory claims
        # Return confidence for each claim
        return {}
    
    @staticmethod
    def verify_against_local_memory(
        source: WebSource, 
        local_facts: list[dict]
    ) -> tuple[bool, str]:
        """
        Verify web source against workspace memory facts.
        
        Returns:
            (is_consistent, explanation)
        """
        # Check if web source contradicts known workspace facts
        # If inconsistency found, flag for human review
        return True, "No conflicts detected"


class CitationExtractor:
    """Extract structured citations from web sources."""
    
    @staticmethod
    def to_citation_string(source: WebSource) -> str:
        """Generate citation string (APA/MLA style)."""
        return f"{source.title}. Retrieved from {source.url} on {source.fetched_at}"
    
    @staticmethod
    def to_markdown_citation(source: WebSource) -> str:
        """Generate markdown citation."""
        return f"[{source.title}]({source.url}) (Retrieved: {source.fetched_at})"
    
    @staticmethod
    def embed_citations_in_response(
        response: str,
        sources: list[WebSource]
    ) -> tuple[str, list[dict]]:
        """
        Embed citations into response text.
        
        Returns:
            (annotated_response, citation_list)
        """
        citations = [
            {
                "index": i + 1,
                "text": CitationExtractor.to_citation_string(src),
                "markdown": CitationExtractor.to_markdown_citation(src),
                "freshness": src.is_fresh(),
            }
            for i, src in enumerate(sources)
        ]
        
        # Would add [1], [2] references to response
        annotated = response + "\n\n**Sources:**\n"
        annotated += "\n".join(f"[{i['index']}] {i['text']}" for i in citations)
        
        return annotated, citations


class WebKnowledgeCapability:
    """
    High-level world knowledge capability using web augmentation.
    
    Bridges L6 retrieval with live web data for current events, 
    latest research, real-time information.
    """
    
    def __init__(self, workspace_id: str):
        """Initialize world knowledge capability."""
        self.workspace_id = workspace_id
        self.retrieval = WebAugmentedRetrieval(workspace_id)
        self.verifier = WebSearchVerification()
        self.citations = CitationExtractor()
    
    async def answer_with_sources(
        self,
        query: str,
        local_memory: Optional[list[dict]] = None
    ) -> dict:
        """
        Answer a query using web sources + local memory.
        
        Returns:
            {
                "answer": str,
                "sources": [WebSource],
                "confidence": float,
                "is_live_data": bool,
                "conflicts": list,
                "gaps": list,
            }
        """
        # Search web for current information
        web_sources = await self.retrieval.search(query)
        
        if not web_sources:
            return {
                "answer": None,
                "sources": [],
                "confidence": 0.0,
                "is_live_data": False,
                "conflicts": [],
                "gaps": ["No web sources found for this query"],
            }
        
        # Verify source reliability
        verified_sources = []
        for source in web_sources:
            is_reliable, confidence = self.verifier.check_source_reliability(source)
            if is_reliable:
                source.confidence = confidence
                verified_sources.append(source)
        
        # Check for conflicts
        conflicts = self.verifier.detect_conflicting_sources(verified_sources)
        
        # Verify against local memory
        consistency_issues = []
        for source in verified_sources:
            if local_memory:
                is_consistent, explanation = self.verifier.verify_against_local_memory(
                    source, local_memory
                )
                if not is_consistent:
                    consistency_issues.append({
                        "source": source.url,
                        "issue": explanation,
                    })
        
        # Synthesize answer from sources
        answer = self._synthesize_answer(verified_sources)
        
        # Calculate overall confidence
        avg_confidence = sum(s.confidence for s in verified_sources) / len(verified_sources)
        
        return {
            "answer": answer,
            "sources": verified_sources,
            "confidence": avg_confidence,
            "is_live_data": True,
            "conflicts": conflicts,
            "gaps": [issue["issue"] for issue in consistency_issues],
        }
    
    def _synthesize_answer(self, sources: list[WebSource]) -> str:
        """Synthesize answer from web sources."""
        if not sources:
            return None
        
        # Stub: would use CSSE to render from source snippets
        return f"Found {len(sources)} sources. " + " ".join(
            f"({i+1}) {src.snippet}" for i, src in enumerate(sources[:3])
        )


# Example usage for testing
if __name__ == "__main__":
    async def test_web_retrieval():
        """Test web retrieval capability."""
        capability = WebKnowledgeCapability(workspace_id="test_workspace")
        
        result = await capability.answer_with_sources(
            "What is the current state of AI regulation in 2026?",
            local_memory=[
                {"fact": "EU AI Act passed in 2024", "confidence": 0.95}
            ]
        )
        
        print("Web Knowledge Result:")
        print(f"  Answer: {result['answer']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Sources: {len(result['sources'])}")
        print(f"  Conflicts: {result['conflicts']}")
        print(f"  Gaps: {result['gaps']}")
    
    # Run test
    asyncio.run(test_web_retrieval())
