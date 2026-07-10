"""Deterministic math-expression extraction — grammar, not generation.

Mathematical notation is a FORMAL LANGUAGE embedded in natural-language text:
digits, operators, parentheses, variables, and function application follow a
grammar that is identical in every human language. Extracting an expression is
therefore a parsing problem, not a language-understanding problem — no LLM,
no per-language patterns, no English keywords.

Method: NFKC-normalize (folds full-width ＋１２ etc. — Unicode data, not ours),
tokenize into math atoms vs other text, take maximal contiguous runs of math
atoms, trim to balanced parentheses, and keep the best-scoring well-formed run
(must contain an operator and an operand — a bare number in prose is not an
expression). A run containing '=' with exactly one variable becomes an
equation with that variable as solve target.

What counts as a math atom is positional grammar, not vocabulary:
  - numbers (ints/decimals)
  - operators + - * / ^ = and parentheses (× ÷ − fold to * / -)
  - short identifiers (<= 2 chars) adjacent to an operator/paren — variables
  - identifiers immediately followed by '(' — function application (sympy
    resolves whether it knows the function; we never list function names)

Outside this grammar the extractor returns nothing and the caller records a
gap (Independence Policy) — it never guesses.
"""

from __future__ import annotations

import re
import unicodedata

_OP_FOLD = str.maketrans({"×": "*", "÷": "/", "−": "-", "–": "-", "＝": "=", "^": "^"})
_TOKEN = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<op>[+\-*/^=])"
    r"|(?P<paren>[()])"
    r"|(?P<word>[A-Za-z_]\w*)"
    r"|(?P<other>\S)"
)


def _tokens(text: str) -> list[tuple[str, str, int, int]]:
    text = unicodedata.normalize("NFKC", text).translate(_OP_FOLD)
    return [(m.lastgroup, m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)], text


_FORMULA = re.compile(r"(?:[A-Z][a-z]?\d*)+")


def _is_chemical_formula(value: str, elements: frozenset[str]) -> bool:
    """A token is a chemical formula iff it decomposes as (ElementSymbol,
    optional count)+ with every symbol present in the element table, and
    carries at least one digit (so bare element-symbol words like 'In' or
    'No' in prose are not claimed). Lookup against data — the periodic table
    lives with the solver, never as a list here."""
    if not elements or not any(ch.isdigit() for ch in value):
        return False
    if not _FORMULA.fullmatch(value):
        return False
    return all(symbol in elements for symbol in re.findall(r"[A-Z][a-z]?", value))


def _is_math_atom(kind: str, value: str, neighbors: tuple[str | None, str | None],
                  next_char: str, known_symbols: frozenset[str],
                  elements: frozenset[str]) -> bool:
    if kind in ("num", "op", "paren"):
        return True
    if kind == "word":
        if next_char == "(":            # function application: name '(' — grammar position
            return len(value) <= 8
        # Known-symbol admission (the projection principle): identifiers that
        # exist in the solver's GROWING namespaces — physics constants (k_B,
        # N_A, ...), engineering symbols, chemical formulas over the element
        # table — are formal vocabulary by DATA lookup, whatever their length.
        # The namespaces live with the solver (ultimately sourced from
        # CODATA / the periodic table), never as lists in this file.
        if value in known_symbols:
            return any(n in ("op", "paren") for n in neighbors if n)
        if any(ch.isdigit() for ch in value) and _is_chemical_formula(value, elements):
            return True
        # Variable-like identifiers are admitted by GRAMMAR POSITION only:
        # adjacent to an operator/equals/paren ("2*x", "x =", "(y"). A short
        # English word floating in prose ("is 33") has no operator contact
        # and is text, not algebra.
        return len(value) <= 2 and any(n in ("op", "paren") for n in neighbors if n)
    return False


