#!/usr/bin/env python3
"""
Create (or update) the modal-jimsai-secrets Modal Secret from .env.

Only the keys that Modal services actually need at runtime are included.
Keys like MODAL_TOKEN_ID, DOCKER_SOCKET, JIMS_BENCHMARK_* are local-only.

Usage: python scripts/create_modal_secret.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"

# Keys to include in the Modal Secret (everything Modal containers need)
MODAL_SECRET_KEYS = [
    # Auth
    "JIMS_MODAL_API_KEY",
    # Supabase
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    # Neo4j
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    # Redis
    "REDIS_URL",
    "REDIS_PASSWORD",
    # Cloudflare
    "CF_ACCOUNT_ID",
    "CF_TOKEN",
    "CF_R2_BUCKET",
    "CF_R2_ACCESS_KEY",
    "CF_R2_SECRET_KEY",
    "CF_VECTORIZE_INDEX",
    "CF_VECTORIZE_API_TOKEN",
    "CF_VECTORIZE_DIMENSIONS",
    # HuggingFace (needed for model downloads inside Modal containers)
    "HF_TOKEN",
    # Embedding
    "JIMS_EMBEDDING_SERVICE_URL",
    "JIMS_EMBEDDING_SERVICE_TOKEN",
    "JIMS_EMBEDDING_MODEL",
    # Modal service URLs
    "JIMS_CLASSIFICATION_SERVICE_URL",
    "JIMS_INTENT_SERVICE_URL",
    "JIMS_RENDERER_SERVICE_URL",
    "JIMS_REASONING_SERVICE_URL",
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            values[key] = val
    return values


def main() -> int:
    if not ENV_FILE.exists():
        print(f"ERROR: {ENV_FILE} not found", file=sys.stderr)
        return 1

    env = load_env(ENV_FILE)
    missing = [k for k in MODAL_SECRET_KEYS if k not in env or not env[k]]
    if missing:
        print(f"WARNING: These keys are missing or empty in .env — they will be skipped:")
        for k in missing:
            print(f"  {k}")

    pairs = [f"{k}={env[k]}" for k in MODAL_SECRET_KEYS if k in env and env[k]]
    if not pairs:
        print("ERROR: No secret values to set", file=sys.stderr)
        return 1

    print(f"Creating/updating Modal secret 'modal-jimsai-secrets' ({len(pairs)} keys)...")

    # Use modal secret create with --force to overwrite if it exists
    cmd = ["modal", "secret", "create", "modal-jimsai-secrets", "--force"] + pairs
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FAILED:\n{result.stderr}", file=sys.stderr)
        return 1

    print(f"✓ modal-jimsai-secrets created with {len(pairs)} keys")
    print("Keys set:", ", ".join(k for k in MODAL_SECRET_KEYS if k in env and env[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
