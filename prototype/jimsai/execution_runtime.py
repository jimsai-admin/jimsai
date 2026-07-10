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
    # Physics/chemistry constants available in expressions
    _PHYSICS_NAMESPACE: dict = {
        "g": 9.80665,    # gravitational acceleration m/s²
        "c": 299792458,  # speed of light m/s
        "h": 6.62607015e-34,  # Planck constant J·s
        "k_B": 1.380649e-23,  # Boltzmann constant J/K
        "R": 8.314462618,  # gas constant J/(mol·K)
        "N_A": 6.02214076e23,  # Avogadro constant mol⁻¹
        "e": 1.602176634e-19,  # elementary charge C
        "pi": 3.14159265358979,
    }

    # Molar masses of common elements (g/mol)
    _ELEMENT_MASSES: dict = {
        "H": 1.008, "He": 4.003, "Li": 6.941, "Be": 9.012, "B": 10.811,
        "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
        "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.086, "P": 30.974,
        "S": 32.065, "Cl": 35.453, "K": 39.098, "Ca": 40.078, "Fe": 55.845,
        "Cu": 63.546, "Zn": 65.38, "Br": 79.904, "Ag": 107.868, "I": 126.904,
        "Au": 196.967, "Pb": 207.2,
    }

    def solve(self, expression: str, solve_for: str | None = None, show_steps: bool = True) -> dict:
        """Solve a mathematical expression and return result with step-by-step breakdown.

        Returns:
            {
                "status": "solved" | "failed",
                "result": str,
                "method": str,
                "steps": list[str],  # empty list when show_steps=False or steps unavailable
            }
        """
        text = expression.strip().rstrip("=").strip()
        if not text:
            return {"status": "failed", "result": "empty expression", "method": "sympy_solve", "steps": []}

        # ── Molar mass query ────────────────────────────────────────────────
        molar_match = re.match(r"(?:molar\s+mass\s+of\s+|molar\s+mass\s*:?\s*)([A-Za-z0-9]+)", text, re.IGNORECASE)
        if molar_match:
            return self._compute_molar_mass(molar_match.group(1))

        # Normalize implicit multiplication before anything else
        text = re.sub(r"(?<=\d)([a-zA-Z])", r"*\1", text)
        text = re.sub(r"([a-zA-Z])(?=\d)", r"\1*", text)

        try:
            import sympy as sp
            from sympy.parsing.sympy_parser import (
                parse_expr, standard_transformations, implicit_multiplication_application,
            )
            transformations = standard_transformations + (implicit_multiplication_application,)

            def safe_parse(s: str):
                # Inject physics constants into namespace
                return parse_expr(s.strip() or "0", transformations=transformations,
                                  local_dict={k: sp.Float(v) for k, v in self._PHYSICS_NAMESPACE.items()})

        except ModuleNotFoundError:
            return self._solve_without_sympy(text, solve_for)

        # ── Direct sympy function call (from T1 bridge extraction) ───────────
        # The bridge returns expressions like diff(x**3, x) or integrate(sin(x), x)
        # that can be evaluated directly by sympy without keyword detection.
        if text.startswith("diff(") or text.startswith("Derivative("):
            return self._solve_calculus(text, "diff", safe_parse)
        if text.startswith("integrate(") or text.startswith("Integral("):
            return self._solve_calculus(text, "integrate", safe_parse)
        if text.startswith("limit(") or text.startswith("Limit("):
            try:
                result = eval(text, {"__builtins__": {}},
                              {k: getattr(sp, k) for k in dir(sp) if not k.startswith("_")})
                return {"status": "solved", "result": str(result), "method": "sympy_eval", "steps": [f"{text} = {result}"]}
            except Exception as exc:
                return {"status": "failed", "result": str(exc), "method": "sympy_eval", "steps": []}

        # ── Calculus: derivatives ────────────────────────────────────────────
        calc_kws = ("derivative", "differentiate", "d/dx", "d/dy", "d/dz", "∂", "diff(")
        if any(kw in text.lower() for kw in calc_kws):
            return self._solve_calculus(text, "diff", safe_parse)

        # ── Calculus: integrals ──────────────────────────────────────────────
        int_kws = ("integrate", "integral", "∫", "antiderivative")
        if any(kw in text.lower() for kw in int_kws):
            return self._solve_calculus(text, "integrate", safe_parse)

        # ── System of equations: comma or newline separated ──────────────────
        equations = [e.strip() for e in re.split(r"[,\n;]", text) if "=" in e.strip()]
        if len(equations) >= 2:
            return self._solve_system(equations, safe_parse)

        try:
            if "=" in text:
                left, right = text.split("=", 1)
                right = right.strip() or "0"
                lhs = safe_parse(left)
                rhs = safe_parse(right)
                free = lhs.free_symbols | rhs.free_symbols
                if not free:
                    # Pure evaluation: the equation itself is the whole working.
                    return {"status": "solved", "result": str(sp.simplify(lhs)), "method": "sympy_eval", "steps": []}
                symbol = sp.Symbol(solve_for) if solve_for else sorted(free, key=str)[0]
                equation = sp.Eq(lhs, rhs)
                solutions = sp.solve(equation, symbol)
                # Steps are LANGUAGE-NEUTRAL NOTATION only — the algebraic working,
                # no English labels ("Solving for …"), so a detailed answer reads
                # correctly in every language. Show: original equation, an
                # isolation step for linear cases, then each solution.
                steps: list[str] = []
                if show_steps:
                    steps.append(f"{left.strip()} = {right.strip()}")
                    try:
                        poly = sp.Poly(sp.simplify(lhs - rhs), symbol)
                        if poly.degree() == 1:
                            a, b = poly.all_coeffs()  # a·symbol + b
                            if b != 0:
                                steps.append(f"{sp.nsimplify(a)}*{symbol} = {sp.nsimplify(-b)}")
                    except Exception:
                        pass
                    for sol in solutions:
                        steps.append(f"{symbol} = {sp.nsimplify(sol)}")
                return {"status": "solved", "result": str(solutions), "method": "sympy_solve", "steps": steps}
            else:
                expr = safe_parse(text)
                value = sp.simplify(expr)
                steps = []
                if show_steps:
                    steps = [f"Expression: {text}", f"Simplified: {value}"]
                    # Show numeric approximation if symbolic result is complex
                    try:
                        approx = float(value.evalf())
                        if str(approx) != str(value):
                            steps.append(f"Numeric approximation: ≈ {round(approx, 6)}")
                    except Exception:
                        pass
                return {"status": "solved", "result": str(value), "method": "sympy_simplify", "steps": steps}
        except Exception:
            return self._solve_without_sympy(text, solve_for)

    def _solve_calculus(self, text: str, operation: str, safe_parse) -> dict:
        """Handle derivative and integral computation."""
        import sympy as sp

        # Extract expression — strip operation keywords
        clean = re.sub(
            r"(?:derivative\s+of|differentiate|d/d[xyz]|∂|diff\(|integrate|integral\s+of|∫|antiderivative\s+of)\s*",
            "", text, flags=re.IGNORECASE
        ).strip().strip("()").strip()

        # Determine variable (default x)
        var_match = re.search(r"with\s+respect\s+to\s+([a-zA-Z])", text, re.IGNORECASE)
        var_name = var_match.group(1) if var_match else "x"
        # Remove "with respect to X" from expression
        if var_match:
            clean = clean[:var_match.start()].strip()

        var = sp.Symbol(var_name)
        try:
            expr = safe_parse(clean.replace(var_name, str(var)))
            if operation == "diff":
                result = sp.diff(expr, var)
                steps = [
                    f"Expression: {clean}",
                    f"Differentiate with respect to {var_name}",
                    f"d/d{var_name}({expr}) = {result}",
                ]
                # Show simplified form if different
                simplified = sp.simplify(result)
                if simplified != result:
                    steps.append(f"Simplified: {simplified}")
                return {"status": "solved", "result": str(result), "method": "sympy_diff", "steps": steps}
            else:
                result = sp.integrate(expr, var)
                steps = [
                    f"Expression: {clean}",
                    f"Integrate with respect to {var_name}",
                    f"∫{expr} d{var_name} = {result} + C",
                ]
                return {"status": "solved", "result": f"{result} + C", "method": "sympy_integrate", "steps": steps}
        except Exception as exc:
            return {"status": "failed", "result": str(exc), "method": f"sympy_{operation}", "steps": []}

    def _solve_system(self, equations: list[str], safe_parse) -> dict:
        """Solve a system of equations."""
        import sympy as sp

        sym_names = set()
        eq_objs = []
        try:
            for eq_text in equations:
                left, right = eq_text.split("=", 1)
                lhs = safe_parse(left)
                rhs = safe_parse(right.strip() or "0")
                eq_objs.append(sp.Eq(lhs, rhs))
                for s in (lhs.free_symbols | rhs.free_symbols):
                    sym_names.add(str(s))
            syms = [sp.Symbol(n) for n in sorted(sym_names)]
            solutions = sp.solve(eq_objs, syms)
            # Language-neutral notation: the equations, then the solution set.
            steps = [eq.strip() for eq in equations]
            if isinstance(solutions, dict):
                steps.extend(f"{k} = {v}" for k, v in solutions.items())
            else:
                steps.append(str(solutions))
            return {"status": "solved", "result": str(solutions), "method": "sympy_system", "steps": steps}
        except Exception as exc:
            return {"status": "failed", "result": str(exc), "method": "sympy_system", "steps": []}

    def _compute_molar_mass(self, formula: str) -> dict:
        """Compute molar mass from a chemical formula like H2O, NaCl, C6H12O6."""
        tokens = re.findall(r"([A-Z][a-z]?)(\d*)", formula)
        total = 0.0
        steps = [f"Chemical formula: {formula}"]
        for element, count_str in tokens:
            if not element:
                continue
            count = int(count_str) if count_str else 1
            mass = self._ELEMENT_MASSES.get(element)
            if mass is None:
                return {"status": "failed", "result": f"Unknown element: {element}", "method": "molar_mass", "steps": steps}
            contribution = mass * count
            total += contribution
            steps.append(f"{element}×{count}: {mass} × {count} = {contribution:.3f} g/mol")
        steps.append(f"Total molar mass: {total:.3f} g/mol")
        return {"status": "solved", "result": f"{round(total, 3)} g/mol", "method": "molar_mass", "steps": steps}

    def _solve_without_sympy(self, expression: str, solve_for: str | None = None) -> dict:
        symbol = solve_for or "x"
        text = expression.rstrip("=").strip()

        if "=" not in text:
            if not re.fullmatch(r"[\d\s+\-*/().]+", text):
                return {"status": "failed", "result": "sympy unavailable and expression contains unsupported tokens", "method": "linear_fallback", "steps": []}
            try:
                value = eval(text, {"__builtins__": {}}, {})  # noqa: S307
                return {"status": "solved", "result": str(value), "method": "linear_fallback", "steps": [f"Arithmetic: {text} = {value}"]}
            except Exception:
                return {"status": "failed", "result": "sympy unavailable and expression is not a supported arithmetic expression", "method": "linear_fallback", "steps": []}

        allowed = re.fullmatch(rf"[\d\s+\-*/().{re.escape(symbol)}=]+", text)
        if not allowed:
            return {"status": "failed", "result": "sympy unavailable and equation contains unsupported tokens", "method": "linear_fallback", "steps": []}
        left, right = text.split("=", 1)
        right = right.strip() or "0"

        def evaluate(side: str, value: float) -> float:
            scoped = side.replace(symbol, f"({value})")
            return float(eval(scoped, {"__builtins__": {}}, {}))  # noqa: S307

        try:
            b = evaluate(left, 0.0) - evaluate(right, 0.0)
            a = (evaluate(left, 1.0) - evaluate(right, 1.0)) - b
            if abs(a) < 1e-12:
                try:
                    value = eval(left.strip(), {"__builtins__": {}}, {})
                    return {"status": "solved", "result": str(value), "method": "linear_fallback", "steps": []}
                except Exception:
                    return {"status": "failed", "result": "no linear solution found", "method": "linear_fallback", "steps": []}
            root = -b / a
        except Exception:
            return {"status": "failed", "result": "sympy unavailable and fallback solve failed", "method": "linear_fallback", "steps": []}
        result = int(root) if float(root).is_integer() else round(root, 8)
        return {
            "status": "solved",
            "result": f"[{result}]",
            "method": "linear_fallback",
            "steps": [f"Linear equation: {left.strip()} = {right.strip()}", f"{symbol} = {result}"],
        }
