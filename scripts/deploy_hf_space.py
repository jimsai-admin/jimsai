#!/usr/bin/env python3
"""
deploy_hf_space.py
------------------
Deploys the JimsAI embedding-service Space to Hugging Face.

Reads credentials from .env (root directory).
Usage:  python scripts/deploy_hf_space.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


# ── Load .env ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"

if not env_path.exists():
    sys.exit(f"ERROR: .env not found at {env_path}. Copy .env.example → .env and fill values.")

values: dict[str, str] = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = line.split("=", 1)
    values[key.strip()] = val.strip().strip('"').strip("'")

# ── Resolve HF token ──────────────────────────────────────────────────────────

HF_TOKEN = (
    values.get("HF_TOKEN")
    or values.get("HUGGINGFACE_HUB_TOKEN")
    or values.get("HUGGING_ACCESS_TOKEN")
    or values.get("HUGGING_ACESS_TOKEN")
    or ""
).strip()

if not HF_TOKEN:
    sys.exit(
        "ERROR: No HF token found in .env.\n"
        "Add one of: HF_TOKEN, HUGGINGFACE_HUB_TOKEN, HUGGING_ACCESS_TOKEN"
    )

# ── Resolve Space repo ID ─────────────────────────────────────────────────────

REPO_ID = values.get("HF_SPACE_REPO_ID", "jimstechai/jimsai-embedding-service").strip()
SPACE_DIR = ROOT / "infrastructure" / "huggingface-space" / "jimsai-embedding-service"

FILES_TO_UPLOAD = ["app.py", "Dockerfile", "README.md", "requirements.txt"]

# ── Upload ────────────────────────────────────────────────────────────────────

try:
    from huggingface_hub import HfApi
except ImportError:
    sys.exit(
        "ERROR: huggingface_hub not installed.\n"
        "Run: pip install huggingface_hub"
    )

print(f"\n🚀 Deploying JimsAI Embedding Space")
print(f"   Repo:  {REPO_ID}")
print(f"   Files: {', '.join(FILES_TO_UPLOAD)}\n")

api = HfApi(token=HF_TOKEN)

# Confirm space exists (create if not)
try:
    api.repo_info(repo_id=REPO_ID, repo_type="space")
    print(f"   ✓ Space {REPO_ID} exists")
except Exception:
    print(f"   Creating space {REPO_ID}...")
    api.create_repo(
        repo_id=REPO_ID,
        repo_type="space",
        space_sdk="docker",
        private=False,
    )
    print(f"   ✓ Space created")

errors: list[str] = []
for filename in FILES_TO_UPLOAD:
    local_path = SPACE_DIR / filename
    if not local_path.exists():
        print(f"   ⚠  SKIP {filename} (file not found locally)")
        continue
    try:
        url = api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=filename,
            repo_id=REPO_ID,
            repo_type="space",
            commit_message=f"feat: deploy {filename} (JimsAI tasks 19, 22-25)",
        )
        print(f"   ✓ {filename} → {url}")
    except Exception as exc:
        err_str = str(exc)
        # "No files have been modified" is not a real error — file already up to date
        if "No files have been modified" in err_str or "nothing to commit" in err_str.lower():
            print(f"   ✓ {filename} (already up to date, no change)")
        else:
            msg = f"   ✗ FAILED {filename}: {exc}"
            print(msg)
            errors.append(msg)

if errors:
    print(f"\n❌ Deploy completed with {len(errors)} error(s):")
    for e in errors:
        print(e)
    sys.exit(1)

print(f"\n✅ All files uploaded to {REPO_ID}")
print(f"   Space URL: https://huggingface.co/spaces/{REPO_ID}")
print(f"   Runtime URL: https://{REPO_ID.replace('/', '-')}.hf.space")
print("\n⏳ Space is rebuilding (~2–3 min). Check status at:")
print(f"   https://huggingface.co/spaces/{REPO_ID}/logs\n")
print("After build completes, verify:")
print(f"   curl https://{REPO_ID.replace('/', '-')}.hf.space/health")
print(f"   curl https://{REPO_ID.replace('/', '-')}.hf.space/v1/model/config")
