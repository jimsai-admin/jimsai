"""
Data Source Connectors for Autonomous Training Agent

Connects to various data sources:
- Wikipedia (public knowledge)
- OpenSubtitles (multilingual conversations)
- User interactions (real system usage)
- Synthetic generation (Groq-generated fallback data)
- Web crawling (approved domains)
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator

import aiohttp


logger = logging.getLogger(__name__)


@dataclass
class DataSourceDocument:
    """A document from a data source."""

    source: str
    document_id: str
    content: str
    language: str
    metadata: dict[str, Any]


class DataSourceConnector(ABC):
    """Abstract base for data source connectors."""

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to data source."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    async def available_documents(self, limit: int = 1000) -> int:
        """Get count of available documents."""
        pass

    @abstractmethod
    async def fetch_documents(
        self,
        limit: int = 100,
        language: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Fetch documents from source."""
        pass


class WikipediaConnector(DataSourceConnector):
    """Connector for Wikipedia content."""

    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["en", "es", "fr", "de", "ar", "yo", "zh"]
        self.session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        """Initialize Wikipedia connection."""
        self.session = aiohttp.ClientSession()
        logger.info(f"🔗 Connected to Wikipedia ({len(self.languages)} languages)")

    async def disconnect(self) -> None:
        """Close Wikipedia connection."""
        if self.session:
            await self.session.close()

    async def available_documents(self, limit: int = 1000) -> int:
        """Wikipedia has millions of documents."""
        return 6000000

    async def fetch_documents(
        self,
        limit: int = 100,
        language: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Fetch random Wikipedia articles."""
        
        if language is None:
            language = "en"
        
        base_url = f"https://{language}.wikipedia.org/w/api.php"
        
        for i in range(min(limit, 10)):  # Limited to 10 for demo
            try:
                params = {
                    "action": "query",
                    "format": "json",
                    "list": "random",
                    "rnnamespace": 0,
                    "rnlimit": 1,
                }
                
                if not self.session:
                    raise RuntimeError("Not connected")
                
                async with self.session.get(base_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Wikipedia API error: {resp.status}")
                        continue
                    
                    data = await resp.json()
                    pages = data.get("query", {}).get("random", [])
                    
                    if not pages:
                        continue
                    
                    page_id = pages[0]["id"]
                    title = pages[0]["title"]
                    
                    # Fetch page content
                    content_params = {
                        "action": "query",
                        "pageid": page_id,
                        "format": "json",
                        "prop": "extracts",
                        "explaintext": 1,
                    }
                    
                    async with self.session.get(base_url, params=content_params, timeout=aiohttp.ClientTimeout(total=10)) as resp2:
                        if resp2.status == 200:
                            content_data = await resp2.json()
                            pages_content = content_data.get("query", {}).get("pages", {})
                            for page_content in pages_content.values():
                                extract = page_content.get("extract", "")
                                if extract:
                                    yield DataSourceDocument(
                                        source="wikipedia",
                                        document_id=f"wiki-{language}-{page_id}",
                                        content=extract[:5000],  # Limit size
                                        language=language,
                                        metadata={
                                            "title": title,
                                            "page_id": page_id,
                                            "wiki_lang": language,
                                        },
                                    )
                                    break
                
            except Exception as e:
                logger.warning(f"Error fetching from Wikipedia: {e}")
                continue
            
            await asyncio.sleep(0.5)  # Rate limiting


class UserInteractionsConnector(DataSourceConnector):
    """Connector for real user interactions from deployed system."""

    def __init__(self, pipeline=None):
        self.pipeline = pipeline

    async def connect(self) -> None:
        """Initialize user interactions connector."""
        logger.info("🔗 Connected to user interactions")

    async def disconnect(self) -> None:
        """Close user interactions connector."""
        pass

    async def available_documents(self, limit: int = 1000) -> int:
        """Get count of user interactions."""
        if not self.pipeline:
            return 0
        return len(self.pipeline.feedback_events)

    async def fetch_documents(
        self,
        limit: int = 100,
        language: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Fetch user interactions as training documents."""
        
        if not self.pipeline:
            return
        
        for feedback in self.pipeline.feedback_events[:limit]:
            # Convert feedback to document
            content = f"Query: {feedback.query}\nCorrection: {feedback.correction}"
            
            yield DataSourceDocument(
                source="user_interactions",
                document_id=f"feedback-{feedback.id}",
                content=content,
                language="en",  # Could detect from content
                metadata={
                    "type": "user_feedback",
                    "feedback_id": feedback.id,
                    "original_query": feedback.query,
                    "correction_type": feedback.correction_type,
                },
            )


class SyntheticGenerationConnector(DataSourceConnector):
    """Connector for Groq-generated synthetic data."""

    def __init__(self, groq_bridge=None):
        self.groq_bridge = groq_bridge
        self.prompts = [
            "Generate a diverse question about renewable energy and provide an answer.",
            "Generate a diverse question about machine learning and provide an answer.",
            "Generate a diverse question about history and provide an answer.",
            "Generate a diverse question about software engineering and provide an answer.",
            "Generate a diverse question about biology and provide an answer.",
        ]

    async def connect(self) -> None:
        """Initialize synthetic generation connector."""
        logger.info("🔗 Connected to synthetic generation")

    async def disconnect(self) -> None:
        """Close synthetic generation connector."""
        pass

    async def available_documents(self, limit: int = 1000) -> int:
        """Synthetic data available on-demand."""
        return limit * 10  # Can generate many on-demand

    async def fetch_documents(
        self,
        limit: int = 100,
        language: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Generate synthetic documents."""
        
        for i in range(min(limit, 20)):  # Limited for safety
            prompt = self.prompts[i % len(self.prompts)]
            
            # In production: call groq_bridge to generate
            # For now: use placeholder
            content = f"[Generated] {prompt}\n\nSynthetic answer for training."
            
            yield DataSourceDocument(
                source="synthetic_generation",
                document_id=f"synthetic-{i:04d}",
                content=content,
                language="en",
                metadata={
                    "type": "synthetic",
                    "prompt": prompt,
                    "confidence": 0.75,
                },
            )
            
            await asyncio.sleep(0.1)


class OpenSubtitlesConnector(DataSourceConnector):
    """Connector for OpenSubtitles multilingual content."""

    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["en", "es", "fr", "de", "ar", "yo"]
        self.samples = {
            "en": "Good morning. How are you today?",
            "es": "Buenos días. ¿Cómo estás hoy?",
            "fr": "Bonjour. Comment allez-vous?",
            "de": "Guten Morgen. Wie geht es Ihnen?",
            "ar": "صباح الخير. كيف حالك؟",
            "yo": "Bawo. Bawo ni o?"
        }

    async def connect(self) -> None:
        """Initialize OpenSubtitles connection."""
        logger.info(f"🔗 Connected to OpenSubtitles ({len(self.languages)} languages)")

    async def disconnect(self) -> None:
        """Close OpenSubtitles connection."""
        pass

    async def available_documents(self, limit: int = 1000) -> int:
        """OpenSubtitles has millions of subtitles."""
        return 50000000

    async def fetch_documents(
        self,
        limit: int = 100,
        language: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Fetch subtitle excerpts."""
        
        if language is None:
            language = "en"
        
        for i in range(min(limit, 10)):
            # In production: fetch actual subtitles from OpenSubtitles API
            sample_content = self.samples.get(language, "Sample dialogue in " + language)
            
            yield DataSourceDocument(
                source="opensubtitles",
                document_id=f"subtitle-{language}-{i:04d}",
                content=sample_content,
                language=language,
                metadata={
                    "type": "subtitle",
                    "movie_id": f"movie_{i}",
                },
            )
            
            await asyncio.sleep(0.05)


class DataSourceManager:
    """
    Manages all data source connectors.
    
    Coordinates:
    - Multiple simultaneous connections
    - Parallel fetching from different sources
    - Rate limiting and backoff
    - Error recovery
    """

    def __init__(self):
        self.connectors: dict[str, DataSourceConnector] = {}
        self.active: dict[str, bool] = {}

    def register_connector(self, name: str, connector: DataSourceConnector) -> None:
        """Register a data source connector."""
        self.connectors[name] = connector
        self.active[name] = False
        logger.info(f"📝 Registered connector: {name}")

    async def connect_all(self) -> None:
        """Connect all registered connectors."""
        tasks = [
            self._connect_with_error_handling(name, connector)
            for name, connector in self.connectors.items()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _connect_with_error_handling(self, name: str, connector: DataSourceConnector) -> None:
        """Connect a single connector with error handling."""
        try:
            await connector.connect()
            self.active[name] = True
        except Exception as e:
            logger.error(f"❌ Failed to connect {name}: {e}")
            self.active[name] = False

    async def disconnect_all(self) -> None:
        """Disconnect all connectors."""
        tasks = [
            connector.disconnect()
            for connector in self.connectors.values()
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def fetch_from_sources(
        self,
        source_names: list[str] | None = None,
        limit: int = 100,
        language: str | None = None,
    ) -> AsyncIterator[DataSourceDocument]:
        """Fetch documents from specified sources."""
        
        sources = source_names or list(self.connectors.keys())
        
        # Fetch from each source in parallel
        async def fetch_source(name: str) -> AsyncIterator[DataSourceDocument]:
            if not self.active.get(name, False):
                logger.warning(f"⚠️ Source {name} not active")
                return
            
            connector = self.connectors[name]
            count = 0
            async for doc in connector.fetch_documents(limit=limit, language=language):
                yield doc
                count += 1
            
            logger.debug(f"✓ Fetched {count} docs from {name}")
        
        # Merge results from all sources
        for source in sources:
            async for doc in fetch_source(source):
                yield doc


def create_default_manager(pipeline=None) -> DataSourceManager:
    """Create manager with all default connectors."""
    manager = DataSourceManager()
    
    # Register connectors
    manager.register_connector("wikipedia", WikipediaConnector())
    manager.register_connector("opensubtitles", OpenSubtitlesConnector())
    manager.register_connector("user_interactions", UserInteractionsConnector(pipeline))
    manager.register_connector("synthetic_generation", SyntheticGenerationConnector())
    
    return manager
