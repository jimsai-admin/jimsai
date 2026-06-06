"""
JimsAI Backend Connectivity Health Check
Checks all backend services for latency and availability.
Secrets are loaded from .env and NEVER printed in plain text.
"""

import os
import sys
import time
import asyncio
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
env_vars: dict[str, str] = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_vars[key.strip()] = value.strip()

def get(key: str, fallback: str = "") -> str:
    return env_vars.get(key, os.environ.get(key, fallback))

def mask(value: str) -> str:
    """Return a masked version for display."""
    if not value:
        return "(not set)"
    return value[:6] + "***"

# ── Credentials (never printed raw) ───────────────────────────────────────
SUPABASE_BASE_URL   = get("SUPABASE_URL").rstrip("/")   # may include /rest/v1/
SUPABASE_ANON_KEY   = get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = get("SUPABASE_SERVICE_KEY")

CF_ACCOUNT_ID       = get("CF_ACCOUNT_ID")
CF_VECTORIZE_INDEX  = get("CF_VECTORIZE_INDEX")
CF_VECTORIZE_TOKEN  = get("CF_VECTORIZE_API_TOKEN")
CF_R2_BUCKET        = get("CF_R2_BUCKET")
CF_R2_ACCESS_KEY    = get("CF_R2_ACCESS_KEY")
CF_R2_SECRET_KEY    = get("CF_R2_SECRET_KEY")

NEO4J_URI           = get("NEO4J_URI")
NEO4J_USER          = get("NEO4J_USER") or get("NEO4J_USERNAME")
NEO4J_PASSWORD      = get("NEO4J_PASSWORD")
NEO4J_DATABASE      = get("NEO4J_DATABASE", "neo4j")

REDIS_URL           = get("REDIS_URL")

# Supabase project base URL (strip /rest/v1 suffix if present)
if "/rest/v1" in SUPABASE_BASE_URL:
    SUPABASE_PROJECT_URL = SUPABASE_BASE_URL.split("/rest/v1")[0]
else:
    SUPABASE_PROJECT_URL = SUPABASE_BASE_URL

SUPABASE_REST_URL   = SUPABASE_PROJECT_URL + "/rest/v1"
SUPABASE_AUTH_URL   = SUPABASE_PROJECT_URL + "/auth/v1"

# ── Result helpers ─────────────────────────────────────────────────────────
SLOW_THRESHOLD_MS = 2000
results: list[dict] = []

def record(service: str, status: str, latency_ms: float | None, note: str = ""):
    emoji = {"OK": "✅", "FAIL": "❌", "SLOW": "⚠️ SLOW"}.get(status, status)
    lat_str = f"{latency_ms:.0f}ms" if latency_ms is not None else "N/A"
    line = f"  {emoji:10s} {service:<30s}  {lat_str:<10s}  {note}"
    print(line)
    results.append({"service": service, "status": status, "latency_ms": latency_ms, "note": note})

def classify(latency_ms: float) -> str:
    return "SLOW" if latency_ms > SLOW_THRESHOLD_MS else "OK"

