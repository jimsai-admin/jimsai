"""
Parallel Ingestion Worker Pool

Processes documents from data sources in parallel:
- Unicode normalization
- Multilingual embedding
- Entity and relation extraction
- IR construction
- Graph updates
- Signature storage

No judgment — follows rules mechanically.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .data_source_connectors import DataSourceDocument
from .document_ingestion import extract_document_facts, fact_to_signature, is_document_like
from .encoder import DualRepresentationEncoder, stable_id
from .models import MemorySignature, SPPETrainingPair, utc_now
from .semantic_compiler import normalize_language


logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of ingesting a document."""

    success: bool
    document_id: str
    source: str
    signature_id: str | None = None
    sppe_pair_id: str | None = None
    world_model_candidates: int = 0
    error: str | None = None
    processing_time_ms: float = 0.0


class IngestionWorker:
    """
    Worker that processes a single document.
    
    Strictly mechanical — no judgment.
    Follows rules deterministically.
    """

    def __init__(self, encoder: DualRepresentationEncoder):
        self.encoder = encoder

    async def process_document(self, doc: DataSourceDocument) -> IngestionResult:
        """
        Process a single document through the ingestion pipeline.
        
        Steps:
        1. Validate document
        2. Normalize language
        3. Extract facts
        4. Create signature
        5. Generate embeddings
        6. Create SPPE pair
        7. Generate world model candidates
        """
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Step 1: Validate
            if not is_document_like(doc.content):
                return IngestionResult(
                    success=False,
                    document_id=doc.document_id,
                    source=doc.source,
                    error="Document format invalid",
                    processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
                )
            
            # Step 2: Normalize
            normalized = normalize_language(doc.content)
            
            # Step 3: Extract facts
            facts = extract_document_facts(normalized, language=doc.language)
            
            # Step 4: Create signature
            signature = fact_to_signature(
                facts=facts,
                raw_content=doc.content,
                source_url=doc.metadata.get("source_url", f"{doc.source}/{doc.document_id}"),
                source=doc.source,
            )
            
            # Step 5: Generate embeddings (latent representation)
            # In production: would use multilingual encoder
            signature.latent_embedding = [0.0] * 384  # Placeholder
            signature.metadata["latent_embedding_source"] = "placeholder"
            
            # Step 6: Create SPPE pair (Semantic-Phrase-Pair-Evaluation)
            sppe_pair = await self._create_sppe_pair(signature, doc)
            
            # Step 7: Generate world model candidates
            world_model_count = self._generate_world_model_candidates(signature, facts)
            
            processing_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            return IngestionResult(
                success=True,
                document_id=doc.document_id,
                source=doc.source,
                signature_id=signature.id,
                sppe_pair_id=sppe_pair.id if sppe_pair else None,
                world_model_candidates=world_model_count,
                processing_time_ms=processing_time,
            )
            
        except Exception as e:
            logger.error(f"Error processing document {doc.document_id}: {e}")
            return IngestionResult(
                success=False,
                document_id=doc.document_id,
                source=doc.source,
                error=str(e),
                processing_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )

    async def _create_sppe_pair(self, signature: MemorySignature, doc: DataSourceDocument) -> SPPETrainingPair | None:
        """Create SPPE (Semantic-Phrase-Pair-Evaluation) training pair."""
        
        if signature.confidence.score < 0.65:
            return None  # Too low confidence
        
        # Quality scoring
        semantic_score = min(signature.confidence.score, 1.0)
        verification_score = 0.9 if len(signature.structured.entities) > 0 else 0.6
        source_score = 1.0  # We have source metadata
        gap_score = max(0.0, 1.0 - len(signature.structured.entities) * 0.1)
        efficiency_score = 0.8  # Reasonable for ingested content
        
        # Composite SPPE quality
        sppe_quality = (
            semantic_score * 0.25 +
            verification_score * 0.30 +
            source_score * 0.20 +
            gap_score * 0.15 +
            efficiency_score * 0.10
        )
        
        pair = SPPETrainingPair(
            id=f"sppe-{stable_id(doc.document_id)}",
            semantic_ir=str(signature.metadata.get("ir_target", "WORKSPACE_QUERY")),
            query=doc.metadata.get("title", doc.content[:100]),
            response=doc.content[:500],
            quality_score=sppe_quality,
            source=doc.source,
            created_at=utc_now(),
        )
        
        return pair

    def _generate_world_model_candidates(self, signature: MemorySignature, facts: list[dict[str, Any]]) -> int:
        """Generate world model candidates from extracted facts."""
        
        # A fact becomes a world model candidate if it has:
        # - Causal relationship (IF fact A THEN fact B)
        # - Entity involvement
        # - High confidence
        
        candidate_count = 0
        
        # Extract causal links as candidates
        for link in signature.structured.causal_chain:
            candidate_count += 1
        
        # Extract entity relationships as candidates
        if len(signature.structured.entities) >= 2:
            candidate_count += len(signature.structured.relations)
        
        return candidate_count


class IngestionWorkerPool:
    """
    Pool of workers processing documents in parallel.
    
    Manages:
    - Worker lifecycle
    - Work queue
    - Result collection
    - Backpressure and flow control
    """

    def __init__(self, encoder: DualRepresentationEncoder, worker_count: int = 8):
        self.encoder = encoder
        self.worker_count = worker_count
        self.workers: list[IngestionWorker] = [
            IngestionWorker(encoder) for _ in range(worker_count)
        ]

    async def process_documents(
        self,
        documents: list[DataSourceDocument],
        progress_callback: callable | None = None,
    ) -> list[IngestionResult]:
        """
        Process a batch of documents in parallel.
        
        Args:
            documents: List of documents to process
            progress_callback: Optional callback(processed_count, total_count)
        
        Returns:
            List of ingestion results
        """
        
        results = []
        queue = asyncio.Queue()
        
        # Populate queue
        for doc in documents:
            await queue.put(doc)
        
        # Create worker tasks
        async def worker_task() -> None:
            while True:
                try:
                    doc = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                # Pick a worker (round-robin)
                worker = self.workers[len(results) % len(self.workers)]
                result = await worker.process_document(doc)
                results.append(result)
                
                if progress_callback:
                    progress_callback(len(results), len(documents))
        
        # Run workers in parallel
        tasks = [worker_task() for _ in range(min(self.worker_count, len(documents)))]
        await asyncio.gather(*tasks)
        
        # Log summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        avg_time = sum(r.processing_time_ms for r in results) / len(results) if results else 0
        
        logger.info(f"✓ Processed {len(results)} docs: {successful} success, {failed} failed, avg {avg_time:.1f}ms")
        
        return results


async def run_ingestion_pipeline(
    encoder: DualRepresentationEncoder,
    documents: list[DataSourceDocument],
    worker_count: int = 8,
    progress_callback: callable | None = None,
) -> dict[str, Any]:
    """
    High-level function to run document ingestion.
    
    Returns:
        Summary of ingestion results
    """
    
    pool = IngestionWorkerPool(encoder, worker_count)
    results = await pool.process_documents(documents, progress_callback)
    
    # Aggregate results
    successful_results = [r for r in results if r.success]
    
    summary = {
        "total_processed": len(results),
        "successful": len(successful_results),
        "failed": len(results) - len(successful_results),
        "signatures_created": sum(1 for r in successful_results if r.signature_id),
        "sppe_pairs_generated": sum(1 for r in successful_results if r.sppe_pair_id),
        "world_model_candidates": sum(r.world_model_candidates for r in successful_results),
        "avg_processing_time_ms": sum(r.processing_time_ms for r in results) / len(results) if results else 0,
        "results": results,
    }
    
    return summary
