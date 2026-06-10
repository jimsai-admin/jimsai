"""Quick smoke test: verify Groq T1 and T2 paths both work."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from prototype.jimsai.model_bridge import QwenBridge


async def main() -> None:
    b = QwenBridge()
    print(f"  groq_enabled : {b.groq_enabled}")
    print(f"  t1_model     : {b.groq_t1_model}")
    print(f"  t2_model     : {b.groq_t2_model}")
    print()

    if not b.qwen_enabled:
        print("ERROR: bridge not enabled — check JIMS_ALLOW_EXTERNAL_GROQ and GROQ_API_KEY")
        sys.exit(1)

    # T1: intent extraction
    print("T1 (llama-3.1-8b-instant) ...")
    r1 = await b._chat_json(
        "t1",
        'Return JSON only with key "intent" set to "CODE_GENERATE".',
        "Write a JavaScript function",
        max_tokens=60,
    )
    print(f"  result: {r1}")
    assert r1 and "intent" in r1, f"T1 failed — got: {r1}"
    print("  T1 PASS\n")

    # T2: code generation (language inferred — JS in this case)
    print("T2 (llama-3.3-70b-versatile) ...")
    r2 = await b._render_chat_json(
        (
            "You are a code generation engine that supports all programming languages. "
            "Return JSON only with key 'candidate_steps' containing a list with one element: "
            "the complete implementation as a single string."
        ),
        json.dumps({"goal": "Write a JavaScript arrow function that doubles a number"}),
        max_tokens=300,
    )
    print(f"  result keys: {list(r2.keys()) if r2 else None}")
    steps = (r2 or {}).get("candidate_steps", [])
    print(f"  code preview: {str(steps[0])[:150] if steps else 'EMPTY'}")
    assert steps and len(str(steps[0])) > 10, f"T2 failed — got: {r2}"
    print("  T2 PASS\n")

    print("Both Groq paths working correctly.")


if __name__ == "__main__":
    asyncio.run(main())
