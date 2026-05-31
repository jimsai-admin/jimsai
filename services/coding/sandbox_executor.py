"""
Deterministic Code Sandbox: Safe, reproducible code execution with verification.

Provides:
- Docker-based sandboxing (no network access, resource limits)
- Result caching (avoid recomputing identical code)
- Test verification (run tests before returning results)
- Static analysis (catch obvious errors)
- Provenance tracking (inputs → hash → outputs)

This implements the coding capability for JimsAI v9.
"""

import hashlib
import json
import subprocess
import tempfile
import logging
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


@dataclass
class CodeExecutionRequest:
    """Request to execute code."""
    code: str
    language: str  # "python", "javascript", "bash"
    test_code: Optional[str] = None
    timeout_seconds: int = 30
    max_memory_mb: int = 512
    workspace_id: Optional[str] = None
    
    def compute_hash(self) -> str:
        """Compute reproducible hash of request."""
        content = f"{self.code}|{self.language}|{self.test_code or ''}"
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class CodeExecutionResult:
    """Result of code execution."""
    success: bool
    stdout: str
    stderr: str
    return_value: Optional[str] = None
    test_passed: bool = True
    test_output: str = ""
    execution_time_ms: float = 0.0
    result_hash: str = ""
    is_cached: bool = False
    static_analysis_issues: list[str] = None
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_value": self.return_value,
            "test_passed": self.test_passed,
            "test_output": self.test_output,
            "execution_time_ms": self.execution_time_ms,
            "result_hash": self.result_hash,
            "is_cached": self.is_cached,
            "static_analysis_issues": self.static_analysis_issues or [],
        }


class StaticAnalyzer:
    """Static analysis for code safety before execution."""
    
    DANGEROUS_PATTERNS = {
        "python": [
            "__import__",
            "eval(",
            "exec(",
            "compile(",
            "open(",
            "subprocess.",
            "os.system",
            "socket.",
            "sys.exit",
            "import os",
            "from os import",
            "import subprocess",
            "from subprocess import",
            "import socket",
            "from socket import",
            "pickle.loads",
            "pickle.load",
        ]
    }
    
    @staticmethod
    def analyze(code: str, language: str) -> list[str]:
        """
        Analyze code for dangerous patterns.
        
        Returns:
            List of issues found
        """
        issues = []
        
        patterns = StaticAnalyzer.DANGEROUS_PATTERNS.get(language, [])
        code_lower = code.lower()
        
        for pattern in patterns:
            if pattern.lower() in code_lower:
                issues.append(f"Potentially dangerous pattern detected: {pattern}")
        
        return issues


