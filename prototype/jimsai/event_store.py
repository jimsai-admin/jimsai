from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import utc_now


class AuditEventStore:
    """Durable append-only SQLite event store with CQRS-friendly indexes."""

    def __init__(self, path: str | None = None) -> None:
        is_lambda = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        default_dir = Path("/tmp/.logs") if is_lambda else Path(".logs")
        default_path = default_dir / "jimsai_events.sqlite3"
        self.path = Path(path or os.getenv("JIMS_EVENT_STORE_PATH", str(default_path)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def append(self, event_type: str, aggregate_id: str, payload: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
        event = {
            "event_id": uuid4().hex,
            "event_type": event_type,
            "aggregate_id": aggregate_id,
            "user_id": user_id,
            "payload": payload,
            "created_at": utc_now().isoformat(),
        }
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (event_id, event_type, aggregate_id, user_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event["event_id"], event_type, aggregate_id, user_id, payload_json, event["created_at"]),
            )
            self._update_projection(connection, event_type, aggregate_id, user_id, payload_json, event["created_at"])
        return event

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, aggregate_id, user_id, payload_json, created_at
                FROM audit_events
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._row_to_event(row) for row in reversed(rows)]

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            projections = connection.execute("SELECT COUNT(*) FROM cqrs_read_models").fetchone()[0]
        return {"audit_events_total": int(total), "cqrs_read_models": int(projections)}

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    user_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_aggregate ON audit_events(aggregate_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_user ON audit_events(user_id)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cqrs_read_models (
                    model_name TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    user_id TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (model_name, aggregate_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _update_projection(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        aggregate_id: str,
        user_id: str | None,
        payload_json: str,
        created_at: str,
    ) -> None:
        model_name = {
            "memory_signature_inserted": "memory_signatures",
            "feedback_recorded": "feedback_events",
            "query_completed": "query_results",
            "query_cache_hit": "query_cache_hits",
            "result_cache_invalidated": "cache_invalidations",
            "result_signature_written": "result_signatures",
            "review_action_recorded": "review_actions",
            "saga_started": "saga_state",
            "saga_step_completed": "saga_state",
            "saga_completed": "saga_state",
            "saga_failed": "saga_state",
            "sandbox_execution_completed": "sandbox_results",
            "math_solve_completed": "math_results",
        }.get(event_type)
        if not model_name:
            return
        connection.execute(
            """
            INSERT INTO cqrs_read_models (model_name, aggregate_id, user_id, payload_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(model_name, aggregate_id)
            DO UPDATE SET user_id = excluded.user_id, payload_json = excluded.payload_json, updated_at = excluded.updated_at
            """,
            (model_name, aggregate_id, user_id, payload_json, created_at),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        return {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "aggregate_id": row["aggregate_id"],
            "user_id": row["user_id"],
            "payload": payload,
            "created_at": row["created_at"],
        }


class VerifiedResultCache:
    """Durable SQLite cache keyed by canonical scoped request signatures."""

    def __init__(self, path: str | None = None) -> None:
        is_lambda = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
        default_dir = Path("/tmp/.logs") if is_lambda else Path(".logs")
        default_path = default_dir / "jimsai_events.sqlite3"
        self.path = Path(path or os.getenv("JIMS_EVENT_STORE_PATH", str(default_path)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()  # add this
        self._initialize()              # add this

    def key(self, namespace: str, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"{namespace}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    def get(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value_json, stored_at FROM verified_result_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError:
            return None
        return {"value": value, "stored_at": row["stored_at"]}

    def set(self, key: str, value: dict[str, Any]) -> None:
        value_json = json.dumps(value, sort_keys=True, default=str)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO verified_result_cache (cache_key, value_json, stored_at)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key)
                DO UPDATE SET value_json = excluded.value_json, stored_at = excluded.stored_at
                """,
                (key, value_json, utc_now().isoformat()),
            )

    def clear(self) -> int:
        with self._lock, self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM verified_result_cache").fetchone()[0]
            connection.execute("DELETE FROM verified_result_cache")
        return int(count)

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM verified_result_cache").fetchone()[0]
        return {"result_cache_entries": int(count)}

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS verified_result_cache (
                    cache_key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    stored_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection
