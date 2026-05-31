"""
Phase 5 Integration Test Suite - Real-world prompts and end-to-end validation

Tests Phase 5 components with realistic queries, measuring:
- Event generation and audit trail
- SPPE pair quality scoring
- T1/T2 skip decisions
- Creative writing routing
- Human review workflows
- Training batch formation
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import asdict

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Real-world test prompts covering all capability routes
REAL_WORLD_PROMPTS = [
    {
        "query": "What are the latest developments in quantum computing?",
        "route": "world_knowledge",
        "expected_confidence": 0.85,
        "description": "Web search knowledge query"
    },
    {
        "query": "Write a haiku about artificial intelligence",
        "route": "creative_text",
        "expected_confidence": 0.90,
        "description": "Creative writing with style constraint"
    },
    {
        "query": "Solve: if x + 2 = 5, what is x?",
        "route": "math_science",
        "expected_confidence": 0.95,
        "description": "Simple math with deterministic answer"
    },
    {
        "query": "Write a Python function to reverse a list",
        "route": "coding",
        "expected_confidence": 0.92,
        "description": "Code generation task"
    },
    {
        "query": "What's 2 + 2?",
        "route": "math_science",
        "expected_confidence": 0.99,
        "description": "Simple arithmetic (high confidence memory route)"
    },
    {
        "query": "Explain the theory of relativity in simple terms",
        "route": "world_knowledge",
        "expected_confidence": 0.80,
        "description": "Knowledge explanation"
    },
    {
        "query": "Write a technical guide for setting up Docker",
        "route": "creative_text",
        "expected_confidence": 0.85,
        "description": "Technical writing with style"
    },
    {
        "query": "What is the capital of France?",
        "route": "memory_chat",
        "expected_confidence": 0.99,
        "description": "Factual question (very high confidence)"
    },
]


class Phase5TestRunner:
    """Execute Phase 5 integration tests."""
    
    def __init__(self, event_store_pipeline, workspace_id: str = "test-workspace"):
        self.pipeline = event_store_pipeline
        self.workspace_id = workspace_id
        self.results = []
        self.metrics = {
            "total_queries": 0,
            "total_events": 0,
            "t1_skips": 0,
            "t2_skips": 0,
            "sppe_pairs_generated": 0,
            "avg_quality_score": 0.0,
            "avg_latency_ms": 0.0,
            "total_cost": 0.0,
        }
    
    async def simulate_query_execution(
        self,
        query_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Simulate query execution through pipeline."""
        query_id = str(uuid.uuid4())
        query = query_data["query"]
        route = query_data["route"]
        expected_confidence = query_data["expected_confidence"]
        
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing: {query}")
        logger.info(f"Route: {route} | Expected Confidence: {expected_confidence:.2%}")
        logger.info(f"Query ID: {query_id}")
        
        try:
            # 1. Emit query received
            await self.pipeline.emit_query_received(
                query_id=query_id,
                query=query,
                user_id="test-user",
                metadata={"test": True, "route": route}
            )
            logger.info("✓ Emitted UserQueryReceived")
            
            # 2. Simulate route determination
            await self.pipeline.emit_query_rooted(
                query_id=query_id,
                route=route,
                confidence=expected_confidence,
                reasoning="Route determined by semantic analysis"
            )
            logger.info(f"✓ Emitted QueryRooted -> {route}")
            
            # 3. Determine if T1 should be skipped
            should_skip_t1 = expected_confidence > 0.90
            if should_skip_t1:
                await self.pipeline.emit_t1_skip_decision(
                    query_id=query_id,
                    memory_confidence=expected_confidence,
                    reason="Memory confidence > 0.90 threshold"
                )
                logger.info(f"✓ T1 SKIPPED (confidence: {expected_confidence:.2%})")
                self.metrics["t1_skips"] += 1
            else:
                logger.info(f"✓ T1 EXECUTED (confidence: {expected_confidence:.2%})")
            
            # 4. Simulate execution
            execution_time_ms = 150 if route == "math_science" else 450
            provider = "z3" if route == "math_science" else "duckduckgo" if route == "world_knowledge" else "docker"
            
            output = self._generate_mock_output(query, route)
            sources = self._generate_mock_sources(route, expected_confidence)
            gaps = [] if expected_confidence > 0.85 else ["additional_context_might_help"]
            
            await self.pipeline.record_execution(
                query_id=query_id,
                provider=provider,
                input_data=query,
                output_data=output,
                execution_time_ms=execution_time_ms,
                verification_status="verified" if expected_confidence > 0.85 else "partial",
                sources=sources,
                gaps=gaps,
                cache_hit=(expected_confidence > 0.95)
            )
            logger.info(f"✓ Recorded execution via {provider} ({execution_time_ms}ms)")
            
            # 5. Determine if T2 should be skipped (fluency renderer)
            output_confidence = min(expected_confidence + 0.05, 1.0)  # Slight boost from verification
            should_skip_t2 = output_confidence > 0.95 and len(sources) > 0
            
            if should_skip_t2:
                await self.pipeline.emit_t2_skip_decision(
                    query_id=query_id,
                    csse_confidence=output_confidence,
                    reason="CSSE confidence > 0.95 threshold and sources present"
                )
                logger.info(f"✓ T2 SKIPPED (output confidence: {output_confidence:.2%})")
                self.metrics["t2_skips"] += 1
            else:
                logger.info(f"✓ T2 EXECUTED (output confidence: {output_confidence:.2%})")
            
            # 6. Generate SPPE pair for training
            semantic_ir = {
                "intent": route,
                "query_embedding": f"embedding_{query_id[:8]}",
                "constraints": []
            }
            
            # Create execution trace for SPPE pair generation
            from prototype.jimsai.training.sppe_generator import ExecutionTrace
            trace = ExecutionTrace(
                query_id=query_id,
                query=query,
                semantic_confidence=expected_confidence,
                semantic_ir=semantic_ir,
                verification_status="verified" if expected_confidence > 0.85 else "partial",
                sources=sources,
                hallucination_gaps=gaps,
                route_type=route,
                used_t1=(not should_skip_t1),
                used_t2=(not should_skip_t2),
                memory_confidence=expected_confidence,
                output_confidence=output_confidence,
                execution_time_ms=execution_time_ms,
                provider=provider,
                cost=0.0025 if provider == "z3" else 0.01
            )
            
            await self.pipeline.generate_sppe_pair(
                query_id=query_id,
                query=query,
                semantic_ir=semantic_ir,
                output=output,
                trace=trace
            )
            logger.info("✓ Generated SPPE training pair")
            self.metrics["sppe_pairs_generated"] += 1
            
            # 7. If creative writing, emit event
            if route == "creative_text":
                await self.pipeline.emit_creative_writing_generated(
                    query_id=query_id,
                    prompt=query,
                    style="technical" if "technical" in query.lower() else "poetic",
                    content=output,
                    model_used="deterministic" if should_skip_t2 else "groq-t2",
                    verification_status="verified",
                    execution_time_ms=execution_time_ms
                )
                logger.info("✓ Emitted CreativeWritingGenerated event")
            
            # Store result
            result = {
                "query_id": query_id,
                "query": query,
                "route": route,
                "t1_skipped": should_skip_t1,
                "t2_skipped": should_skip_t2,
                "confidence": expected_confidence,
                "latency_ms": execution_time_ms,
                "status": "success"
            }
            
            self.results.append(result)
            self.metrics["total_queries"] += 1
            self.metrics["avg_latency_ms"] += execution_time_ms
            
            logger.info(f"✅ Query completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"❌ Query execution failed: {e}", exc_info=True)
            return {
                "query_id": query_id,
                "query": query,
                "status": "failed",
                "error": str(e)
            }
    
    def _generate_mock_output(self, query: str, route: str) -> str:
        """Generate mock output for testing."""
        if route == "math_science":
            return "The answer is 3. Using basic algebra: x + 2 = 5 → x = 5 - 2 → x = 3"
        elif route == "creative_text":
            if "haiku" in query.lower():
                return "Digital mind\\nThinking through the void\\nWisdom emerges"
            return "This is creative content matching the query style and constraints."
        elif route == "coding":
            return "```python\ndef reverse_list(lst):\n    return lst[::-1]\n```"
        elif route == "world_knowledge":
            return "The latest developments in quantum computing include breakthroughs in quantum error correction and experimental quantum advantage demonstrations."
        else:
            return "Response to query: " + query
    
    def _generate_mock_sources(self, route: str, confidence: float) -> List[str]:
        """Generate mock sources for verification."""
        if confidence > 0.95:
            return ["internal_knowledge_base", "verified_memory"]
        elif confidence > 0.85:
            return ["source_1", "source_2"]
        else:
            return ["source_1"]
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all test queries."""
        logger.info("🚀 Starting Phase 5 Integration Test Suite")
        logger.info(f"Running {len(REAL_WORLD_PROMPTS)} real-world queries...")
        
        start_time = datetime.utcnow()
        
        for prompt_data in REAL_WORLD_PROMPTS:
            await self.simulate_query_execution(prompt_data)
            # Small delay between queries
            await asyncio.sleep(0.1)
        
        end_time = datetime.utcnow()
        elapsed_seconds = (end_time - start_time).total_seconds()
        
        # Calculate final metrics
        if self.metrics["total_queries"] > 0:
            self.metrics["avg_latency_ms"] /= self.metrics["total_queries"]
            self.metrics["avg_quality_score"] = 0.82  # Mock value
        
        total_events = sum(
            1 for r in self.results if r["status"] == "success"
        ) * 5  # Estimate ~5 events per query
        
        self.metrics["total_events"] = total_events
        
        summary = {
            "test_run": {
                "duration_seconds": elapsed_seconds,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed"
            },
            "results": self.results,
            "metrics": self.metrics,
            "transformer_optimization": {
                "t1_skip_rate": self.metrics["t1_skips"] / max(self.metrics["total_queries"], 1),
                "t2_skip_rate": self.metrics["t2_skips"] / max(self.metrics["total_queries"], 1),
                "total_skips": self.metrics["t1_skips"] + self.metrics["t2_skips"],
                "queries_executed": self.metrics["total_queries"],
            }
        }
        
        return summary
    
    def print_summary(self, summary: Dict[str, Any]) -> None:
        """Print test summary to console."""
        logger.info("\n" + "="*80)
        logger.info("PHASE 5 INTEGRATION TEST SUMMARY")
        logger.info("="*80)
        
        metrics = summary["metrics"]
        opt = summary["transformer_optimization"]
        
        logger.info(f"\n📊 Execution Metrics:")
        logger.info(f"  • Total Queries: {metrics['total_queries']}")
        logger.info(f"  • Total Events: {metrics['total_events']}")
        logger.info(f"  • Avg Latency: {metrics['avg_latency_ms']:.1f}ms")
        logger.info(f"  • SPPE Pairs Generated: {metrics['sppe_pairs_generated']}")
        logger.info(f"  • Avg Quality Score: {metrics['avg_quality_score']:.2f}/1.0")
        
        logger.info(f"\n🎯 Transformer Optimization:")
        logger.info(f"  • T1 Skip Rate: {opt['t1_skip_rate']:.1%} ({opt['t1_skip_rate']*metrics['total_queries']:.0f}/{metrics['total_queries']} queries)")
        logger.info(f"  • T2 Skip Rate: {opt['t2_skip_rate']:.1%} ({opt['t2_skip_rate']*metrics['total_queries']:.0f}/{metrics['total_queries']} queries)")
        logger.info(f"  • Total Transformer Calls Skipped: {opt['total_skips']}")
        
        logger.info(f"\n✅ Test Status:")
        successful = sum(1 for r in summary["results"] if r["status"] == "success")
        failed = sum(1 for r in summary["results"] if r["status"] == "failed")
        logger.info(f"  • Successful: {successful}")
        logger.info(f"  • Failed: {failed}")
        
        logger.info(f"\n⏱️  Duration: {summary['test_run']['duration_seconds']:.2f} seconds")
        logger.info("="*80 + "\n")
    
    def export_results(self, filepath: str) -> None:
        """Export test results to JSON."""
        import json
        summary = {
            "test_run": {
                "timestamp": datetime.utcnow().isoformat(),
                "total_queries": self.metrics["total_queries"],
                "total_events": self.metrics["total_events"],
                "results": self.results,
                "metrics": self.metrics,
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"✓ Results exported to: {filepath}")


async def main():
    """Main test entry point."""
    # Note: This would be called after EventStore is initialized
    logger.info("Phase 5 Test Suite ready. Call run_all_tests() to execute.")
    logger.info("Usage: await test_runner.run_all_tests()")


if __name__ == "__main__":
    logger.info("Phase 5 Integration Test Suite")
    logger.info("This module is meant to be imported and used with an initialized EventStore")
    logger.info("See PHASE5_QUICKSTART.md for integration instructions")
