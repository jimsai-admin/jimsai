"""Quick test: verify the HF Space render endpoint responds to a code generation request."""
import httpx
import json
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(__import__("pathlib").Path(__file__).parent.parent / ".env")
except ImportError:
    pass

base = os.getenv("JIMS_LOCAL_INFERENCE_URL") or os.getenv("JIMS_EMBEDDING_SERVICE_URL", "")
token = (
    os.getenv("JIMS_LOCAL_INFERENCE_API_KEY")
    or os.getenv("JIMS_RENDER_AGENT_TOKEN")
    or os.getenv("JIMS_EMBEDDING_SERVICE_TOKEN", "")
)
t2_model = os.getenv("JIMS_LOCAL_RENDER_MODEL") or os.getenv("JIMS_QWEN_MODEL", "qwen3-4b-instruct")
render_path = os.getenv("JIMS_LOCAL_RENDER_CHAT_PATH", "/v1/chat/render")

print(f"  Base URL : {base}")
print(f"  Model    : {t2_model}")
print(f"  Path     : {render_path}")
print(f"  Token    : {'set' if token else 'MISSING'}")
print()

if not base:
    print("ERROR: No inference URL configured.")
    sys.exit(1)

headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

payload = {
    "model": t2_model,
    "messages": [
        {
            "role": "system",
            "content": (
                "You are a code generation engine that supports all programming languages. "
                "Return JSON only with key 'candidate_steps' containing a list with one element: "
                "the complete implementation as a single string."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"goal": "Write a Python function that reverses a string"}),
        },
    ],
    "max_tokens": 400,
    "temperature": 0,
    "response_format": {"type": "json_object"},
}

try:
    r = httpx.post(f"{base}{render_path}", headers=headers, json=payload, timeout=60)
    print(f"Status: {r.status_code}")
    body = r.json()
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    steps = parsed.get("candidate_steps", [])
    print(f"candidate_steps count: {len(steps)}")
    if steps:
        print(f"First step preview:\n{str(steps[0])[:300]}")
    else:
        print("WARNING: empty candidate_steps — full response:")
        print(content[:400])
except Exception as e:
    print(f"ERROR: {e}")
    if "r" in dir():
        print(r.text[:400])
