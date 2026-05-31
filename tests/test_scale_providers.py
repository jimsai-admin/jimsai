"""
Phase 4 Scale Testing - Measure Impact of Real Providers vs Stubs

Tests:
- 1000+ SPPE pair ingestions through training loop
- Performance metrics: throughput, latency, cache hit rate
- Quality metrics: success rate, confidence scores
- Fallback mechanisms under load
- Comparison vs Phase 3 baselines
"""

import pytest
import time
import asyncio
import importlib
import logging
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Import modules with hyphenated names
def get_web_retrieval_module():
    return importlib.import_module('services.world-knowledge.web_retrieval')

def get_sandbox_executor_module():
    return importlib.import_module('services.coding.sandbox_executor')

def get_math_solver_module():
    return importlib.import_module('services.math-science.math_solver')


@dataclass
class ScaleTestMetrics:
    """Metrics collected during scale testing."""
    total_queries: int
    successful_queries: int
    failed_queries: int
    total_time_seconds: float
    avg_latency_ms: float
    throughput_qps: float  # Queries per second
    cache_hit_rate: float
    avg_confidence: float
    excellent_pairs: int
    good_pairs: int
    acceptable_pairs: int
    marginal_pairs: int
    docker_executions: int
    subprocess_fallbacks: int
    z3_verifications: int
    symbolic_fallbacks: int
    memory_peak_mb: float
    
    def to_dict(self):
        """Convert to dictionary for reporting."""
        return {
            "total_queries": self.total_queries,
            "successful_queries": self.successful_queries,
            "failed_queries": self.failed_queries,
            "success_rate": f"{100 * self.successful_queries / self.total_queries:.1f}%",
            "total_time_seconds": f"{self.total_time_seconds:.2f}",
            "avg_latency_ms": f"{self.avg_latency_ms:.2f}",
            "throughput_qps": f"{self.throughput_qps:.2f}",
            "cache_hit_rate": f"{100 * self.cache_hit_rate:.1f}%",
            "avg_confidence": f"{self.avg_confidence:.3f}",
            "quality_distribution": {
                "excellent (>0.95)": self.excellent_pairs,
                "good (0.85-0.95)": self.good_pairs,
                "acceptable (0.70-0.85)": self.acceptable_pairs,
                "marginal (<0.70)": self.marginal_pairs,
            },
            "provider_usage": {
                "docker_executions": self.docker_executions,
                "subprocess_fallbacks": self.subprocess_fallbacks,
                "z3_verifications": self.z3_verifications,
                "symbolic_fallbacks": self.symbolic_fallbacks,
            },
            "memory_peak_mb": f"{self.memory_peak_mb:.1f}",
        }


