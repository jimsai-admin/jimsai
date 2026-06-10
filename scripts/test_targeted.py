"""
JimsAI Targeted Regression Tests
==================================
Tests only the three areas known to be broken:
  1. T2/Qwen code generation   — any language, not Python-specific
  2. Memory ingestion + recall — "my name is X" then "what is my name?"
  3. Web search                — world_knowledge route returns real content

Usage:
    python scripts/test_targeted.py [--base-url http://127.0.0.1:8001]

Pass = test behaves as expected.  Fail = something still broken.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:
    import httpx
except ImportError:
    print("httpx not found. pip install httpx")
    sys.exit(1)

# ── Test cases ────────────────────────────────────────────────────────────────

TESTS = [

    # ── 1. CODING: T2/Qwen generates real code (not planner labels) ──────────
    # Language inferred from the prompt — no hardcoding.
    {
        "id": "code_python",
        "group": "coding",
        "prompt": "Write a Python function that reverses a string.",
        "expect": {
            "cap": "coding",
            "response_contains_any": ["def ", "return", "[::-1]", "reverse"],
            "response_not_contains": ["compile_ir", "retrieve_signatures", "assemble_code"],
            "min_confidence": 0.50,
        },
        "note": "T2 Qwen must produce real Python, not planner step labels",
    },
    {
        "id": "code_javascript",
        "group": "coding",
        "prompt": "Write a JavaScript function that checks if a string is a palindrome.",
        "expect": {
            "cap": "coding",
            "response_contains_any": ["function", "return", "reverse", "===", "split"],
            "response_not_contains": ["compile_ir", "retrieve_signatures"],
            "min_confidence": 0.50,
        },
        "note": "T2 Qwen must infer JS from the prompt — no language hardcoding",
    },
    {
        "id": "code_sql",
        "group": "coding",
        "prompt": (
            "Write a SQL query to find the top 5 customers by total order value "
            "from tables: orders(order_id, customer_id, total_amount) and "
            "customers(customer_id, name)."
        ),
        "expect": {
            "cap": "coding",
            "response_contains_any": ["SELECT", "JOIN", "ORDER BY", "LIMIT", "SUM"],
            "response_not_contains": ["compile_ir", "retrieve_signatures"],
            "min_confidence": 0.50,
        },
        "note": "T2 Qwen must infer SQL from the prompt",
    },

    # ── 2. MEMORY: profile ingestion + recall ─────────────────────────────────
    {
        "id": "memory_write",
        "group": "memory",
        "prompt": "My name is TestUser99. Please remember that.",
        "expect": {
            "ir_not": "EMOTIONAL_CATCH",
            "response_contains_any": ["TestUser99", "remember", "noted", "got it", "name"],
            "min_confidence": 0.50,
        },
        "note": "Profile write must NOT route to EMOTIONAL_CATCH",
    },
    {
        "id": "memory_recall",
        "group": "memory",
        "prompt": "What is my name?",
        "expect": {
            "response_contains_any": ["TestUser99"],
            "min_confidence": 0.50,
        },
        "note": "Must recall the name written in memory_write (run after it in same thread)",
        "depends_on": "memory_write",
    },

    # ── 3. WEB: world_knowledge returns real content ──────────────────────────
    {
        "id": "web_python_version",
        "group": "web",
        "prompt": "What is the latest stable version of Python?",
        "expect": {
            "cap": "world_knowledge",
            "response_contains_any": ["3.", "Python", "release", "version"],
            "response_not_contains": ["compile_ir"],
            "max_gaps": 1,
        },
        "note": "Web search must return real Python version info from DDG",
    },
    {
        "id": "web_factual",
        "group": "web",
        "prompt": "What is the capital city of France?",
        "expect": {
            "response_contains_any": ["Paris"],
            "max_gaps": 1,
        },
        "note": "Simple factual web lookup — should find Paris",
    },

    # ── 4. QWEN T2 STATUS: verify Qwen is actually being called ──────────────
    {
        "id": "qwen_t2_active",
        "group": "qwen",
        "prompt": "Explain in one sentence what compound interest is.",
        "expect": {
            "used_local_model": True,
            "response_not_contains": ["compile_ir"],
        },
        "note": "used_local_model=True in layer results confirms T2 Qwen fired",
    },
]

# ── Runner ────────────────────────────────────────────────────────────────────

async def run_tests(base_url: str) -> None:
    print(f"\n{'='*65}")
    print(f"  JimsAI Targeted Tests  |  {base_url}")
    print(f"{'='*65}\n")

    async with httpx.AsyncClient(timeout=300.0) as client:
        # Health check
        try:
            h = await client.get(f"{base_url}/health")
            if h.status_code != 200:
                print(f"❌ Backend not healthy: {h.status_code}"); return
            print(f"✅ Backend: {h.json()}\n")
        except Exception as e:
            print(f"❌ Cannot reach backend: {e}"); return

        # Auth
        email = os.getenv("JIMS_BENCHMARK_EMAIL", "")
        password = os.getenv("JIMS_BENCHMARK_PASSWORD", "")
        headers: dict = {}
        if email and password:
            try:
                r = await client.post(f"{base_url}/v1/auth/signin",
                                      json={"email": email, "password": password}, timeout=30)
                if r.status_code == 200:
                    tok = r.json().get("access_token") or r.json().get("token", "")
                    if tok:
                        headers["Authorization"] = f"Bearer {tok}"
                        print(f"✅ Authenticated as {email}\n")
            except Exception:
                pass

        # Use a single thread_id so memory_write persists for memory_recall
        thread_id = f"targeted_{int(time.time())}"

        results: list[dict] = []
        passed = failed = 0

        for test in TESTS:
            tid = test["id"]
            group = test["group"]
            prompt = test["prompt"]
            expect = test["expect"]

            print(f"[{group.upper():8s}] {tid}")
            print(f"  Prompt: {prompt[:90]}")

            payload = {
                "user_id": "targeted_test_user",
                "query": prompt,
                "modality": "text",
                "workspace_id": "targeted_test_ws",
                "thread_id": thread_id,
                "return_trace": True,
            }

            t0 = time.perf_counter()
            try:
                resp = await client.post(f"{base_url}/v1/query",
                                         json=payload, headers=headers, timeout=300)
                elapsed = time.perf_counter() - t0

                if resp.status_code != 200:
                    print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}\n")
                    failed += 1
                    results.append({"id": tid, "pass": False, "reason": f"HTTP {resp.status_code}"})
                    continue

                data = resp.json()
                response_text = data.get("response", "")
                confidence = data.get("confidence", 0.0)
                gaps = data.get("gaps", [])
                cap_plan = data.get("capability_plan") or {}
                cap_kind = cap_plan.get("kind", "") if cap_plan else ""
                ir = (data.get("ir") or {}).get("target_ir", "")
                layer_results = data.get("layer_results", [])
                used_local = any(
                    lr.get("data", {}).get("used_local_model")
                    for lr in layer_results
                    if isinstance(lr, dict)
                )

            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"  ❌ Exception: {e}\n")
                failed += 1
                results.append({"id": tid, "pass": False, "reason": str(e)})
                continue

            # ── Evaluate expectations ────────────────────────────────────────
            failures: list[str] = []

            if "cap" in expect and cap_kind != expect["cap"]:
                failures.append(f"cap={cap_kind!r} expected {expect['cap']!r}")

            if "ir_not" in expect and ir == expect["ir_not"]:
                failures.append(f"ir={ir!r} — should NOT be {expect['ir_not']!r}")

            if "min_confidence" in expect and confidence < expect["min_confidence"]:
                failures.append(f"confidence={confidence:.2f} < {expect['min_confidence']}")

            if "max_gaps" in expect and len(gaps) > expect["max_gaps"]:
                failures.append(f"gaps={len(gaps)} > max {expect['max_gaps']}: {gaps[:2]}")

            rlow = response_text.lower()
            if "response_contains_any" in expect:
                tokens = expect["response_contains_any"]
                if not any(t.lower() in rlow for t in tokens):
                    failures.append(
                        f"response missing all of {tokens} — got: {response_text[:120]!r}"
                    )

            if "response_not_contains" in expect:
                for bad in expect["response_not_contains"]:
                    if bad.lower() in rlow:
                        failures.append(f"response contains forbidden token {bad!r}")

            if "used_local_model" in expect:
                if expect["used_local_model"] and not used_local:
                    failures.append("used_local_model=False — T2 Qwen did not fire")

            ok = len(failures) == 0
            status = "✅ PASS" if ok else "❌ FAIL"
            if ok:
                passed += 1
            else:
                failed += 1

            print(f"  {status}  {elapsed*1000:.0f}ms  conf={confidence:.2f}  "
                  f"cap={cap_kind}  ir={ir}  gaps={len(gaps)}  "
                  f"t2={'yes' if used_local else 'no'}")
            if response_text:
                print(f"  → {response_text[:150].replace(chr(10), ' ')}")
            for f in failures:
                print(f"  ✗ {f}")
            print()

            results.append({"id": tid, "pass": ok, "failures": failures})

    print("="*65)
    print(f"  Results: {passed} passed, {failed} failed  ({len(TESTS)} total)")
    print("="*65)

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r["pass"]:
                print(f"  {r['id']}: {'; '.join(r.get('failures', [r.get('reason','')]))}")
        sys.exit(1)
    else:
        print("\nAll targeted tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    asyncio.run(run_tests(args.base_url))