def extract_expression(text: str, known_symbols: frozenset[str] = frozenset(),
                       elements: frozenset[str] = frozenset()) -> tuple[str, str | None]:
    """Return (expression, solve_for) or ("", None) if no well-formed math
    span exists. Deterministic, language-independent, LLM-free.

    known_symbols / elements are the solver's growing namespaces (physics
    constants, engineering symbols, the periodic table) — admission of long
    identifiers is a data lookup, extending the same grammar to physics,
    chemistry, and engineering notation with zero per-domain code."""
    token_list, folded = _tokens(text)
    runs: list[list[tuple[str, str, int, int]]] = []
    current: list[tuple[str, str, int, int]] = []
    prev_kind: str | None = None
    for i, (kind, value, start, end) in enumerate(token_list):
        next_char = folded[end] if end < len(folded) else ""
        neighbors = (
            token_list[i - 1][0] if i > 0 else None,
            token_list[i + 1][0] if i + 1 < len(token_list) else None,
        )
        if _is_math_atom(kind, value, neighbors, next_char, known_symbols, elements):
            current.append((kind, value, start, end))
        else:
            if current:
                runs.append(current)
            current = []
        prev_kind = kind
    if current:
        runs.append(current)

    best: tuple[float, str, str | None, list] | None = None
    for run in runs:
        expr, solve_for = _normalize_run(run)
        if not expr:
            continue
        score = sum(1 for kind, _v, _s, _e in run if kind in ("num", "op"))
        if best is None or score > best[0]:
            best = (score, expr, solve_for, run)
    if not best:
        return "", None
    _score, expr, solve_for, run = best

    # Solve-TARGET detection for expression-heavy science/engineering problems
    # ("solve F = m*a for a", "express t in terms of v, u, a", "rearrange
    # E = m*c^2 for m"). The answer is an EXPRESSION, not a number, and the
    # target is whichever equation symbol ALSO appears in the query OUTSIDE the
    # equation span — a repeated variable, no "for"/"pour"/"solve" keyword, so
    # it is language-independent. If several qualify, take the earliest mention.
    if "=" in expr and solve_for is None:
        run_start, run_end = run[0][2], run[-1][3]
        eq_syms = {v for k, v, _s, _e in run if k == "word"}
        outside = sorted(
            (s, v) for (k, v, s, e) in token_list
            if k == "word" and v in eq_syms and (e <= run_start or s >= run_end)
        )
        if outside:
            solve_for = outside[0][1]
    return expr, solve_for


def _normalize_run(run: list[tuple[str, str, int, int]]) -> tuple[str, str | None]:
    # Trim leading/trailing operators (except a leading unary minus) and
    # unbalanced parens; require >= 1 operator/equals and >= 2 operands OR an
    # equation — a lone number inside prose is not an expression.
    tokens = list(run)
    while tokens and tokens[0][0] == "op" and tokens[0][1] != "-":
        tokens.pop(0)
    while tokens and tokens[-1][0] == "op":
        tokens.pop()
    # balance parens by trimming from the offending side
    while tokens:
        depth = 0
        bad = False
        for kind, value, _s, _e in tokens:
            if value == "(":
                depth += 1
            elif value == ")":
                depth -= 1
                if depth < 0:
                    bad = True
                    break
        if bad:
            tokens = tokens[1:] if tokens[0][1] == ")" else tokens[:-1]
            continue
        if depth > 0:
            tokens = tokens[1:] if tokens[0][1] == "(" else tokens[:-1]
            continue
        break
    if not tokens:
        return "", None

    kinds = [k for k, _v, _s, _e in tokens]
    values = [v for _k, v, _s, _e in tokens]
    n_ops = sum(1 for k, v in zip(kinds, values) if k == "op" and v != "=")
    n_eq = values.count("=")
    n_operands = sum(1 for k in kinds if k in ("num", "word"))
    if n_eq == 0 and (n_ops < 1 or n_operands < 2):
        return "", None
    if n_eq > 1:
        return "", None

    variables = sorted({v for k, v in zip(kinds, values) if k == "word"
                        and not (values.index(v) + 1 < len(values))} |
                       {v for i, (k, v) in enumerate(zip(kinds, values))
                        if k == "word" and not (i + 1 < len(values) and values[i + 1] == "(")})
    solve_for = variables[0] if n_eq == 1 and len(variables) == 1 else None
    if n_eq == 1 and not variables:
        return "", None  # "1 + 1 = 3" style statements are claims, not solve requests

    expr = ""
    for i, (kind, value, start, _e) in enumerate(tokens):
        if i and kind in ("num", "word") and tokens[i - 1][0] in ("num", "word"):
            # Implicit multiplication: a coefficient stuck to a variable ("2x",
            # "3y") — a NUMBER immediately followed (no space) by a short
            # identifier. Universal math notation, language-independent; insert
            # the '*'. Genuine prose ("Fagur 20", spaced or word→word) is still
            # rejected as not-an-expression.
            adjacent = tokens[i - 1][3] == start
            if adjacent and tokens[i - 1][0] == "num" and kind == "word":
                expr += "*"
            else:
                return "", None
        expr += "**" if value == "^" else value  # sympy reads ^ as XOR
    return expr, solve_for
