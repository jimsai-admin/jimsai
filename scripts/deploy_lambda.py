#!/usr/bin/env python3
"""
deploy_lambda.py
----------------
Triggers the PowerShell Lambda deploy script and streams its output.

Reads AWS credentials / settings from .env (root directory).
Usage:  python scripts/deploy_lambda.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Load .env ─────────────────────────────────────────────────────────────────

env_path = ROOT / ".env"
if not env_path.exists():
    sys.exit(f"ERROR: .env not found at {env_path}")

values: dict[str, str] = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, val = line.split("=", 1)
    values[key.strip()] = val.strip().strip('"').strip("'")

# Inject .env values into the current process environment so PowerShell inherits them
os.environ.update(values)

# ── Run deploy script ──────────────────────────────────────────────────────────

deploy_script = ROOT / "infrastructure" / "aws-lambda" / "deploy-lambda-zip.ps1"
if not deploy_script.exists():
    sys.exit(f"ERROR: deploy script not found at {deploy_script}")

print(f"\n🚀 Deploying JimsAI API Gateway to AWS Lambda")
print(f"   Script: {deploy_script}\n")

result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(deploy_script)],
    cwd=str(ROOT),
    env=os.environ,
)

if result.returncode != 0:
    print(f"\n❌ Lambda deploy failed (exit code {result.returncode})")
    sys.exit(result.returncode)

print("\n✅ Lambda deploy completed successfully")
