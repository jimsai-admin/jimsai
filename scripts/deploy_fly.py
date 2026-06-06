#!/usr/bin/env python3
"""
deploy_fly.py
-------------
Deploy JimsAI API Gateway to Fly.io.

1. Reads secrets from .env and pushes them via `fly secrets set`
2. Runs `fly deploy` from the repo root using infrastructure/fly/fly.toml
3. Polls /health until the app is live

Usage:
    python scripts/deploy_fly.py
    python scripts/deploy_fly.py --app jimsai-api --region lhr
    python scripts/deploy_fly.py --secrets-only   # only push secrets, skip deploy
    python scripts/deploy_fly.py --deploy-only    # skip secrets, just deploy
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FLY_TOML = ROOT / "fly.toml"

# ── Secrets that must be injected via `fly secrets set` (never in fly.toml) ──
FLY_SECRET_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "JIMS_EMBEDDING_SERVICE_TOKEN",
    "JIMS_MULTIMODAL_ENCODER_API_KEY",
    "JIMS_LOCAL_INFERENCE_API_KEY",
    "JIMS_QWEN_SERVICE_TOKEN",
    "JIMS_CAPABILITY_EMBEDDING_SERVICE_TOKEN",
    "JIMS_CAPABILITY_CLASSIFIER_TOKEN",
    "CF_ACCOUNT_ID",
    "CF_VECTORIZE_INDEX",
    "CF_VECTORIZE_API_TOKEN",
    "CF_R2_BUCKET",
    "CF_R2_ACCESS_KEY",
    "CF_R2_SECRET_KEY",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "REDIS_URL",
    "KAGGLE_USERNAME",
    "KAGGLE_API_TOKEN",
    "KAGGLE_DATASET_OWNER",
    # Optional extras
    "JIMS_RENDER_AGENT_TOKEN",
    "CORS_ORIGINS",
]


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def run(cmd: list[str], **kwargs) -> int:
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    return result.returncode


def push_secrets(env: dict[str, str], app: str) -> None:
    pairs = [f"{k}={env[k]}" for k in FLY_SECRET_KEYS if k in env and env[k]]
    if not pairs:
        print("  ⚠️  No secrets found in .env to push")
        return

    print(f"\n🔐 Pushing {len(pairs)} secrets to Fly.io app '{app}'…")
    cmd = ["fly", "secrets", "set", "--app", app, "--stage"] + pairs
    rc = run(cmd)
    if rc != 0:
        sys.exit(f"❌ fly secrets set failed (exit {rc})")
    print(f"  ✅ {len(pairs)} secrets staged")


def deploy(app: str, region: str | None) -> None:
    print(f"\n🚀 Deploying JimsAI API to Fly.io app '{app}'…")
    cmd = [
        "fly", "deploy",
        "--config", str(FLY_TOML),
        "--app", app,
        "--remote-only",
    ]
    if region:
        cmd += ["--region", region]
    rc = run(cmd, cwd=str(ROOT))
    if rc != 0:
        sys.exit(f"❌ fly deploy failed (exit {rc})")


def wait_for_health(app: str, timeout: int = 180) -> None:
    url = f"https://{app}.fly.dev/health"
    print(f"\n⏳ Waiting for {url} to be healthy (up to {timeout}s)…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=10)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"  ✅ {url} → {resp.json()}")
                return
            print(f"  ⏳ {resp.status_code} — waiting…")
        except Exception as exc:
            print(f"  ⏳ not ready yet ({exc.__class__.__name__}) — waiting…")
        time.sleep(8)
    sys.exit(f"❌ App did not become healthy within {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy JimsAI API to Fly.io")
    parser.add_argument("--app",          default="jimsai-api",  help="Fly app name")
    parser.add_argument("--region",       default=None,          help="Override primary region (e.g. lhr, fra)")
    parser.add_argument("--secrets-only", action="store_true",   help="Only push secrets, skip deploy")
    parser.add_argument("--deploy-only",  action="store_true",   help="Skip secrets, only deploy")
    args = parser.parse_args()

    env_path = ROOT / ".env"
    if not env_path.exists():
        sys.exit(f"ERROR: .env not found at {env_path}")
    env = load_env(env_path)

    print(f"\n{'='*60}")
    print(f"  JimsAI Fly.io Deploy")
    print(f"  App   : {args.app}")
    print(f"  Region: {args.region or 'from fly.toml (iad)'}")
    print(f"{'='*60}")

    if not args.deploy_only:
        push_secrets(env, args.app)

    if not args.secrets_only:
        deploy(args.app, args.region)
        wait_for_health(args.app)

    print(f"\n{'='*60}")
    print(f"  ✅ Deploy complete!")
    print(f"  URL  : https://{args.app}.fly.dev")
    print(f"  Health: https://{args.app}.fly.dev/health")
    print(f"\n  Next steps:")
    print(f"    1. Update Vercel env: NEXT_PUBLIC_API_BASE_URL=https://{args.app}.fly.dev")
    print(f"    2. Redeploy Vercel frontend")
    print(f"    3. Update CORS_ORIGINS if needed: fly secrets set CORS_ORIGINS=https://jimsai.vercel.app")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