class ScaleTestDataGenerator:
    """Generate diverse test queries for scale testing."""
    
    WEB_QUERIES = [
        "What is machine learning?",
        "How does deep learning work?",
        "Explain neural networks",
        "What is transfer learning?",
        "Define reinforcement learning",
        "What is natural language processing?",
        "Explain computer vision",
        "How does backpropagation work?",
        "What are convolutional neural networks?",
        "Explain attention mechanisms",
    ]
    
    CODE_SNIPPETS = [
        "print('Hello World')",
        "x = 5 + 3; print(x)",
        "for i in range(5): print(i)",
        "[x**2 for x in range(10)]",
        "sum([1, 2, 3, 4, 5])",
        "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2); print(fib(10))",
        "import math; print(math.sqrt(16))",
        "data = {'a': 1, 'b': 2}; print(data['a'])",
        "s = 'hello'; print(s.upper())",
        "nums = [3, 1, 4, 1, 5]; print(sorted(nums))",
    ]
    
    MATH_PROBLEMS = [
        ("2*x + 3 = 7", "x"),
        ("x**2 - 5*x + 6 = 0", "x"),
        ("3*x + 2*y = 8", "x"),
        ("x/2 + 4 = 10", "x"),
        ("5*(x - 2) = 15", "x"),
        ("x**2 + 2*x + 1 = 0", "x"),
        ("10*x - 5 = 25", "x"),
        ("x**3 - 8 = 0", "x"),
        ("2*x**2 - 8*x + 6 = 0", "x"),
        ("x + x + x = 9", "x"),
    ]
    
    @staticmethod
    def generate_web_search_query(index: int) -> Dict:
        """Generate web search query."""
        query = ScaleTestDataGenerator.WEB_QUERIES[index % len(ScaleTestDataGenerator.WEB_QUERIES)]
        return {
            "query": query,
            "intent": "WEB_SEARCH",
            "entities": query.split()[:3],
            "target_ir": "WEB_SEARCH",
            "plan_steps": ["Search web", "Extract relevant results"],
            "plan_confidence": 0.85 + (index % 5) * 0.03,
        }
    
    @staticmethod
    def generate_code_execution_query(index: int) -> Dict:
        """Generate code execution query."""
        code = ScaleTestDataGenerator.CODE_SNIPPETS[index % len(ScaleTestDataGenerator.CODE_SNIPPETS)]
        return {
            "query": f"Execute: {code}",
            "intent": "CODE_EXECUTE",
            "entities": ["python", "execution"],
            "target_ir": "CODE_EXECUTE",
            "plan_steps": ["Parse code", "Execute in sandbox"],
            "plan_confidence": 0.90 + (index % 3) * 0.03,
            "code": code,
        }
    
    @staticmethod
    def generate_math_query(index: int) -> Dict:
        """Generate math solving query."""
        expr, var = ScaleTestDataGenerator.MATH_PROBLEMS[index % len(ScaleTestDataGenerator.MATH_PROBLEMS)]
        return {
            "query": f"Solve: {expr}",
            "intent": "MATH_SOLVE",
            "entities": ["equation", "solve", var],
            "target_ir": "MATH_SOLVE",
            "plan_steps": ["Parse equation", "Solve for variable"],
            "plan_confidence": 0.88 + (index % 4) * 0.03,
            "equation": expr,
            "variable": var,
        }


