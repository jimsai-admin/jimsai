"""cloud_artifact.py — load a bulk data artifact from R2 with a local cache.

The object-store analogue of `cloud_counter.CloudCounter`, and the same rule for a
different data shape: reference data that GROWS (the concept lexicon, learned common
words, the concept graph) must not be baked into the deployment package. A Lambda's
filesystem is read-only, training/enrichment cannot rewrite a packaged file, and a
code-bundled copy silently drifts from what local development uses. So the artifact
lives once in R2 — the single source of truth for BOTH local and deploy — and is
fetched into a cache directory on first use.

Load pattern: the concept index reads its lexicon WHOLE at startup (not row-by-row),
so an object store is the right fit — one GET per cold start, revalidated by ETag so
a re-seeded snapshot is picked up automatically with no redeploy. If R2 is
unavailable the loader serves a previously cached copy, then a caller-supplied local
fallback file (the repo's seed data, for offline dev), and only then returns None so
the caller fails safe (e.g. the index runs empty) — never a crash, never stale data
frozen into a release.

This is a general mechanism: any bulk artifact (`concept-model/lexicon.jsonl`,
`common_words.jsonl`, `edges.jsonl`, future model snapshots) uses the same path.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_client = None
_tried = False


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _cache_dir() -> Path:
    """Writable cache root. /tmp on Lambda (the only writable path there); the OS
    temp dir locally. Override with JIMS_ARTIFACT_CACHE."""
    root = os.getenv("JIMS_ARTIFACT_CACHE") or str(Path(tempfile.gettempdir()) / "jims-artifacts")
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_name(key: str) -> str:
    return key.replace("/", "__").replace("\\", "__")


def _bucket(explicit: str | None = None) -> str | None:
    return explicit or os.getenv("JIMS_LEXICON_R2_BUCKET") or os.getenv("CF_R2_BUCKET")


def _get_client():
    """Lazily build one boto3 S3 client for R2 from the CF_* credentials; return
    None (and stay None) if boto3 or the credentials are unavailable. Mirrors the
    connection shape of providers.R2Adapter so there is one way to reach R2."""
    global _client, _tried
    if _client is not None or _tried:
        return _client
    _tried = True
    account = os.getenv("CF_ACCOUNT_ID")
    access_key = os.getenv("CF_R2_ACCESS_KEY")
    secret_key = os.getenv("CF_R2_SECRET_KEY")
    if not (account and access_key and secret_key):
        return None
    try:
        import boto3  # bundled in the Lambda runtime; a normal dep locally

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
    except Exception as e:  # pragma: no cover - environment dependent
        logger.warning("cloud_artifact: R2 client unavailable (%s)", e)
        _client = None
    return _client


def r2_available() -> bool:
    return _get_client() is not None and bool(_bucket())


def artifact_path(
    key: str,
    *,
    local_fallback: str | Path | None = None,
    bucket: str | None = None,
    refresh: bool | None = None,
) -> Path | None:
    """Return a local filesystem path to the R2 object at ``key``.

    Fetches from R2 into the cache on first use and whenever the object's ETag has
    changed (so a re-seeded snapshot propagates without a redeploy). Serves the
    cached copy when R2 is unreachable, then ``local_fallback`` if it exists, then
    None. Never raises — the caller decides how to degrade.
    """
    bucket = _bucket(bucket)
    if refresh is None:
        refresh = _truthy(os.getenv("JIMS_ARTIFACT_REFRESH"))
    cache = _cache_dir() / _safe_name(key)
    etag_file = cache.with_name(cache.name + ".etag")

    client = _get_client()
    if client is not None and bucket:
        try:
            head = client.head_object(Bucket=bucket, Key=key)
            etag = str(head.get("ETag", "")).strip('"')
            cached_etag = etag_file.read_text(encoding="utf-8").strip() if etag_file.exists() else ""
            if cache.exists() and cached_etag and cached_etag == etag and not refresh:
                return cache
            tmp = cache.with_name(cache.name + ".tmp")
            client.download_file(bucket, key, str(tmp))
            os.replace(tmp, cache)  # atomic — never expose a partial download
            if etag:
                etag_file.write_text(etag, encoding="utf-8")
            logger.info("cloud_artifact: fetched %s from R2 bucket %s (%d bytes)", key, bucket, cache.stat().st_size)
            return cache
        except Exception as e:
            logger.warning("cloud_artifact: R2 fetch failed for %s (%s); falling back", key, e)

    if cache.exists():  # R2 down/absent but we fetched it before — serve the cache
        logger.info("cloud_artifact: serving cached %s (R2 unavailable)", key)
        return cache
    if local_fallback:
        fb = Path(local_fallback)
        if fb.exists():
            logger.info("cloud_artifact: using local fallback for %s -> %s", key, fb)
            return fb
    logger.warning("cloud_artifact: no source for %s (R2 unavailable, no cache, no local fallback)", key)
    return None


def upload_artifact(key: str, path: str | Path, *, bucket: str | None = None) -> bool:
    """Publish/refresh a local file to R2 under ``key``. Used by the seed script and
    by enrichment to push a new snapshot. Returns True on success."""
    client = _get_client()
    bucket = _bucket(bucket)
    if client is None or not bucket:
        logger.error("cloud_artifact: cannot upload %s — R2 client or bucket unavailable", key)
        return False
    p = Path(path)
    if not p.exists():
        logger.error("cloud_artifact: cannot upload %s — local file missing: %s", key, p)
        return False
    try:
        client.upload_file(str(p), bucket, key)
        logger.info("cloud_artifact: uploaded %s -> r2://%s/%s (%d bytes)", p, bucket, key, p.stat().st_size)
        return True
    except Exception as e:
        logger.error("cloud_artifact: upload failed for %s (%s)", key, e)
        return False