class CodeExecutor:
    """Execute code safely in isolated sandbox."""
    
    def __init__(self, workspace_id: str, cache_dir: Optional[str] = None):
        """
        Initialize code executor.
        
        Args:
            workspace_id: Workspace for scoped execution
            cache_dir: Directory for result caching (defaults to platform temp dir)
        """
        self.workspace_id = workspace_id
        
        # Use platform-appropriate temp directory
        if cache_dir is None:
            import tempfile
            cache_dir = os.path.join(tempfile.gettempdir(), "jims_code_cache")
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self._memory_cache: dict[str, CodeExecutionResult] = {}
    
    def execute(self, request: CodeExecutionRequest) -> CodeExecutionResult:
        """
        Execute code request in sandbox.
        
        Returns:
            CodeExecutionResult with output and metadata
        """
        import time
        start_time = time.time()
        
        # Compute request hash for caching
        request_hash = request.compute_hash()
        
        # Check memory cache first
        if request_hash in self._memory_cache:
            logger.info(f"Code execution cache hit: {request_hash[:8]}")
            cached = self._memory_cache[request_hash]
            cached.is_cached = True
            return cached
        
        # Check disk cache
        cache_file = self.cache_dir / f"{self.workspace_id}_{request_hash}.json"
        if cache_file.exists():
            logger.info(f"Code execution disk cache hit: {request_hash[:8]}")
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    result = CodeExecutionResult(**data)
                    result.is_cached = True
                    self._memory_cache[request_hash] = result
                    return result
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
        
        # Static analysis
        static_issues = StaticAnalyzer.analyze(request.code, request.language)
        if static_issues:
            logger.warning(f"Static analysis issues: {static_issues}")
        
        # Execute code
        result = self._execute_in_sandbox(request, static_issues)
        
        # Run tests if provided
        if request.test_code and result.success:
            result = self._run_tests(request, result)
        
        # Record execution time
        result.execution_time_ms = (time.time() - start_time) * 1000
        
        # Compute result hash (for retrieval of similar results)
        result.result_hash = hashlib.sha256(
            f"{request.code}|{result.stdout}".encode()
        ).hexdigest()
        
        # Cache result
        self._memory_cache[request_hash] = result
        try:
            with open(cache_file, "w") as f:
                json.dump(result.to_dict(), f)
        except Exception as e:
            logger.warning(f"Failed to write result cache: {e}")
        
        logger.info(f"Code execution completed: {request.language} (success={result.success})")
        return result
    
    def _execute_in_sandbox(
        self,
        request: CodeExecutionRequest,
        static_issues: list[str]
    ) -> CodeExecutionResult:
        """
        Execute code in isolated Docker container.
        
        Resource limits:
        - Memory: Limited to max_memory_mb
        - CPU: 1 core
        - Network: Disabled
        - Filesystem: Temporary only
        - Runtime: Limited to timeout_seconds
        
        Args:
            request: Code execution request
            static_issues: Issues found by static analysis
        
        Returns:
            CodeExecutionResult with stdout/stderr
        """
        try:
            # Try Docker first
            return self._execute_docker(request, static_issues)
        except Exception as docker_error:
            logger.warning(f"Docker execution failed: {docker_error}, falling back to subprocess")
            # Fall back to subprocess if Docker not available
            return self._execute_subprocess(request, static_issues)
    
    def _execute_docker(
        self,
        request: CodeExecutionRequest,
        static_issues: list[str]
    ) -> CodeExecutionResult:
        """Execute code in Docker container (production implementation)."""
        try:
            # Import docker conditionally
            try:
                import docker
                from docker.errors import ImageNotFound, ContainerError
            except ImportError:
                raise RuntimeError("Docker SDK not installed. Install with: pip install docker")
            
            # Import config
            from prototype.jimsai.config import get_config
            config = get_config()
            
            if not config.docker.enabled:
                raise RuntimeError("Docker execution disabled in configuration")
            
            # Connect to Docker daemon
            client = docker.from_env()
            
            # Select image based on language
            if request.language == "python":
                image = config.docker.image_python
                cmd = ["python", "-c", request.code]
            elif request.language == "javascript":
                image = config.docker.image_nodejs
                cmd = ["node", "-e", request.code]
            elif request.language == "bash":
                image = "alpine:latest"
                cmd = ["sh", "-c", request.code]
            else:
                raise ValueError(f"Unsupported language: {request.language}")
            
            # Prepare container configuration
            mem_limit = f"{request.max_memory_mb}m"
            
            logger.info(f"Executing {request.language} in Docker container {image}")
            
            # Run container with resource limits
            container = client.containers.run(
                image,
                cmd,
                detach=False,
                remove=True,
                mem_limit=mem_limit,
                memswap_limit=mem_limit,
                cpus=1,
                network_mode="none",  # Disable network
                timeout=request.timeout_seconds,
                stderr=True,
                stdout=True,
            )
            
            # Get output
            output = container.decode("utf-8") if isinstance(container, bytes) else container
            
            return CodeExecutionResult(
                success=True,
                stdout=output,
                stderr="",
                static_analysis_issues=static_issues,
                is_cached=False,
            )
        
        except ImportError as e:
            logger.error(f"Docker SDK not available: {e}")
            raise RuntimeError(str(e))
        except Exception as e:
            logger.error(f"Docker execution error: {e}")
            # Try to extract the error class name safely
            try:
                from docker.errors import ImageNotFound, ContainerError
                if isinstance(e, ImageNotFound):
                    logger.error(f"Docker image not found for language: {request.language}")
                    return CodeExecutionResult(
                        success=False,
                        stdout="",
                        stderr="Docker image not found. Run: docker pull <image>",
                        static_analysis_issues=static_issues,
                        is_cached=False,
                    )
                elif isinstance(e, ContainerError):
                    logger.error(f"Container execution failed: {e}")
                    return CodeExecutionResult(
                        success=False,
                        stdout=getattr(e, 'stdout', b'').decode("utf-8") if getattr(e, 'stdout', None) else "",
                        stderr=getattr(e, 'stderr', b'').decode("utf-8") if getattr(e, 'stderr', None) else str(e),
                        static_analysis_issues=static_issues,
                        is_cached=False,
                    )
            except:
                pass
            
            # Generic error
            raise
    
    def _execute_subprocess(
        self,
        request: CodeExecutionRequest,
        static_issues: list[str]
    ) -> CodeExecutionResult:
        """
        Execute code via subprocess (fallback when Docker unavailable).
        
        Less isolated than Docker but works without Docker daemon.
        """
        try:
            if request.language == "python":
                return self._execute_python(request.code, static_issues, request.timeout_seconds)
            elif request.language == "javascript":
                return self._execute_javascript(request.code, static_issues, request.timeout_seconds)
            elif request.language == "bash":
                return self._execute_bash(request.code, static_issues, request.timeout_seconds)
            else:
                return CodeExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Unsupported language: {request.language}",
                    static_analysis_issues=static_issues,
                )
        except Exception as e:
            logger.error(f"Subprocess execution error: {e}")
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                static_analysis_issues=static_issues,
            )
    
    def _execute_python(self, code: str, static_issues: list[str], timeout: int = 30) -> CodeExecutionResult:
        """Execute Python code via subprocess."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            os.unlink(temp_file)
            
            return CodeExecutionResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                static_analysis_issues=static_issues,
                is_cached=False,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Python execution timeout ({timeout}s)")
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timeout after {timeout} seconds",
                static_analysis_issues=static_issues,
            )
        except Exception as e:
            logger.error(f"Python execution error: {e}")
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                static_analysis_issues=static_issues,
            )
    
    def _execute_javascript(self, code: str, static_issues: list[str], timeout: int = 30) -> CodeExecutionResult:
        """Execute JavaScript code via subprocess (requires Node.js)."""
        try:
            result = subprocess.run(
                ["node", "-e", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            return CodeExecutionResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                static_analysis_issues=static_issues,
                is_cached=False,
            )
        except subprocess.TimeoutExpired:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timeout after {timeout} seconds",
                static_analysis_issues=static_issues,
            )
        except FileNotFoundError:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr="Node.js not found. Install Node.js or use Docker.",
                static_analysis_issues=static_issues,
            )
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                static_analysis_issues=static_issues,
            )
    
    def _execute_bash(self, code: str, static_issues: list[str], timeout: int = 30) -> CodeExecutionResult:
        """Execute bash code via subprocess."""
        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            return CodeExecutionResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
                static_analysis_issues=static_issues,
                is_cached=False,
            )
        except subprocess.TimeoutExpired:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timeout after {timeout} seconds",
                static_analysis_issues=static_issues,
            )
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                static_analysis_issues=static_issues,
            )
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr="Execution timeout (>30s)",
            )
        except Exception as e:
            return CodeExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
            )
    
    def _execute_javascript(self, code: str) -> CodeExecutionResult:
        """Execute JavaScript code (stub)."""
        return CodeExecutionResult(
            success=False,
            stdout="",
            stderr="JavaScript execution not yet implemented",
        )
    
    def _run_tests(
        self,
        request: CodeExecutionRequest,
        code_result: CodeExecutionResult
    ) -> CodeExecutionResult:
        """Run tests on successful code execution."""
        
        # Combine code + tests
        combined_code = f"{request.code}\n\n{request.test_code}"
        
        # Execute combined
        test_request = CodeExecutionRequest(
            code=combined_code,
            language=request.language,
            timeout_seconds=request.timeout_seconds,
        )
        
        # Temporarily disable cache for tests
        cache_hash = test_request.compute_hash()
        was_cached = cache_hash in self._memory_cache
        if was_cached:
            del self._memory_cache[cache_hash]
        
        test_result = self._execute_in_sandbox(test_request, [])
        
        code_result.test_passed = test_result.success
        code_result.test_output = test_result.stdout + test_result.stderr
        
        return code_result


class CodeVerification:
    """Verify code execution results for correctness."""
    
    @staticmethod
    def verify_output_signature(
        expected_output: str,
        actual_output: str
    ) -> tuple[bool, float]:
        """
        Verify actual output matches expected (with fuzzy matching).
        
        Returns:
            (is_correct, confidence)
        """
        # Exact match
        if expected_output == actual_output:
            return True, 1.0
        
        # Fuzzy match (lines match, ignoring whitespace)
        expected_lines = {line.strip() for line in expected_output.strip().split('\n')}
        actual_lines = {line.strip() for line in actual_output.strip().split('\n')}
        
        if expected_lines == actual_lines:
            return True, 0.95
        
        # Partial match
        matches = len(expected_lines & actual_lines)
        total = len(expected_lines | actual_lines)
        
        confidence = matches / total if total > 0 else 0.0
        return confidence > 0.80, confidence


class CodingCapability:
    """
    High-level coding capability using sandbox execution.
    
    Bridges L6 retrieval with real code execution for verification,
    testing, and interactive development.
    """
    
    def __init__(self, workspace_id: str):
        """Initialize coding capability."""
        self.workspace_id = workspace_id
        self.executor = CodeExecutor(workspace_id)
        self.verifier = CodeVerification()
    
    def execute_with_verification(
        self,
        code: str,
        language: str = "python",
        test_code: Optional[str] = None,
        expected_output: Optional[str] = None,
    ) -> dict:
        """
        Execute code with verification and caching.
        
        Returns:
            {
                "success": bool,
                "output": str,
                "test_passed": bool,
                "verified": bool,
                "confidence": float,
                "execution_time_ms": float,
                "is_cached": bool,
                "issues": list,
            }
        """
        request = CodeExecutionRequest(
            code=code,
            language=language,
            test_code=test_code,
            workspace_id=self.workspace_id,
        )
        
        result = self.executor.execute(request)
        
        # Verify if expected output provided
        verified = True
        confidence = 1.0
        if expected_output and result.success:
            verified, confidence = self.verifier.verify_output_signature(
                expected_output,
                result.stdout
            )
        
        return {
            "success": result.success,
            "output": result.stdout,
            "errors": result.stderr,
            "test_passed": result.test_passed,
            "test_output": result.test_output,
            "verified": verified,
            "confidence": confidence,
            "execution_time_ms": result.execution_time_ms,
            "is_cached": result.is_cached,
            "issues": result.static_analysis_issues or [],
        }


# Example usage
if __name__ == "__main__":
    capability = CodingCapability(workspace_id="test_workspace")
    
    # Test Python execution
    result = capability.execute_with_verification(
        code='print("Hello, World!")',
        language="python",
        test_code='assert "Hello" in open(__file__.replace(".py", "_test.py")).read()',
        expected_output="Hello, World!\n",
    )
    
    print("Code Execution Result:")
    print(f"  Success: {result['success']}")
    print(f"  Output: {result['output']}")
    print(f"  Verified: {result['verified']}")
    print(f"  Cached: {result['is_cached']}")
    print(f"  Execution time: {result['execution_time_ms']:.1f}ms")