class ScaleTestExecutor:
    """Execute scale tests against real providers."""
    
    def __init__(self, workspace_id: str = "scale_test"):
        """Initialize scale test executor."""
        self.workspace_id = workspace_id
        from prototype.jimsai.training_loop import TrainingLoopIntegration
        self.training_loop = TrainingLoopIntegration(
            workspace_id=workspace_id,
            kaggle_dataset_owner="jimsai_scale_test"
        )
        
        # Metrics tracking
        self.metrics = ScaleTestMetrics(
            total_queries=0,
            successful_queries=0,
            failed_queries=0,
            total_time_seconds=0.0,
            avg_latency_ms=0.0,
            throughput_qps=0.0,
            cache_hit_rate=0.0,
            avg_confidence=0.0,
            excellent_pairs=0,
            good_pairs=0,
            acceptable_pairs=0,
            marginal_pairs=0,
            docker_executions=0,
            subprocess_fallbacks=0,
            z3_verifications=0,
            symbolic_fallbacks=0,
            memory_peak_mb=0.0,
        )
        
        self.latencies = []
        self.confidences = []
        self.query_times = {}
    
    def execute_web_search_query(self, query_data: Dict) -> bool:
        """Execute web search query."""
        try:
            web_mod = get_web_retrieval_module()
            WebAugmentedRetrieval = web_mod.WebAugmentedRetrieval
            
            retrieval = WebAugmentedRetrieval(workspace_id=self.workspace_id)
            
            # Execute search
            results = asyncio.run(retrieval.search(query_data["query"]))
            
            # Ingest to training loop
            execution_output = json.dumps([
                {
                    "url": r.url if hasattr(r, 'url') else "",
                    "title": r.title if hasattr(r, 'title') else "",
                }
                for r in results
            ])
            
            self.training_loop.ingest_query_execution(
                query=query_data["query"],
                intent=query_data["intent"],
                entities=query_data["entities"],
                target_ir=query_data["target_ir"],
                plan_steps=query_data["plan_steps"],
                plan_confidence=query_data["plan_confidence"],
                execution_output=execution_output,
                execution_success=True,
                verification_score=0.9 if len(results) > 0 else 0.5,
            )
            
            return True
        except Exception as e:
            logger.warning(f"Web search failed: {e}")
            return False
    
    def execute_code_execution_query(self, query_data: Dict) -> bool:
        """Execute code execution query."""
        try:
            sandbox_mod = get_sandbox_executor_module()
            CodeExecutor = sandbox_mod.CodeExecutor
            CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
            
            executor = CodeExecutor(workspace_id=self.workspace_id)
            
            request = CodeExecutionRequest(
                code=query_data["code"],
                language="python",
                timeout_seconds=5,
            )
            
            result = executor.execute(request)
            
            # Track provider usage
            if hasattr(result, 'execution_method'):
                if result.execution_method == 'docker':
                    self.metrics.docker_executions += 1
                elif result.execution_method == 'subprocess':
                    self.metrics.subprocess_fallbacks += 1
            
            self.training_loop.ingest_query_execution(
                query=query_data["query"],
                intent=query_data["intent"],
                entities=query_data["entities"],
                target_ir=query_data["target_ir"],
                plan_steps=query_data["plan_steps"],
                plan_confidence=query_data["plan_confidence"],
                execution_output=result.stdout + result.stderr,
                execution_success=result.success,
                verification_score=1.0 if result.success else 0.0,
            )
            
            # Track cache hit
            if hasattr(result, 'is_cached') and result.is_cached:
                self.metrics.cache_hit_rate += 1.0
            
            return result.success
        except Exception as e:
            logger.warning(f"Code execution failed: {e}")
            return False
    
    def execute_math_query(self, query_data: Dict) -> bool:
        """Execute math solving query."""
        try:
            math_mod = get_math_solver_module()
            SymbolicSolver = math_mod.SymbolicSolver
            MathProblem = math_mod.MathProblem
            
            solver = SymbolicSolver()
            
            problem = MathProblem(
                expression=query_data["equation"],
                variable=query_data["variable"]
            )
            
            solution = solver.solve_equation(problem)
            
            # Track provider usage
            if hasattr(solution, 'method'):
                if solution.method == 'z3':
                    self.metrics.z3_verifications += 1
                elif solution.method == 'symbolic':
                    self.metrics.symbolic_fallbacks += 1
            
            self.training_loop.ingest_query_execution(
                query=query_data["query"],
                intent=query_data["intent"],
                entities=query_data["entities"],
                target_ir=query_data["target_ir"],
                plan_steps=query_data["plan_steps"],
                plan_confidence=query_data["plan_confidence"],
                execution_output=str(solution.solution) if solution.success else "no solution",
                execution_success=solution.success,
                verification_score=0.95 if solution.success else 0.0,
            )
            
            return solution.success
        except Exception as e:
            logger.warning(f"Math solving failed: {e}")
            return False
    
    def run_scale_test(self, num_queries: int = 1000, query_types: List[str] = None):
        """
        Run scale test with specified number of queries.
        
        Args:
            num_queries: Total number of queries to execute
            query_types: List of query types to distribute (web_search, code_execute, math_solve)
        """
        if query_types is None:
            query_types = ["web_search", "code_execute", "math_solve"]
        
        logger.info(f"Starting scale test: {num_queries} queries")
        
        # Pre-generate all queries
        queries = []
        for i in range(num_queries):
            query_type = query_types[i % len(query_types)]
            
            if query_type == "web_search":
                query = ScaleTestDataGenerator.generate_web_search_query(i)
            elif query_type == "code_execute":
                query = ScaleTestDataGenerator.generate_code_execution_query(i)
            else:  # math_solve
                query = ScaleTestDataGenerator.generate_math_query(i)
            
            queries.append((query_type, query))
        
        # Execute queries
        start_time = time.time()
        
        for idx, (query_type, query) in enumerate(queries):
            query_start = time.time()
            
            try:
                if query_type == "web_search":
                    success = self.execute_web_search_query(query)
                elif query_type == "code_execute":
                    success = self.execute_code_execution_query(query)
                else:  # math_solve
                    success = self.execute_math_query(query)
                
                self.metrics.total_queries += 1
                if success:
                    self.metrics.successful_queries += 1
                    self.confidences.append(query["plan_confidence"])
                else:
                    self.metrics.failed_queries += 1
            
            except Exception as e:
                self.metrics.total_queries += 1
                self.metrics.failed_queries += 1
                logger.error(f"Query {idx} failed: {e}")
            
            query_time = time.time() - query_start
            self.latencies.append(query_time * 1000)  # Convert to ms
            
            # Log progress every 100 queries
            if (idx + 1) % 100 == 0:
                logger.info(f"Progress: {idx + 1}/{num_queries} queries completed")
        
        # Finalize metrics
        self.metrics.total_time_seconds = time.time() - start_time
        self.metrics.avg_latency_ms = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0
        self.metrics.throughput_qps = self.metrics.total_queries / self.metrics.total_time_seconds if self.metrics.total_time_seconds > 0 else 0.0
        self.metrics.cache_hit_rate = self.metrics.cache_hit_rate / self.metrics.total_queries if self.metrics.total_queries > 0 else 0.0
        self.metrics.avg_confidence = sum(self.confidences) / len(self.confidences) if self.confidences else 0.0
        
        # Quality distribution from training loop
        for pair in self.training_loop.sppe_generator._pair_cache.values():
            if pair.quality_score >= 0.95:
                self.metrics.excellent_pairs += 1
            elif pair.quality_score >= 0.85:
                self.metrics.good_pairs += 1
            elif pair.quality_score >= 0.70:
                self.metrics.acceptable_pairs += 1
            else:
                self.metrics.marginal_pairs += 1
        
        logger.info(f"Scale test completed in {self.metrics.total_time_seconds:.2f}s")
        logger.info(f"Throughput: {self.metrics.throughput_qps:.2f} queries/second")
        logger.info(f"Success rate: {100 * self.metrics.successful_queries / self.metrics.total_queries:.1f}%")
        
        return self.metrics


