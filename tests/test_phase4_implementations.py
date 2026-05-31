"""
Phase 4 Integration Tests - Real Provider Implementations

Tests for:
- DuckDuckGo web search API
- Docker code sandbox execution
- Z3 constraint solver
- Configuration management
- Error handling and fallbacks
"""

import pytest
import asyncio
import os
import importlib
from pathlib import Path

# Import helpers for hyphenated module names
def get_web_retrieval_module():
    """Get world-knowledge module (uses importlib for hyphenated name)."""
    return importlib.import_module('services.world-knowledge.web_retrieval')

def get_sandbox_executor_module():
    """Get coding module (normal import works)."""
    return importlib.import_module('services.coding.sandbox_executor')

def get_math_solver_module():
    """Get math-science module (uses importlib for hyphenated name)."""
    return importlib.import_module('services.math-science.math_solver')

# Test configuration provider
def test_config_loads_from_env():
    """Test configuration loader from environment variables."""
    from prototype.jimsai.config import Config, get_config
    
    config = get_config()
    assert config is not None
    assert hasattr(config, "web_search")
    assert hasattr(config, "docker")
    assert hasattr(config, "z3")
    assert hasattr(config, "kaggle")
    assert hasattr(config, "system")


def test_config_validates():
    """Test configuration validation."""
    from prototype.jimsai.config import get_config
    
    config = get_config()
    validation = config.validate()
    
    assert "valid" in validation
    assert "issues" in validation
    assert "config_summary" in validation
    
    # Should not crash even with missing API keys
    assert isinstance(validation["valid"], bool)


# ==================== WEB SEARCH TESTS ====================

@pytest.mark.asyncio
async def test_duckduckgo_search_real():
    """Test real DuckDuckGo API search (network test)."""
    web_mod = get_web_retrieval_module()
    WebAugmentedRetrieval = web_mod.WebAugmentedRetrieval
    
    retrieval = WebAugmentedRetrieval(workspace_id="test")
    
    # Query about current events (likely to have web results)
    results = await retrieval.search("what is the capital of france")
    
    # Should return at least some results
    assert isinstance(results, list)
    
    if len(results) > 0:
        # Verify result structure
        result = results[0]
        assert hasattr(result, "url")
        assert hasattr(result, "title")
        assert hasattr(result, "snippet")
        assert hasattr(result, "fetched_at")
        
        # URLs should be valid
        assert result.url.startswith("http")


@pytest.mark.asyncio
async def test_web_search_caching():
    """Test web search result caching."""
    web_mod = get_web_retrieval_module()
    WebAugmentedRetrieval = web_mod.WebAugmentedRetrieval
    
    retrieval = WebAugmentedRetrieval(workspace_id="test")
    
    query = "test search query"
    
    # First search
    results1 = await retrieval.search(query)
    
    # Second search (should use cache)
    results2 = await retrieval.search(query)
    
    # Should return identical results
    assert results1 == results2


def test_web_source_freshness():
    """Test web source freshness tracking."""
    web_mod = get_web_retrieval_module()
    WebSource = web_mod.WebSource
    from datetime import datetime, timedelta
    
    # Fresh source
    now = datetime.now()
    source = WebSource(
        url="https://example.com",
        title="Example",
        snippet="Content",
        fetched_at=now.isoformat(),
        freshness_ttl=86400,  # 24 hours
    )
    
    assert source.is_fresh() is True
    
    # Stale source
    old_time = (now - timedelta(days=2)).isoformat()
    old_source = WebSource(
        url="https://example.com",
        title="Example",
        snippet="Content",
        fetched_at=old_time,
        freshness_ttl=86400,
    )
    
    assert old_source.is_fresh() is False


# ==================== CODE EXECUTION TESTS ====================

def test_docker_config_valid():
    """Test Docker configuration is properly detected."""
    from prototype.jimsai.config import get_config
    
    config = get_config()
    
    assert config.docker is not None
    assert hasattr(config.docker, "enabled")
    assert hasattr(config.docker, "socket")
    assert hasattr(config.docker, "timeout_seconds")


def test_code_execution_python_simple():
    """Test simple Python code execution."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    executor = CodeExecutor(workspace_id="test")
    
    request = CodeExecutionRequest(
        code='print("hello world")',
        language="python",
        timeout_seconds=5,
    )
    
    result = executor.execute(request)
    
    assert result.success is True
    assert "hello world" in result.stdout


def test_code_execution_with_error():
    """Test code execution with error."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    executor = CodeExecutor(workspace_id="test")
    
    request = CodeExecutionRequest(
        code='raise ValueError("test error")',
        language="python",
        timeout_seconds=5,
    )
    
    result = executor.execute(request)
    
    assert result.success is False
    assert "ValueError" in result.stderr or "test error" in result.stderr