# ══════════════════════════════════════════════════════════════════════════
# 1.  Supabase REST API
# ══════════════════════════════════════════════════════════════════════════
def check_supabase_rest():
    import httpx
    url = f"{SUPABASE_REST_URL}/signatures?limit=1"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    try:
        t0 = time.perf_counter()
        r = httpx.get(url, headers=headers, timeout=15)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            record("Supabase REST", classify(ms), ms, f"HTTP {r.status_code}")
        else:
            record("Supabase REST", "FAIL", ms,
                   f"HTTP {r.status_code} — {r.text[:120]}")
    except Exception as exc:
        record("Supabase REST", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# 2.  Supabase Auth
# ══════════════════════════════════════════════════════════════════════════
def check_supabase_auth():
    import httpx
    url = f"{SUPABASE_AUTH_URL}/token?grant_type=password"
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "email": "Jimstechinnovations@gmail.com",
        "password": "Irekanmi@231",
    }
    try:
        t0 = time.perf_counter()
        r = httpx.post(url, headers=headers, json=body, timeout=15)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            record("Supabase Auth", classify(ms), ms, f"HTTP {r.status_code} — token issued")
        else:
            record("Supabase Auth", "FAIL", ms,
                   f"HTTP {r.status_code} — {r.text[:120]}")
    except Exception as exc:
        record("Supabase Auth", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# 3.  Cloudflare Vectorize
# ══════════════════════════════════════════════════════════════════════════
def check_vectorize():
    import httpx
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        f"/vectorize/v2/indexes/{CF_VECTORIZE_INDEX}/query"
    )
    headers = {
        "Authorization": f"Bearer {CF_VECTORIZE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"vector": [0.1] * 768, "topK": 1}
    try:
        t0 = time.perf_counter()
        r = httpx.post(url, headers=headers, json=body, timeout=20)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code in (200, 204):
            record("Cloudflare Vectorize", classify(ms), ms, f"HTTP {r.status_code}")
        else:
            record("Cloudflare Vectorize", "FAIL", ms,
                   f"HTTP {r.status_code} — {r.text[:120]}")
    except Exception as exc:
        record("Cloudflare Vectorize", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# 4.  Neo4j AuraDB
# ══════════════════════════════════════════════════════════════════════════
def check_neo4j():
    try:
        from neo4j import GraphDatabase
        t0 = time.perf_counter()
        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=15,
        )
        driver.verify_connectivity()
        ms = (time.perf_counter() - t0) * 1000
        driver.close()
        record("Neo4j AuraDB", classify(ms), ms, "Bolt OK")
    except Exception as exc:
        record("Neo4j AuraDB", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# 5.  Redis
# ══════════════════════════════════════════════════════════════════════════
def check_redis():
    try:
        import redis as redis_lib
        t0 = time.perf_counter()
        r = redis_lib.from_url(REDIS_URL, socket_connect_timeout=10, socket_timeout=10)
        result = r.ping()
        ms = (time.perf_counter() - t0) * 1000
        if result:
            record("Redis", classify(ms), ms, "PONG")
        else:
            record("Redis", "FAIL", ms, "PING returned False")
    except Exception as exc:
        record("Redis", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# 6.  Cloudflare R2 (S3-compatible)
# ══════════════════════════════════════════════════════════════════════════
def check_r2():
    try:
        import boto3
        from botocore.config import Config
        endpoint = f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=CF_R2_ACCESS_KEY,
            aws_secret_access_key=CF_R2_SECRET_KEY,
            region_name="auto",
            config=Config(connect_timeout=10, read_timeout=15),
        )
        t0 = time.perf_counter()
        resp = client.list_objects_v2(Bucket=CF_R2_BUCKET, MaxKeys=1)
        ms = (time.perf_counter() - t0) * 1000
        count = resp.get("KeyCount", "?")
        record("Cloudflare R2", classify(ms), ms, f"Listed OK, KeyCount={count}")
    except Exception as exc:
        record("Cloudflare R2", "FAIL", None, str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 72)
    print("  JimsAI Backend Connectivity Health Check")
    print("=" * 72)
    print(f"  Supabase project : {SUPABASE_PROJECT_URL}")
    print(f"  Supabase key     : {mask(SUPABASE_ANON_KEY)}")
    print(f"  CF account       : {mask(CF_ACCOUNT_ID)}")
    print(f"  CF Vectorize idx : {CF_VECTORIZE_INDEX}")
    print(f"  Neo4j URI        : {NEO4J_URI}")
    print(f"  Redis URL        : {REDIS_URL[:30]}***")
    print(f"  R2 bucket        : {CF_R2_BUCKET}")
    print("=" * 72)
    print()

    checks = [
        ("1. Supabase REST API",       check_supabase_rest),
        ("2. Supabase Auth",           check_supabase_auth),
        ("3. Cloudflare Vectorize",    check_vectorize),
        ("4. Neo4j AuraDB",            check_neo4j),
        ("5. Redis",                   check_redis),
        ("6. Cloudflare R2",           check_r2),
    ]

    for label, fn in checks:
        print(f"[{label}]")
        fn()
        print()

    # Summary
    print("=" * 72)
    ok    = [r for r in results if r["status"] == "OK"]
    slow  = [r for r in results if r["status"] == "SLOW"]
    fail  = [r for r in results if r["status"] == "FAIL"]
    print(f"  SUMMARY  ✅ {len(ok)} OK   ⚠️  {len(slow)} SLOW   ❌ {len(fail)} FAIL")
    if slow or fail:
        print()
        print("  ACTION NEEDED:")
        for r in slow:
            print(f"    ⚠️  {r['service']} is slow ({r['latency_ms']:.0f}ms > {SLOW_THRESHOLD_MS}ms)")
        for r in fail:
            print(f"    ❌  {r['service']} FAILED — {r['note']}")
    print("=" * 72)
    sys.exit(1 if fail else 0)
