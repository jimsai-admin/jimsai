import os
from pathlib import Path
ROOT = Path(__file__).parent.parent
import sys; sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv; load_dotenv()

import httpx
import asyncio
import json

async def test():
    url = os.getenv("JIMS_INTENT_SERVICE_URL", "").rstrip("/")
    token = os.getenv("JIMS_MODAL_API_KEY", "")
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Exact same payload as QwenBridge
    system = (
        "You are an intent classifier for JIMS-AI. "
        "IMPORTANT: Output ONLY a valid JSON object. NO thinking, NO reasoning, NO explanations. "
        "Just the JSON object with 'target_ir' and 'confidence' fields. "
        "Allowed targets: WORKSPACE_QUERY, FETCH_DOCUMENT, SYSTEM_DIAGNOSTIC, CODE_GENERATE, RUN_CANVAS, RUN_INVENTION, GENERAL_FACT, EMOTIONAL_CATCH, META_INQUIRY. "
        "Do not include any text before or after the JSON."
    )
    user = json.dumps({
        "raw_input": "My name is Celestine.",
        "deterministic_ir": {"target_ir": "WORKSPACE_QUERY", "confidence": 0.3},
        "allowed_targets": [
            "WORKSPACE_QUERY",
            "FETCH_DOCUMENT",
            "SYSTEM_DIAGNOSTIC",
            "CODE_GENERATE",
            "RUN_CANVAS",
            "RUN_INVENTION",
            "GENERAL_FACT",
            "EMOTIONAL_CATCH",
            "META_INQUIRY",
        ],
    }, sort_keys=True)
    
    payload = {
        "model": "qwen3-1.7b-instruct",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 400,
    }
    
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        try:
            r = await client.post(f"{url}/generate", headers=headers, json=payload, follow_redirects=True)
            print(f"Status: {r.status_code}")
            data = r.json()
            print(f"Full response: {json.dumps(data, indent=2)}")
            
            raw_content = data.get("response") or data.get("content") or ""
            if not raw_content and "choices" in data:
                raw_content = data["choices"][0]["message"]["content"]
            print(f"\nRaw content: {raw_content[:500]}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

asyncio.run(test())