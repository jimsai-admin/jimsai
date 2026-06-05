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
        # Normalize: strip trailing bare "=" and inject explicit multiplication
        text = expression.strip().rstrip("=").strip()
        if not text:
            return {"status": "failed", "result": "empty expression", "method": "sympy_solve"}
        # Convert implicit multiplication: 3x → 3*x, x3 → x*3
        text = re.sub(r"(?<=\d)([a-zA-Z])", r"*\1", text)
        text = re.sub(r"([a-zA-Z])(?=\d)", r"\1*", text)
        try:
            import sympy as sp
            from sympy.parsing.sympy_parser import (
                parse_expr,
                standard_transformations,
                implicit_multiplication_application,
            )
            transformations = standard_transformations + (implicit_multiplication_application,)

            def safe_parse(s: str):
                return parse_expr(s.strip() or "0", transformations=transformations)

        except ModuleNotFoundError:
            return self._solve_without_sympy(text, solve_for)

        try:
            if "=" in text:
                left, right = text.split("=", 1)
                right = right.strip() or "0"  # bare LHS= → treat as LHS=0
                lhs = safe_parse(left)
                rhs = safe_parse(right)
                free = lhs.free_symbols | rhs.free_symbols
                if not free:
                    # No variables — evaluate LHS - RHS numerically
                    val = sp.simplify(lhs - rhs)
                    return {"status": "solved", "result": str(lhs), "method": "sympy_eval"}
                symbol = sp.Symbol(solve_for) if solve_for else sorted(free, key=str)[0]
                equation = sp.Eq(lhs, rhs)
                solutions = sp.solve(equation, symbol)
                return {"status": "solved", "result": str(solutions), "method": "sympy_solve"}
            else:
                value = sp.simplify(safe_parse(text))
                return {"status": "solved", "result": str(value), "method": "sympy_simplify"}
        except Exception:
            # sympy failed — fall back to the regex-based linear solver
            return self._solve_without_sympy(text, solve_for)

    def _solve_without_sympy(self, expression: str, solve_for: str | None = None) -> dict[str, str]:
        symbol = solve_for or "x"
        # Strip a trailing bare "=" that some expression extractors emit (e.g. "2+9=")
        text = expression.rstrip("=").strip()

        if "=" not in text:
            # Pure arithmetic — only digits, operators, parens, whitespace
            if not re.fullmatch(r"[\d\s+\-*/().]+", text):
                return {
                    "status": "failed",
                    "result": "sympy unavailable and expression contains unsupported tokens",
                    "method": "linear_fallback",
                }
            try:
                value = eval(text, {"__builtins__": {}}, {})  # noqa: S307 - regex-gated arithmetic only.
                return {"status": "solved", "result": str(value), "method": "linear_fallback"}
            except Exception:
                return {
                    "status": "failed",
                    "result": "sympy unavailable and expression is not a supported arithmetic expression",
                    "method": "linear_fallback",
                }

        # Equation — must match allowed characters
        allowed = re.fullmatch(rf"[\d\s+\-*/().{re.escape(symbol)}=]+", text)
        if not allowed:
            return {
                "status": "failed",
                "result": "sympy unavailable and equation contains unsupported tokens",
                "method": "linear_fallback",
            }
        left, right = text.split("=", 1)
        right = right.strip() or "0"  # bare LHS=RHS where RHS is empty → treat as LHS=0

        def evaluate(side: str, value: float) -> float:
            scoped = side.replace(symbol, f"({value})")
            return float(eval(scoped, {"__builtins__": {}}, {}))  # noqa: S307 - regex-gated arithmetic only.

        try:
            b = evaluate(left, 0.0) - evaluate(right, 0.0)
            a = (evaluate(left, 1.0) - evaluate(right, 1.0)) - b
            if abs(a) < 1e-12:
                # No variable — both sides are constants, evaluate LHS directly
                try:
                    value = eval(left.strip(), {"__builtins__": {}}, {})
                    return {"status": "solved", "result": str(value), "method": "linear_fallback"}
                except Exception:
                    return {"status": "failed", "result": "no linear solution found", "method": "linear_fallback"}
            root = -b / a
        except Exception:
            return {"status": "failed", "result": "sympy unavailable and fallback solve failed", "method": "linear_fallback"}
        result = int(root) if float(root).is_integer() else round(root, 8)
        return {"status": "solved", "result": f"[{result}]", "method": "linear_fallback"}
