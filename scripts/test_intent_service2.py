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
    
    system = "You are an intent classifier. Return only JSON with target_ir and confidence."
    user = json.dumps({
        "raw_input": "My name is Celestine.",
        "deterministic_ir": {"target_ir": "WORKSPACE_QUERY", "confidence": 0.3},
        "allowed_targets": ["WORKSPACE_QUERY", "FETCH_DOCUMENT", "CODE_GENERATE", "GENERAL_FACT"]
    })
    
    payload = {
        "model": "qwen3-1.7b-instruct",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(f"{url}/generate", headers=headers, json=payload)
            print(f"Status: {r.status_code}")
            data = r.json()
            print(f"Response: {json.dumps(data, indent=2)}")
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")

asyncio.run(test())