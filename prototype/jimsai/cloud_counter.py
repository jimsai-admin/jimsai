"""cloud_counter.py — a cold-start-durable, cloud-backed integer counter map.

A GENERAL mechanism for the "no local growing list" rule: any distributionally
learned, continuously growing counter — background document-frequency for
common-vocabulary detection (in ANY language), usage tallies, feedback counts —
must persist to the cloud so it survives Lambda cold starts and is shared across
instances, instead of resetting as an in-process dict on every invocation.

Not a one-off patch and not language-specific: it is a drop-in dict-like counter
that write-behinds increments to a Redis hash and reads through a local cache. If
Redis is unavailable (or disabled) it degrades to a pure in-memory counter that is
byte-for-byte the previous behaviour — so nothing breaks in dev or if the provider
is down. The same class can back any of the other in-memory counters in the
pipeline; object collections (feedback events, ambiguity queue, …) need a
row-store (Supabase/Neo4j) instead — see the migration note in the pipeline.
"""

from __future__ import annotations

import os
from collections import defaultdict

_client = None
_tried = False


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_client(redis_url: str | None = None):
    """Lazily connect to Redis once; return None (and stay None) if unavailable."""
    global _client, _tried
    if _client is not None or _tried:
        return _client
    _tried = True
    if not _truthy(os.getenv("REDIS_ENABLED", "false")):
        return None
    url = redis_url or os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        import redis  # redis-py is already a backend dependency

        c = redis.from_url(url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True)
        c.ping()
        _client = c
    except Exception:
        _client = None
    return _client


class CloudCounter:
    """Dict-like `{key: int}` counter backed by a Redis hash (namespace)."""

    def __init__(self, namespace: str, flush_every: int = 64, redis_url: str | None = None) -> None:
        self._ns = namespace
        self._local: dict[str, int] = defaultdict(int)   # read cache (authoritative in-process)
        self._pending: dict[str, int] = defaultdict(int)  # unflushed increments
        self._loaded: set[str] = set()                    # keys already hydrated from Redis
        self._flush_every = max(1, flush_every)
        self._since = 0
        self._client = _get_client(redis_url)

    @property
    def cloud_backed(self) -> bool:
        return self._client is not None

    def get(self, key: str, default: int = 0) -> int:
        if key not in self._local and self._client is not None and key not in self._loaded:
            self._loaded.add(key)
            try:
                v = self._client.hget(self._ns, key)
                if v is not None:
                    self._local[key] = int(v)
            except Exception:
                pass
        return self._local.get(key, default)

    def incr(self, key: str, n: int = 1) -> None:
        self._local[key] += n
        self._pending[key] += n
        self._since += n
        if self._since >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        """Write-behind pending increments to Redis in one pipeline. Best-effort:
        on failure the increments are retained locally and retried next flush."""
        if not self._pending:
            self._since = 0
            return
        pending = self._pending
        self._pending = defaultdict(int)
        self._since = 0
        if self._client is None:
            return
        try:
            pipe = self._client.pipeline()
            for k, v in pending.items():
                pipe.hincrby(self._ns, k, v)
            pipe.execute()
        except Exception:
            for k, v in pending.items():
                self._pending[k] += v   # keep for next attempt

    def clear(self) -> None:
        self._local.clear()
        self._pending.clear()
        self._loaded.clear()
        self._since = 0
        if self._client is not None:
            try:
                self._client.delete(self._ns)
            except Exception:
                pass

    def __len__(self) -> int:
        return len(self._local)

    def __contains__(self, key: str) -> bool:
        return self.get(key, -1) >= 0