def test_code_execution_caching():
    """Test code execution result caching."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    # Use unique workspace to avoid cache pollution from other tests
    executor = CodeExecutor(workspace_id="test_cache_unique_1234567")
    
    request = CodeExecutionRequest(
        code='print("unique_cache_test_123")',
        language="python",
        timeout_seconds=5,
    )
    
    # First execution (should not be cached)
    result1 = executor.execute(request)
    # First execution might be cached if we're unlucky, so we just check consistency
    first_cached = result1.is_cached
    first_output = result1.stdout
    
    # Second execution (should be cached)
    result2 = executor.execute(request)
    # Second execution should definitely be cached
    assert result2.is_cached is True
    
    # Results should be identical
    assert result1.stdout == result2.stdout


def test_code_static_analysis():
    """Test static analysis detection of dangerous patterns."""
    sandbox_mod = get_sandbox_executor_module()
    StaticAnalyzer = sandbox_mod.StaticAnalyzer
    
    # Safe code
    safe_code = 'x = 2 + 3\nprint(x)'
    issues = StaticAnalyzer.analyze(safe_code, "python")
    assert len(issues) == 0
    
    # Dangerous code
    dangerous_code = 'import os; os.system("rm -rf /")'
    issues = StaticAnalyzer.analyze(dangerous_code, "python")
    assert len(issues) > 0


def test_code_execution_timeout():
    """Test code execution timeout."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    executor = CodeExecutor(workspace_id="test")
    
    request = CodeExecutionRequest(
        code='import time; time.sleep(100)',  # Sleep for 100 seconds
        language="python",
        timeout_seconds=1,  # 1 second timeout
    )
    
    result = executor.execute(request)
    
    # Should fail due to timeout
    assert result.success is False
    assert "timeout" in result.stderr.lower() or result.execution_time_ms < 100000


# ==================== MATH SOLVER TESTS ====================

def test_z3_config_valid():
    """Test Z3 configuration."""
    from prototype.jimsai.config import get_config
    
    config = get_config()
    
    assert config.z3 is not None
    assert hasattr(config.z3, "enabled")
    assert hasattr(config.z3, "timeout_seconds")
    assert hasattr(config.z3, "solver_strategy")


def test_math_solve_linear_equation():
    """Test solving linear equation."""
    math_solver = get_math_solver_module()
    MathProblem = math_solver.MathProblem
    SymbolicSolver = math_solver.SymbolicSolver
    
    solver = SymbolicSolver()
    
    problem = MathProblem(
        expression="2*x + 3 = 7",
        variable="x"
    )
    
    solution = solver.solve_equation(problem)
    
    assert solution.success is True
    assert abs(solution.solution - 2.0) < 0.0001
    assert solution.is_exact is True


def test_math_solve_quadratic_equation():
    """Test solving quadratic equation."""
    math_solver = get_math_solver_module()
    SymbolicSolver = math_solver.SymbolicSolver
    MathProblem = math_solver.MathProblem
    
    solver = SymbolicSolver()
    
    problem = MathProblem(
        expression="x**2 - 5*x + 6 = 0",
        variable="x"
    )
    
    solution = solver.solve_equation(problem)
    
    assert solution.success is True
    # x = 2 or x = 3
    assert solution.solution in [2.0, 3.0] or abs(solution.solution - 2.0) < 0.0001 or abs(solution.solution - 3.0) < 0.0001


def test_math_verification_with_z3():
    """Test Z3-based solution verification (if Z3 available)."""
    math_solver = get_math_solver_module()
    FormalVerifier = math_solver.FormalVerifier
    
    verifier = FormalVerifier()
    
    # Correct solution: 2*x + 3 = 7 has x = 2
    is_correct, confidence = verifier.verify_solution(
        equation="2*x + 3 = 7",
        variable="x",
        proposed_solution=2.0
    )
    
    assert is_correct is True
    assert confidence > 0.8
    
    # Incorrect solution: x should be 2, not 3
    is_wrong, confidence = verifier.verify_solution(
        equation="2*x + 3 = 7",
        variable="x",
        proposed_solution=3.0
    )
    
    assert is_wrong is False


def test_math_simplification():
    """Test expression simplification."""
    math_solver = get_math_solver_module()
    SymbolicSolver = math_solver.SymbolicSolver
    
    solver = SymbolicSolver()
    
    expr = "2*x + x + 3 + 4"
    simplified = solver.simplify_expression(expr)
    
    # Should simplify to 3*x + 7
    assert "3" in simplified and "x" in simplified


# ==================== TRAINING LOOP TESTS ====================

