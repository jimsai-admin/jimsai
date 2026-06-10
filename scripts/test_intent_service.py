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
    
    print(f"URL: {url}")
    print(f"Token: {token[:10] if token else 'None'}...")
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Test health
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.get(f"{url}/health", headers=headers)
            print(f"Health: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"Health check failed: {e}")
        
        # Test generate endpoint
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
        
        try:
            r = await client.post(f"{url}/generate", headers=headers, json=payload)
            print(f"Generate: {r.status_code}")
            data = r.json()
            print(f"Response: {json.dumps(data, indent=2)[:1000]}")
        except Exception as e:
            print(f"Generate failed: {e}")

asyncio.run(test())