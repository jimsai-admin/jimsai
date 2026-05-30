from __future__ import annotations

import re
import subprocess
import tempfile
import textwrap
from pathlib import Path


BLOCKED_PATTERNS = (
    "import os",
    "from os",
    "import subprocess",
    "from subprocess",
    "import socket",
    "from socket",
    "import pathlib",
    "from pathlib",
    "open(",
    "__import__",
    "eval(",
    "exec(",
)


class DeterministicSandbox:
    def run_python(self, code: str, tests: str = "", timeout_ms: int = 1500) -> dict[str, object]:
        lowered = f"{code}\n{tests}".lower()
        if any(pattern in lowered for pattern in BLOCKED_PATTERNS):
            return {
                "status": "blocked",
                "stdout": "",
                "stderr": "blocked by deterministic sandbox policy",
                "exit_code": None,
            }
        source = textwrap.dedent(code).strip()
        test_source = textwrap.dedent(tests).strip()
        payload = source if not test_source else f"{source}\n\n{test_source}\n"
        with tempfile.TemporaryDirectory(prefix="jimsai_sandbox_") as tmp:
            script = Path(tmp) / "main.py"
            script.write_text(payload, encoding="utf-8")
            try:
                completed = subprocess.run(
                    ["python", "-I", str(script)],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    timeout=max(timeout_ms / 1000, 0.1),
                    shell=False,
                )
            except subprocess.TimeoutExpired as error:
                return {
                    "status": "timeout",
                    "stdout": error.stdout or "",
                    "stderr": error.stderr or "execution timed out",
                    "exit_code": None,
                }
        return {
            "status": "passed" if completed.returncode == 0 else "failed",
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "exit_code": completed.returncode,
        }


class SymbolicMathSolver:
    def solve(self, expression: str, solve_for: str | None = None) -> dict[str, str]:
        text = expression.strip()
        try:
            import sympy as sp
        except ModuleNotFoundError:
            return self._solve_without_sympy(text, solve_for)
        if "=" in text:
            left, right = text.split("=", 1)
            equation = sp.Eq(sp.sympify(left), sp.sympify(right))
            symbol = sp.Symbol(solve_for) if solve_for else next(iter(equation.free_symbols), None)
            if symbol is None:
                return {"status": "failed", "result": "no free symbol found", "method": "sympy_solve"}
            return {"status": "solved", "result": str(sp.solve(equation, symbol)), "method": "sympy_solve"}
        value = sp.simplify(sp.sympify(text))
        return {"status": "solved", "result": str(value), "method": "sympy_simplify"}

    def _solve_without_sympy(self, expression: str, solve_for: str | None = None) -> dict[str, str]:
        symbol = solve_for or "x"
        if "=" not in expression:
            if not re.fullmatch(r"[\d\s+\-*/().]+", expression):
                return {"status": "failed", "result": "sympy unavailable and expression contains unsupported tokens", "method": "linear_fallback"}
            try:
                value = eval(expression, {"__builtins__": {}}, {})  # noqa: S307 - regex-gated arithmetic only.
            except Exception:
                return {"status": "failed", "result": "sympy unavailable and expression is not a supported linear equation", "method": "linear_fallback"}
            return {"status": "solved", "result": str(value), "method": "linear_fallback"}

        allowed = re.fullmatch(rf"[\d\s+\-*/().{re.escape(symbol)}=]+", expression)
        if not allowed:
            return {"status": "failed", "result": "sympy unavailable and equation contains unsupported tokens", "method": "linear_fallback"}
        left, right = expression.split("=", 1)

        def evaluate(side: str, value: float) -> float:
            scoped = side.replace(symbol, f"({value})")
            return float(eval(scoped, {"__builtins__": {}}, {}))  # noqa: S307 - regex-gated arithmetic only.

        try:
            b = evaluate(left, 0.0) - evaluate(right, 0.0)
            a = (evaluate(left, 1.0) - evaluate(right, 1.0)) - b
            if abs(a) < 1e-12:
                return {"status": "failed", "result": "no linear solution found", "method": "linear_fallback"}
            root = -b / a
        except Exception:
            return {"status": "failed", "result": "sympy unavailable and fallback solve failed", "method": "linear_fallback"}
        result = int(root) if float(root).is_integer() else round(root, 8)
        return {"status": "solved", "result": f"[{result}]", "method": "linear_fallback"}