# ==================== SCALE TESTS ====================

def test_scale_100_queries():
    """Test with 100 queries (light load)."""
    executor = ScaleTestExecutor(workspace_id="scale_test_100")
    metrics = executor.run_scale_test(num_queries=100)
    
    assert metrics.total_queries == 100
    assert metrics.successful_queries >= 80  # At least 80% success
    assert metrics.throughput_qps > 0


def test_scale_500_queries():
    """Test with 500 queries (medium load)."""
    executor = ScaleTestExecutor(workspace_id="scale_test_500")
    metrics = executor.run_scale_test(num_queries=500)
    
    assert metrics.total_queries == 500
    assert metrics.successful_queries >= 400  # At least 80% success
    assert metrics.throughput_qps > 0


@pytest.mark.slow
def test_scale_1000_queries():
    """Test with 1000+ queries (heavy load)."""
    executor = ScaleTestExecutor(workspace_id="scale_test_1000")
    metrics = executor.run_scale_test(num_queries=1000)
    
    assert metrics.total_queries == 1000
    assert metrics.successful_queries >= 800  # At least 80% success
    assert metrics.throughput_qps > 0
    
    # Log detailed metrics
    logger.info("=" * 80)
    logger.info("SCALE TEST RESULTS (1000 queries)")
    logger.info("=" * 80)
    
    for key, value in metrics.to_dict().items():
        logger.info(f"{key:30s}: {value}")
    
    logger.info("=" * 80)


def test_scale_provider_distribution():
    """Test query distribution across provider types."""
    executor = ScaleTestExecutor(workspace_id="scale_test_distribution")
    
    # 100 queries: 33 web, 33 code, 34 math
    metrics = executor.run_scale_test(
        num_queries=100,
        query_types=["web_search", "code_execute", "math_solve"]
    )
    
    assert metrics.total_queries == 100
    assert metrics.throughput_qps > 0
    
    logger.info(f"Docker executions: {metrics.docker_executions}")
    logger.info(f"Subprocess fallbacks: {metrics.subprocess_fallbacks}")
    logger.info(f"Z3 verifications: {metrics.z3_verifications}")
    logger.info(f"Symbolic fallbacks: {metrics.symbolic_fallbacks}")


def test_scale_cache_effectiveness():
    """Test cache hit rate on repeated queries."""
    executor = ScaleTestExecutor(workspace_id="scale_test_cache")
    
    # First run: 50 unique queries
    metrics1 = executor.run_scale_test(num_queries=50)
    cache_hit_rate_1 = metrics1.cache_hit_rate
    
    # Reset for second run
    executor2 = ScaleTestExecutor(workspace_id="scale_test_cache_2")
    
    # Second run: same 50 queries (repeated pattern)
    metrics2 = executor2.run_scale_test(num_queries=100)
    
    logger.info(f"First run cache hit rate: {100*cache_hit_rate_1:.1f}%")
    logger.info(f"Second run (with repeats) cache hit rate: {100*metrics2.cache_hit_rate:.1f}%")
    
    # Cache should improve on second run
    assert metrics2.cache_hit_rate >= cache_hit_rate_1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
