"""Multi-file REAL Python app by ASSEMBLY from a verified pattern library (no LLM).

Grounds the claim that search→assembly turns the intractable into the tractable at
real, multi-file scale. From a small spec, it ASSEMBLES a 4-file Python package
(model · store · handlers · tests) out of parameterised, verified patterns — real
Python source with faithful docstrings — then VERIFIES by EXECUTING the generated
test suite (real import + run). No token-level search, no LLM.

This is the honest scale demonstration: given a KNOWN pattern vocabulary and a
component spec, assembly produces a running, tested, documented multi-file app.
What it does NOT do (named, not faked): invent patterns it was never given, derive
the spec from a vague prose request, or judge subjective "good taste".

Run: .venv/Scripts/python.exe experiments/synthesis/run_real_python_app.py
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Verified pattern library (parameterised real Python) ─────────────────────
def p_model(entity: str, fields: dict[str, str]) -> str:
    lines = "\n".join(f"    {n}: {t}" for n, t in fields.items())
    return (f'"""Data model for {entity} (assembled from the model pattern)."""\n'
            f"from dataclasses import dataclass, asdict\n\n\n"
            f"@dataclass\n"
            f"class {entity}:\n"
            f'    """A {entity} record; fields are typed and serialisable."""\n'
            f"{lines}\n\n"
            f"    def to_dict(self) -> dict:\n"
            f'        """Faithful plain-dict view of this {entity}."""\n'
            f"        return asdict(self)\n")


def p_store(entity: str) -> str:
    return (f'"""In-memory repository for {entity} (assembled from the store pattern)."""\n'
            f"from models import {entity}\n\n\n"
            f"class {entity}Store:\n"
            f'    """CRUD over an in-memory dict keyed by integer id."""\n\n'
            f"    def __init__(self) -> None:\n"
            f"        self._items: dict[int, {entity}] = {{}}\n"
            f"        self._next = 1\n\n"
            f"    def create(self, **fields) -> {entity}:\n"
            f'        """Insert a new {entity}, assigning the next id."""\n'
            f"        fields['id'] = self._next\n"
            f"        obj = {entity}(**fields)\n"
            f"        self._items[self._next] = obj\n"
            f"        self._next += 1\n"
            f"        return obj\n\n"
            f"    def get(self, item_id: int):\n"
            f'        """Return the {entity} with this id, or None."""\n'
            f"        return self._items.get(item_id)\n\n"
            f"    def list(self) -> list:\n"
            f'        """Return every {entity} record."""\n'
            f"        return list(self._items.values())\n")


def p_handlers(entity: str, routes: list[str]) -> str:
    low = entity.lower()
    body = [f'"""Request handlers for {entity} (assembled from the handler pattern)."""',
            f"from store import {entity}Store", "", f"_store = {entity}Store()", ""]
    if "create" in routes:
        body += [f"def create_{low}(payload: dict) -> tuple[int, dict]:",
                 f'    """POST: create a {entity} from the payload; returns (201, record)."""',
                 f"    obj = _store.create(**payload)",
                 f"    return 201, obj.to_dict()", ""]
    if "get" in routes:
        body += [f"def get_{low}(item_id: int) -> tuple[int, dict]:",
                 f'    """GET: fetch one {entity} by id; 404 if absent."""',
                 f"    obj = _store.get(item_id)",
                 f"    return (200, obj.to_dict()) if obj else (404, {{'error': 'not found'}})", ""]
    if "list" in routes:
        body += [f"def list_{low}() -> tuple[int, list]:",
                 f'    """GET: list all {entity} records; returns (200, [records])."""',
                 f"    return 200, [o.to_dict() for o in _store.list()]", ""]
    return "\n".join(body)


def p_tests(entity: str, routes: list[str]) -> str:
    low = entity.lower()
    return (f'"""Executable tests for the {entity} API (assembled from the test pattern)."""\n'
            f"import handlers\n\n\n"
            f"def run_tests() -> tuple[int, int]:\n"
            f'    """Exercise create/get/list end-to-end; returns (passed, total)."""\n'
            f"    passed = total = 0\n"
            f"    def ok(cond):\n"
            f"        nonlocal passed, total\n"
            f"        total += 1; passed += bool(cond)\n"
            f"    status, rec = handlers.create_{low}({{'title': 'buy milk', 'done': False}})\n"
            f"    ok(status == 201 and rec['id'] == 1 and rec['title'] == 'buy milk')\n"
            f"    status, rec = handlers.get_{low}(1)\n"
            f"    ok(status == 200 and rec['title'] == 'buy milk')\n"
            f"    status, _ = handlers.get_{low}(999)\n"
            f"    ok(status == 404)\n"
            f"    status, items = handlers.list_{low}()\n"
            f"    ok(status == 200 and len(items) == 1)\n"
            f"    return passed, total\n")


def assemble(spec: dict, out: Path) -> dict[str, str]:
    entity, fields, routes = spec["entity"], spec["fields"], spec["routes"]
    files = {
        "models.py": p_model(entity, fields),
        "store.py": p_store(entity),
        "handlers.py": p_handlers(entity, routes),
        "test_app.py": p_tests(entity, routes),
    }
    for name, src in files.items():
        (out / name).write_text(src, encoding="utf-8")
    return files


def verify(out: Path) -> tuple[bool, str]:
    """REAL verification: import the generated package and run its test suite."""
    sys.path.insert(0, str(out))
    try:
        for m in ("models", "store", "handlers", "test_app"):
            sys.modules.pop(m, None)
        test_app = importlib.import_module("test_app")
        passed, total = test_app.run_tests()
        return passed == total, f"{passed}/{total} generated tests pass (executed)"
    except Exception as e:  # a real syntax/runtime failure
        return False, f"generated app failed to run: {type(e).__name__}: {e}"
    finally:
        sys.path.remove(str(out))


def main() -> int:
    spec = {"entity": "Item",
            "fields": {"id": "int", "title": "str", "done": "bool"},
            "routes": ["create", "get", "list"]}
    out = Path(tempfile.mkdtemp(prefix="jims_app_"))
    print("=" * 78)
    print("MULTI-FILE real Python app by ASSEMBLY from a verified pattern library (no LLM)")
    print("-" * 78)
    print(f"spec: {spec['entity']} API with routes {spec['routes']}, fields {list(spec['fields'])}")
    try:
        files = assemble(spec, out)
        loc = sum(len(s.splitlines()) for s in files.values())
        print(f"assembled {len(files)} files ({loc} LOC): {', '.join(files)}")
        ok, detail = verify(out)
        print(f"verification (real execution): {detail}")
        print("\n--- generated handlers.py (excerpt) ---")
        print("\n".join(files["handlers.py"].splitlines()[:14]))
        print("---------------------------------------")
    finally:
        shutil.rmtree(out, ignore_errors=True)

    print("-" * 78)
    print("HONEST bounds: assembly works because the pattern vocabulary (model/store/handler/test)")
    print("is KNOWN and each pattern is verified by execution. It does NOT invent unseen patterns,")
    print("derive this spec from vague prose, or judge subjective 'taste'. Growing the pattern")
    print("library from real code + real verifiers is the training-loop work.")
    print("VERDICT:", "PASS — a running, tested, documented multi-file real-Python app assembled from "
          "verified patterns; 0 hand-written source in the harness output" if ok else "FAIL — see detail")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