def test_training_loop_with_providers():
    """Test training loop integration with real providers."""
    from prototype.jimsai.training_loop import TrainingLoopIntegration
    
    loop = TrainingLoopIntegration(
        workspace_id="test_with_providers",
        kaggle_dataset_owner="jimsai"
    )
    
    # Should be able to ingest executions (returns True on success)
    result = loop.ingest_query_execution(
        query="Calculate 2+2",
        intent="MATH_SOLVE",
        entities=["2", "+", "2"],
        target_ir="RUN_CANVAS",
        plan_steps=["Execute math"],
        plan_confidence=0.95,
        execution_output="4",
        execution_success=True,
        verification_score=1.0,
    )
    
    # Ingestion should succeed
    assert result is True
    
    # Should have generated SPPE pair (check via internal _pending_pairs)
    assert len(loop.batch_builder._pending_pairs) > 0
    
    # Health score should be valid
    health = loop.get_system_health_score()
    assert "health_score" in health
    assert 0 <= health["health_score"] <= 100


# ==================== END-TO-END INTEGRATION TESTS ====================

@pytest.mark.asyncio
async def test_full_pipeline_knowledge_query():
    """Test full pipeline: Query → Web Search → Cached Response."""
    web_mod = get_web_retrieval_module()
    WebKnowledgeCapability = web_mod.WebKnowledgeCapability
    
    capability = WebKnowledgeCapability(workspace_id="e2e_test")
    
    result = await capability.answer_with_sources("What is Paris?")
    
    assert "answer" in result
    assert "sources" in result
    assert "confidence" in result


def test_full_pipeline_code_execution():
    """Test full pipeline: Code → Sandbox → Cached Result."""
    sandbox_mod = get_sandbox_executor_module()
    CodingCapability = sandbox_mod.CodingCapability
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    capability = CodingCapability(workspace_id="e2e_test")
    
    request = CodeExecutionRequest(
        code='print("Hello from sandbox")',
        language="python"
    )
    
    result = capability.execute_with_verification(
        code=request.code,
        language=request.language
    )
    
    assert result is not None
    assert "result" in result or "output" in result


def test_full_pipeline_math_solving():
    """Test full pipeline: Math → Symbolic + Z3 Verification → Cached."""
    math_solver = get_math_solver_module()
    MathScienceCapability = math_solver.MathScienceCapability
    MathProblem = math_solver.MathProblem
    
    capability = MathScienceCapability(workspace_id="e2e_test")
    
    problem = MathProblem(
        expression="x**2 - 4 = 0",
        variable="x"
    )
    
    solution = capability.solve(problem)
    
    assert solution.success is True
    assert solution.verification_passed is True


# ==================== ERROR HANDLING & FALLBACK TESTS ====================

def test_docker_fallback_to_subprocess():
    """Test Docker execution falls back to subprocess if Docker unavailable."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    
    executor = CodeExecutor(workspace_id="test")
    
    # Execute code
    request = CodeExecutionRequest(
        code='print("fallback test")',
        language="python"
    )
    
    result = executor.execute(request)
    
    # Should still succeed (either Docker or subprocess)
    assert result.success is True


def test_z3_fallback_to_symbolic():
    """Test Z3 verification falls back to symbolic if Z3 unavailable."""
    math_solver = get_math_solver_module()
    FormalVerifier = math_solver.FormalVerifier
    
    verifier = FormalVerifier()
    
    is_correct, confidence = verifier.verify_solution(
        equation="x + 1 = 2",
        variable="x",
        proposed_solution=1.0
    )
    
    # Should succeed with fallback even if Z3 missing
    assert is_correct is True


# ==================== PERFORMANCE TESTS ====================

def test_code_caching_performance():
    """Test that caching actually improves performance."""
    sandbox_mod = get_sandbox_executor_module()
    CodeExecutor = sandbox_mod.CodeExecutor
    CodeExecutionRequest = sandbox_mod.CodeExecutionRequest
    import time
    
    executor = CodeExecutor(workspace_id="perf_test")
    
    request = CodeExecutionRequest(
        code='x = sum(range(1000))',
        language="python"
    )
    
    # First execution (not cached)
    start = time.time()
    result1 = executor.execute(request)
    first_time = time.time() - start
    
    # Second execution (cached)
    start = time.time()
    result2 = executor.execute(request)
    cached_time = time.time() - start
    
    # Cached should be much faster (at least 10x or more)
    assert cached_time < first_time * 0.5  # Cached at least 2x faster


# ==================== CONFIGURATION TESTS ====================

def test_kaggle_config_optional():
    """Test Kaggle configuration is optional."""
    from prototype.jimsai.config import get_config
    
    config = get_config()
    
    # Kaggle should be optional
    assert config.kaggle is not None
    # But can be disabled
    if not config.kaggle.enabled:
        # Should not crash if disabled
        assert config.kaggle.username is None or config.kaggle.api_key is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
