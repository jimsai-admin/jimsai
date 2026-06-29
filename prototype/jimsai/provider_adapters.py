from __future__ import annotations

# Use env_config.get_config() for fail-fast startup validation of required env vars.
# provider_adapters.py is loaded lazily and relies on its own .configured property checks.

import json
import math
import os
import time
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import logging

logger = logging.getLogger(__name__)

from .models import MemorySignature, Modality, ProviderStatus, TrainingPanelItem, TrainingPanelPage


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def provider_http_timeout() -> float:
    return env_float("JIMS_PROVIDER_HTTP_TIMEOUT", 6.0)


def provider_check_timeout() -> float:
    return env_float("JIMS_PROVIDER_CHECK_TIMEOUT", 4.0)


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def redis_url_from_env() -> str:
    explicit = os.getenv("REDIS_URL", "").strip()
    if explicit:
        return explicit
    endpoint = os.getenv("REDIS_PUBLIC_ENDPOINT", "").strip()
    password = os.getenv("REDIS_API", "").strip() or os.getenv("REDIS_PASSWORD", "").strip()
    if endpoint and password:
        if endpoint.startswith(("redis://", "rediss://")):
            return endpoint
        return f"rediss://default:{quote(password, safe='')}@{endpoint}/0"
    return ""


@dataclass(frozen=True)
class ProductionSettings:
    strict_provider_startup: bool
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    graph_provider: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str
    redis_url: str
    r2_account_id: str
    r2_bucket: str
    r2_access_key: str
    r2_secret_key: str
    vectorize_account_id: str
    vectorize_api_token: str
    vectorize_index: str
    vectorize_dimensions: int
    embedding_service_url: str
    embedding_service_token: str

    @classmethod
    def from_env(cls) -> "ProductionSettings":
        return cls(
            strict_provider_startup=env_bool("JIMS_STRICT_PROVIDER_STARTUP", False),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY", ""),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
            graph_provider=os.getenv("JIMS_GRAPH_PROVIDER", "neo4j_aura").strip().lower(),
            neo4j_uri=os.getenv("NEO4J_URI", ""),
            neo4j_user=os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            redis_url=redis_url_from_env(),
            r2_account_id=os.getenv("CF_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            r2_bucket=os.getenv("CF_R2_BUCKET") or os.getenv("S3_BUCKET", ""),
            r2_access_key=os.getenv("CF_R2_ACCESS_KEY", ""),
            r2_secret_key=os.getenv("CF_R2_SECRET_KEY", ""),
            vectorize_account_id=os.getenv("CF_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            vectorize_api_token=os.getenv("CF_VECTORIZE_API_TOKEN") or os.getenv("CF_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN", ""),
            vectorize_index=os.getenv("CF_VECTORIZE_INDEX", ""),
            vectorize_dimensions=int(os.getenv("CF_VECTORIZE_DIMENSIONS", "768") or "768"),
            embedding_service_url=os.getenv("JIMS_EMBEDDING_SERVICE_URL", "").strip().rstrip("/"),
            embedding_service_token=os.getenv("JIMS_MODAL_API_KEY", "").strip() or os.getenv("JIMS_EMBEDDING_SERVICE_TOKEN", "").strip(),
        )

    @property
    def production_mode(self) -> bool:
        return True  # always production

    @property
    def enable_r2(self) -> bool:
        return env_flag("JIMS_ENABLE_R2", True)

    @property
    def enable_vectorize(self) -> bool:
        return env_flag("JIMS_ENABLE_VECTORIZE", True)

    @property
    def enable_neo4j(self) -> bool:
        if self.graph_provider != "neo4j_aura":
            return False
        return env_flag("JIMS_ENABLE_NEO4J", True)

    @property
    def enable_celery(self) -> bool:
        return env_flag("JIMS_ENABLE_CELERY", True)

    @property
    def cloud_authoritative(self) -> bool:
        return True  # always cloud-authoritative

    @property
    def enable_multimodal_encoders(self) -> bool:
        # Multimodal encoding routes through the Modal Embedding Service
        return bool(self.embedding_service_url)

    @property
    def effective_multimodal_encoder_mode(self) -> str:
        return "external" if self.embedding_service_url else "disabled"


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        next_key = key.replace(".", "_").replace('"', "_")
        if next_key.startswith("$"):
            next_key = next_key[1:]
        if next_key:
            clean[next_key] = value
    return clean


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(float(value) / norm, 6) for value in values]


def _total_from_content_range(value: str, fallback: int) -> int:
    if "/" not in value:
        return fallback
    total = value.rsplit("/", 1)[1].strip()
    if total == "*":
        return fallback
    try:
        return int(total)
    except ValueError:
        return fallback


class R2ObjectStore:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings
        self._client: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.r2_account_id
            and self.settings.r2_bucket
            and self.settings.r2_access_key
            and self.settings.r2_secret_key
        )

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client(
                service_name="s3",
                endpoint_url=f"https://{self.settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=self.settings.r2_access_key,
                aws_secret_access_key=self.settings.r2_secret_key,
                region_name="auto",
            )
        return self._client

    def check(self) -> str:
        if not self.configured:
            return "missing R2 account, bucket, or S3-compatible access keys"
        self._get_client().head_bucket(Bucket=self.settings.r2_bucket)
        return "connected to R2 bucket"

    def put_text(self, key: str, value: str, content_type: str = "text/plain") -> str:
        self._get_client().put_object(
            Bucket=self.settings.r2_bucket,
            Key=key,
            Body=value.encode("utf-8"),
            ContentType=content_type,
        )
        return f"r2://{self.settings.r2_bucket}/{key}"

    def presign_get(self, key: str, expires_in: int = 900) -> str:
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.r2_bucket, "Key": key},
            ExpiresIn=expires_in,
        )


class CloudflareVectorizeIndex:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.vectorize_account_id and self.settings.vectorize_api_token and self.settings.vectorize_index)

    def check(self) -> str:
        if not self.configured:
            return "missing Cloudflare account, token, or Vectorize index"
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.vectorize_account_id}/vectorize/v2/indexes/{self.settings.vectorize_index}/info"
        )
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {self.settings.vectorize_api_token}"},
            timeout=provider_check_timeout(),
        )
        response.raise_for_status()
        return "connected to Cloudflare Vectorize index"

    def insert_vectors(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return {"success": True, "result": {"mutationId": None}}
        ndjson = "\n".join(json.dumps(record, separators=(",", ":")) for record in records) + "\n"
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.vectorize_account_id}/vectorize/v2/indexes/{self.settings.vectorize_index}/insert"
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.vectorize_api_token}",
                "Content-Type": "application/x-ndjson",
            },
            content=ndjson.encode("utf-8"),
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", False):
            raise RuntimeError(f"Vectorize insert failed: {data}")
        return data

    def insert_signature(self, signature: MemorySignature, object_ref: str | None = None) -> dict[str, Any]:
        values = self._vector_values(signature.latent_embedding)
        metadata = _clean_metadata(
            {
                "signature_id": signature.id,
                "provenance": signature.provenance,
                "modality": signature.modality.value,
                "object_ref": object_ref,
                "workspace_id": signature.workspace_id,
                "user_id": signature.user_id,
                "created_at": signature.created_at.isoformat(),
            }
        )
        return self.insert_vectors([{"id": signature.id, "values": values, "metadata": metadata}])

    def delete_signature(self, signature_id: str) -> dict[str, Any]:
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.vectorize_account_id}/vectorize/v2/indexes/{self.settings.vectorize_index}/delete"
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.vectorize_api_token}",
                "Content-Type": "application/json",
            },
            json={"ids": [signature_id]},
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", False):
            raise RuntimeError(f"Vectorize delete failed: {data}")
        return data

    def query_vectors(
        self,
        values: list[float],
        top_k: int = 8,
        return_metadata: str = "all",
        return_values: bool = False,
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.settings.vectorize_account_id}/vectorize/v2/indexes/{self.settings.vectorize_index}/query"
        )
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {self.settings.vectorize_api_token}",
                "Content-Type": "application/json",
            },
            json={
                "vector": self._vector_values(values),
                "topK": min(max(top_k, 1), 50),
                "returnValues": return_values,
                "returnMetadata": return_metadata,
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success", False):
            raise RuntimeError(f"Vectorize query failed: {data}")
        result = data.get("result") or {}
        matches = result.get("matches") or []
        return [match for match in matches if isinstance(match, dict)]

    def _vector_values(self, values: list[float]) -> list[float]:
        target = max(int(self.settings.vectorize_dimensions or 0), 0)
        if not target or len(values) == target:
            return values
        if len(values) > target:
            return _normalize(values[:target])
        return _normalize([*values, *([0.0] * (target - len(values)))])


class SupabasePostgresStore:
    """Supabase REST store. All persistence goes through the Supabase REST API.
    Direct Postgres / psycopg support has been removed — Supabase is the only
    storage backend.
    """

    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.supabase_url and self.settings.supabase_service_key)

    def _supabase_base_url(self) -> str:
        value = self.settings.supabase_url.strip().rstrip("/")
        for suffix in ("/rest/v1", "/auth/v1"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
        return value

    def _rest_url(self, table: str) -> str:
        return f"{self._supabase_base_url()}/rest/v1/{table}"

    def _rest_headers(self, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_service_key,
            "Authorization": f"Bearer {self.settings.supabase_service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def check(self) -> str:
        if not self.configured:
            return "missing SUPABASE_URL or SUPABASE_SERVICE_KEY"
        response = httpx.get(
            self._rest_url("signatures"),
            headers=self._rest_headers(),
            params={"select": "id", "limit": "1"},
            timeout=provider_check_timeout(),
        )
        response.raise_for_status()
        return "Supabase REST tables reachable"

    def save_signature(self, signature: MemorySignature) -> None:
        self._save_signature_rest(signature)

    def save_panel_items(self, items: list[TrainingPanelItem]) -> None:
        if not items:
            return
        self._save_panel_items_rest(items)

    def save_chat_exchange(
        self,
        user_id: str,
        workspace_id: str | None,
        thread_id: str,
        query: str,
        answer: str,
        trace_id: str,
        confidence: float,
        sources: list[str],
    ) -> None:
        title = query.strip().splitlines()[0][:120] if query.strip() else "Untitled thread"
        now = datetime.now(timezone.utc)
        assistant_at = now + timedelta(milliseconds=1)
        thread = {
            "id": thread_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "title": title,
            "updated_at": now.isoformat(),
        }
        messages = [
            {
                "id": f"{trace_id}:user",
                "thread_id": thread_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "role": "user",
                "content": query,
                "trace_id": trace_id,
                "confidence": None,
                "sources": [],
                "created_at": now.isoformat(),
            },
            {
                "id": f"{trace_id}:assistant",
                "thread_id": thread_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "role": "assistant",
                "content": answer,
                "trace_id": trace_id,
                "confidence": confidence,
                "sources": sources,
                "created_at": assistant_at.isoformat(),
            },
        ]
        self._save_chat_exchange_rest(thread, messages)

    def delete_signature(self, signature_id: str) -> None:
        self._delete_signature_rest(signature_id)

    def delete_panel_items_for_signature(self, signature_id: str) -> int:
        item_ids = [
            f"ingestion:{signature_id}",
            f"memory:{signature_id}",
        ]
        return self._delete_panel_items_for_signature_rest(signature_id, item_ids)

    def review_world_model_candidate(
        self,
        provenance: str,
        rule: str,
        action: str,
        corrected_rule: str | None = None,
    ) -> int:
        return self._review_world_model_candidate_rest(provenance, rule, action, corrected_rule)

    def list_panel_items(self, panel: str, cursor: str | None, limit: int) -> TrainingPanelPage:
        return self._list_panel_items_rest(panel, cursor, limit)

    def list_chat_threads(self, user_id: str, workspace_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        page_size = min(max(limit, 1), 100)
        return self._list_chat_threads_rest(user_id, workspace_id, page_size)

    def list_chat_messages(self, thread_id: str, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        page_size = min(max(limit, 1), 500)
        return self._list_chat_messages_rest(thread_id, user_id, page_size)

    def delete_chat_thread(self, thread_id: str, user_id: str) -> int:
        return self._delete_chat_thread_rest(thread_id, user_id)

    def list_recent_signatures(self, limit: int = 500) -> list[MemorySignature]:
        page_size = min(max(limit, 1), 2000)
        return self._list_recent_signatures_rest(page_size)

    def get_signatures_by_ids(self, ids: list[str]) -> list[MemorySignature]:
        unique_ids = [sig_id for sig_id in dict.fromkeys(ids) if sig_id]
        if not unique_ids:
            return []
        return self._get_signatures_by_ids_rest(unique_ids)

    def _save_signature_rest(self, signature: MemorySignature) -> None:
        payload = {
            "id": signature.id,
            "provenance": signature.provenance,
            "confidence": signature.confidence.score,
            "modality": signature.modality.value,
            "payload": signature.model_dump(mode="json"),
            "created_at": signature.created_at.isoformat(),
        }
        response = httpx.post(
            self._rest_url("signatures"),
            headers=self._rest_headers("resolution=merge-duplicates,return=minimal"),
            json=payload,
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()

    def _delete_signature_rest(self, signature_id: str) -> None:
        response = httpx.delete(
            self._rest_url("signatures"),
            headers=self._rest_headers(),
            params={"id": f"eq.{signature_id}"},
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()

    def _delete_panel_items_for_signature_rest(self, signature_id: str, item_ids: list[str]) -> int:
        filters = [
            f"id.in.({','.join(item_ids)})",
            f"payload->signature->>id.eq.{signature_id}",
            f"payload->>id.eq.{signature_id}",
            f"payload->>provenance.eq.{signature_id}",
            f"payload->>signature_id.eq.{signature_id}",
        ]
        response = httpx.delete(
            self._rest_url("training_panel_items"),
            headers=self._rest_headers("count=exact"),
            params={"or": f"({','.join(filters)})"},
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        content_range = response.headers.get("content-range", "")
        return _total_from_content_range(content_range, 0)

    def _review_world_model_candidate_rest(
        self,
        provenance: str,
        rule: str,
        action: str,
        corrected_rule: str | None,
    ) -> int:
        response = httpx.get(
            self._rest_url("training_panel_items"),
            headers=self._rest_headers(),
            params={
                "select": "id,panel,title,payload,created_at",
                "kind": "eq.world_model_candidate",
                "panel": "in.(review,world-model)",
                "payload->>provenance": f"eq.{provenance}",
                "or": f"(payload->>rule.eq.{rule},title.eq.{rule})",
                "limit": "100",
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        rows = response.json()
        if action == "reject":
            deleted = 0
            for row in rows:
                delete_response = httpx.delete(
                    self._rest_url("training_panel_items"),
                    headers=self._rest_headers(),
                    params={"id": f"eq.{row['id']}"},
                    timeout=provider_http_timeout(),
                )
                delete_response.raise_for_status()
                deleted += 1
            return deleted
        updated = 0
        for row in rows:
            payload = dict(row.get("payload") or {})
            final_rule = (corrected_rule or "").strip() if action == "correct" and corrected_rule else str(payload.get("rule") or rule)
            payload["rule"] = final_rule
            payload["review_required"] = action == "rollback"
            if action in {"accept", "promote", "correct"}:
                payload["review_required"] = False
            if action == "correct":
                payload["confidence"] = max(float(payload.get("confidence") or 0.0), 0.9)
            state = "review required" if payload.get("review_required") else "accepted"
            confidence = float(payload.get("confidence") or 0.0)
            patch_response = httpx.patch(
                self._rest_url("training_panel_items"),
                headers=self._rest_headers("return=minimal"),
                params={"id": f"eq.{row['id']}"},
                json={
                    "title": final_rule,
                    "subtitle": f"{state} / confidence {confidence:.2f} / {provenance}",
                    "payload": payload,
                },
                timeout=provider_http_timeout(),
            )
            patch_response.raise_for_status()
            updated += 1
        return updated

    def _save_panel_items_rest(self, items: list[TrainingPanelItem]) -> None:
        payload = [
            {
                "id": item.id,
                "panel": item.panel,
                "kind": item.kind,
                "title": item.title,
                "subtitle": item.subtitle,
                "payload": item.data,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ]
        response = httpx.post(
            self._rest_url("training_panel_items"),
            headers=self._rest_headers("resolution=merge-duplicates,return=minimal"),
            json=payload,
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()

    def _save_chat_exchange_rest(self, thread: dict[str, Any], messages: list[dict[str, Any]]) -> None:
        thread_response = httpx.post(
            self._rest_url("chat_threads"),
            headers=self._rest_headers("resolution=merge-duplicates,return=minimal"),
            json=thread,
            timeout=provider_http_timeout(),
        )
        thread_response.raise_for_status()
        message_response = httpx.post(
            self._rest_url("chat_messages"),
            headers=self._rest_headers("resolution=merge-duplicates,return=minimal"),
            json=messages,
            timeout=provider_http_timeout(),
        )
        message_response.raise_for_status()

    def save_user_feedback(self, feedback: dict[str, Any]) -> None:
        row = {
            "id": feedback["id"],
            "workspace_id": feedback["workspace_id"],
            "user_id": feedback.get("user_id"),
            "thread_id": feedback.get("thread_id"),
            "trace_id": feedback.get("trace_id"),
            "query": feedback.get("query"),
            "answer": feedback.get("answer"),
            "rating": feedback.get("rating"),
            "feedback": feedback.get("feedback"),
            "learn_this": feedback.get("learn_this", False),
            "payload": feedback.get("payload") or {},
            "created_at": feedback.get("created_at"),
        }
        response = httpx.post(
            self._rest_url("user_feedback"),
            headers=self._rest_headers("resolution=merge-duplicates,return=minimal"),
            json=row,
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()

    def _list_chat_threads_rest(self, user_id: str, workspace_id: str | None, limit: int) -> list[dict[str, Any]]:
        params = {
            "select": "id,workspace_id,user_id,title,created_at,updated_at",
            "user_id": f"eq.{user_id}",
            "order": "updated_at.desc,created_at.desc",
            "limit": str(limit),
        }
        if workspace_id:
            params["workspace_id"] = f"eq.{workspace_id}"
        response = httpx.get(
            self._rest_url("chat_threads"),
            headers=self._rest_headers(),
            params=params,
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        return response.json()

    def _list_chat_messages_rest(self, thread_id: str, user_id: str, limit: int) -> list[dict[str, Any]]:
        response = httpx.get(
            self._rest_url("chat_messages"),
            headers=self._rest_headers(),
            params={
                "select": "id,thread_id,workspace_id,user_id,role,content,trace_id,confidence,sources,created_at",
                "thread_id": f"eq.{thread_id}",
                "user_id": f"eq.{user_id}",
                "order": "created_at.asc,id.asc",
                "limit": str(limit),
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        return response.json()

    def _delete_chat_thread_rest(self, thread_id: str, user_id: str) -> int:
        message_response = httpx.delete(
            self._rest_url("chat_messages"),
            headers=self._rest_headers("count=exact"),
            params={"thread_id": f"eq.{thread_id}", "user_id": f"eq.{user_id}"},
            timeout=provider_http_timeout(),
        )
        message_response.raise_for_status()
        thread_response = httpx.delete(
            self._rest_url("chat_threads"),
            headers=self._rest_headers(),
            params={"id": f"eq.{thread_id}", "user_id": f"eq.{user_id}"},
            timeout=provider_http_timeout(),
        )
        thread_response.raise_for_status()
        return _total_from_content_range(message_response.headers.get("content-range", ""), 0)

    def _list_panel_items_rest(self, panel: str, cursor: str | None, limit: int) -> TrainingPanelPage:
        offset = max(int(cursor or "0"), 0)
        page_size = min(max(limit, 1), 100)
        response = httpx.get(
            self._rest_url("training_panel_items"),
            headers=self._rest_headers("count=exact"),
            params={
                "select": "id,panel,kind,title,subtitle,payload,created_at",
                "panel": f"eq.{panel}",
                "order": "created_at.desc,id.desc",
                "limit": str(page_size + 1),
                "offset": str(offset),
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        rows = response.json()
        visible = rows[:page_size]
        total = _total_from_content_range(response.headers.get("content-range", ""), len(rows))
        has_more = len(rows) > page_size
        return TrainingPanelPage(
            panel=panel,
            items=[
                TrainingPanelItem(
                    id=row["id"],
                    panel=row["panel"],
                    kind=row["kind"],
                    title=row["title"],
                    subtitle=row.get("subtitle") or "",
                    data=row.get("payload") or {},
                    created_at=row["created_at"],
                )
                for row in visible
            ],
            next_cursor=str(offset + page_size) if has_more else None,
            has_more=has_more,
            total=total,
        )

    def _list_recent_signatures_rest(self, limit: int) -> list[MemorySignature]:
        response = httpx.get(
            self._rest_url("signatures"),
            headers=self._rest_headers(),
            params={
                "select": "payload",
                "order": "created_at.desc,id.desc",
                "limit": str(limit),
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        signatures: list[MemorySignature] = []
        for row in response.json():
            payload = row.get("payload")
            if payload:
                signatures.append(MemorySignature.model_validate(payload))
        return signatures

    def _get_signatures_by_ids_rest(self, ids: list[str]) -> list[MemorySignature]:
        response = httpx.get(
            self._rest_url("signatures"),
            headers=self._rest_headers(),
            params={
                "select": "payload",
                "id": f"in.({','.join(ids)})",
            },
            timeout=provider_http_timeout(),
        )
        response.raise_for_status()
        by_id: dict[str, MemorySignature] = {}
        for row in response.json():
            payload = row.get("payload")
            if not payload:
                continue
            signature = MemorySignature.model_validate(payload)
            by_id[signature.id] = signature
        return [by_id[signature_id] for signature_id in ids if signature_id in by_id]


class Neo4jAuraGraphStore:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings
        self._driver: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.neo4j_uri and self.settings.neo4j_user and self.settings.neo4j_password)

    def _get_driver(self) -> Any:
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )
        return self._driver

    def check(self) -> str:
        if not self.configured:
            return "missing Neo4j Aura URI, user, or password"
        self._get_driver().verify_connectivity()
        return "connected to Neo4j"

    def upsert_signature(self, signature: MemorySignature) -> None:
        payload = signature.model_dump(mode="json")
        with self._get_driver().session(database=self.settings.neo4j_database) as session:
            session.run(
                """
                MERGE (s:MemorySignature {id: $id})
                SET s.provenance = $provenance,
                    s.confidence = $confidence,
                    s.modality = $modality,
                    s.raw_excerpt = $raw_excerpt,
                    s.created_at = datetime($created_at)
                """,
                id=signature.id,
                provenance=signature.provenance,
                confidence=signature.confidence.score,
                modality=signature.modality.value,
                raw_excerpt=signature.raw_excerpt,
                created_at=signature.created_at.isoformat(),
            )
            session.run(
                """
                MATCH (s:MemorySignature {id: $signature_id})
                UNWIND $entities AS entity
                MERGE (e:Entity {id: entity.id})
                SET e.name = entity.name, e.type = entity.type
                MERGE (s)-[:MENTIONS]->(e)
                """,
                signature_id=signature.id,
                entities=payload["structured"]["entities"],
            )
            session.run(
                """
                UNWIND $relations AS relation
                MERGE (source:Entity {name: relation.subject})
                MERGE (target:Entity {name: relation.object})
                MERGE (source)-[r:RELATION {predicate: relation.predicate, source_signature: $signature_id}]->(target)
                SET r.confidence = relation.confidence
                """,
                signature_id=signature.id,
                relations=payload["structured"]["relations"],
            )
            session.run(
                """
                UNWIND $causal AS link
                MERGE (cause:Entity {name: link.cause})
                MERGE (effect:Entity {name: link.effect})
                MERGE (cause)-[r:CAUSES {source_signature: $signature_id}]->(effect)
                SET r.confidence = link.confidence
                """,
                signature_id=signature.id,
                causal=payload["structured"]["causal_chain"],
            )


class RedisCeleryQueue:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings
        self._app: Any | None = None
        self._redis: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.redis_url)

    def _get_app(self) -> Any:
        if self._app is None:
            from celery import Celery

            self._app = Celery("jimsai", broker=self.settings.redis_url, backend=self.settings.redis_url)
            self._app.conf.task_default_queue = "jimsai-training"
        return self._app

    def check(self) -> str:
        if not self.configured:
            return "missing REDIS_URL"
        client = self._get_redis()
        client.ping()
        self._get_app()
        return "Redis ping succeeded; Celery broker/result backend configured"

    def enqueue(self, task_name: str, payload: dict[str, Any]) -> str:
        result = self._get_app().send_task(task_name, kwargs={"payload": payload})
        return str(result.id)

    def _get_redis(self) -> Any:
        if self._redis is None:
            import redis

            self._redis = redis.Redis.from_url(self.settings.redis_url, socket_connect_timeout=provider_check_timeout(), socket_timeout=provider_http_timeout())
        return self._redis

    def get_json(self, key: str) -> dict[str, Any] | None:
        value = self._get_redis().get(key)
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        data = json.loads(value)
        return data if isinstance(data, dict) else None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int = 86400) -> None:
        self._get_redis().setex(key, ttl_seconds, json.dumps(value, separators=(",", ":"), sort_keys=True))


class ExternalMultimodalEncoderAdapter:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._base_url())

    def _base_url(self) -> str:
        return self.settings.embedding_service_url.strip().rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = self.settings.embedding_service_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def check(self) -> str:
        if not self.configured:
            return "missing JIMS_EMBEDDING_SERVICE_URL"
        try:
            response = httpx.get(
                f"{self._base_url()}/health",
                headers=self._headers(),
                timeout=8,  # Fast check — Modal cold-start handled by retry in _ensure_adapter
            )
            response.raise_for_status()
            return "external embedding service reachable"
        except Exception as exc:
            # Raise so _ensure_adapter marks it unavailable and retries on next call
            raise

    async def encode(self, content: str, modality: Modality) -> list[float]:
        """Embed content using the Modal Embedding Service /embed endpoint.

        Async — uses httpx.AsyncClient so the event loop is never blocked.
        Real embeddings only. Returns [] on failure; caller marks reembedding_required=True.

        Model selection per modality:
          - CODE  -> codebert                 (768-d, code-aware)
          - DATA  -> jina-v3                  (768-d, when JIMS_JINA_EMBEDDINGS_ENABLED=true)
          - other -> multilingual-e5-small    (768-d, multilingual semantic)
        """
        if not self.configured:
            return []
        base = self._base_url()
        headers = self._headers()

        jina_enabled = os.getenv("JIMS_JINA_EMBEDDINGS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        if modality == Modality.CODE:
            model_id = "codebert"
            purpose = "document"
        elif modality == Modality.DATA and jina_enabled:
            model_id = "jina-v3"
            purpose = "document"
        else:
            model_id = "multilingual-e5-small"
            purpose = "query" if modality == Modality.TEXT else "document"

        target_timeout = float(
            os.getenv("JIMS_L1_EMBEDDING_TIMEOUT")
            or os.getenv("JIMS_INTERACTIVE_EMBEDDING_TIMEOUT")
            or "5"
        )
        try:
            timeout_cap = float(os.getenv("JIMS_INTERACTIVE_SERVICE_TIMEOUT_CAP", "6") or "6")
        except ValueError:
            timeout_cap = 6.0
        if timeout_cap > 0:
            target_timeout = min(target_timeout, timeout_cap)

        try:
            max_attempts = max(1, int(os.getenv("JIMS_EMBEDDING_MAX_ATTEMPTS", "1") or "1"))
        except ValueError:
            max_attempts = 1
        for attempt in range(max_attempts):
            try:
                attempt_timeout = target_timeout if attempt == 0 else min(target_timeout * 1.5, target_timeout + 5.0)
                async with httpx.AsyncClient(timeout=attempt_timeout) as client:
                    response = await asyncio.wait_for(
                        client.post(
                            f"{base}/embed",
                            headers=headers,
                            json={
                                "texts": [content[:16000]],
                                "model": model_id,
                                "purpose": purpose,
                            },
                        ),
                        timeout=max(attempt_timeout, 0.25),
                    )
                response.raise_for_status()
                vector = self._extract_vector(response.json())
                if vector:
                    return vector
                logger.warning(
                    "Embedding service returned 200 but no vector (model=%s, content_len=%d)",
                    model_id, len(content),
                )
                return []
            except Exception as exc:
                if attempt < max_attempts - 1:
                    logger.warning(
                        "Embedding attempt %d/%d failed: %s — retrying",
                        attempt + 1, max_attempts, exc,
                    )
                    continue
                logger.error(
                    "All %d embedding attempts failed (model=%s, content_len=%d). "
                    "Signature will be marked reembedding_required=True.",
                    max_attempts, model_id, len(content),
                )
                return []
        return []

    def embed_batch(
        self,
        texts: list[str],
        purpose: str = "document",
        model_id: str | None = None,
    ) -> list[list[float]]:
        """Embed a batch of texts using the HF Space /v1/embed endpoint.

        Uses the same retry logic as encode(). Each text is embedded
        independently. Returns a list of vectors in the same order;
        failed items return empty list [] so the caller can detect them.

        Args:
            texts: List of text strings to embed.
            purpose: 'document' for storage, 'query' for retrieval.
            model_id: Override model. Defaults to 
                      (intfloat/multilingual-e5-small).
                      Set `model_id='jinaai/jina-embeddings-v3'` when
                      `JIMS_JINA_EMBEDDINGS_ENABLED=true` and the Space
                      confirms support.
        """
        if not self.configured or not texts:
            return [[] for _ in texts]

        base = self._base_url()
        headers = self._headers()
        resolved_model = model_id or "multilingual-e5-small"
        target_timeout = float(os.getenv("JIMS_MULTIMODAL_ENCODER_TIMEOUT", "30") or "30")

        results: list[list[float]] = []
        for text in texts:
            for attempt in range(2):
                try:
                    timeout = target_timeout if attempt == 0 else 45.0
                    response = httpx.post(
                        f"{base}/embed",
                        headers=headers,
                        json={
                            "texts": [text[:16000]],
                            "model": resolved_model,
                            "purpose": purpose,
                        },
                        timeout=timeout,
                    )
                    response.raise_for_status()
                    results.append(self._extract_vector(response.json()))
                    break
                except Exception:
                    if attempt == 1:
                        logger.warning(
                            "embed_batch: embedding service unavailable for item, using empty vector"
                        )
                        results.append([])
                    continue
        return results

    def _extract_vector(self, payload: Any) -> list[float]:
        vector = payload
        if isinstance(payload, dict):
            vector = (
                payload.get("embedding")
                or (payload.get("embeddings")[0] if isinstance(payload.get("embeddings"), list) and payload.get("embeddings") else None)
                or payload.get("vector")
                or payload.get("values")
                or payload.get("latent_embedding")
            )
            if vector is None and isinstance(payload.get("data"), list) and payload["data"]:
                first = payload["data"][0]
                if isinstance(first, dict):
                    vector = first.get("embedding") or first.get("vector") or first.get("values")
            if vector is None and isinstance(payload.get("vectors"), list) and payload["vectors"]:
                vector = payload["vectors"][0]
        if not isinstance(vector, list):
            return []
        try:
            return _normalize([float(value) for value in vector])
        except (TypeError, ValueError):
            return []


class KaggleBatchMultimodalAdapter:
    def __init__(self, settings: ProductionSettings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(os.getenv("KAGGLE_API_TOKEN", "").strip() and self._dataset_owner() and self._kagglehub_available())

    def check(self) -> str:
        if not self._kagglehub_available():
            raise RuntimeError("kagglehub unavailable for batch multimodal handoff")
        if not os.getenv("KAGGLE_API_TOKEN", "").strip():
            raise RuntimeError("missing KAGGLE_API_TOKEN for KaggleHub batch multimodal handoff")
        if not self._dataset_owner():
            raise RuntimeError("missing KAGGLE_DATASET_OWNER or KAGGLE_USERNAME for KaggleHub dataset handles")
        return "KaggleHub batch multimodal handoff configured; realtime encode is intentionally unavailable"

    def encode(self, content: str, modality: Modality) -> list[float]:
        return []

    def _dataset_owner(self) -> str:
        return os.getenv("KAGGLE_DATASET_OWNER", "").strip() or os.getenv("KAGGLE_USERNAME", "").strip()

    def _kagglehub_available(self) -> bool:
        try:
            import kagglehub  # noqa: F401
        except Exception:
            return False
        return True


class ProductionRuntime:
    def __init__(self, settings: ProductionSettings | None = None) -> None:
        self.settings = settings or ProductionSettings.from_env()
        self.statuses: dict[str, ProviderStatus] = {}
        self.r2 = R2ObjectStore(self.settings) if self.settings.enable_r2 else None
        self.vectorize = CloudflareVectorizeIndex(self.settings) if self.settings.enable_vectorize else None
        self.postgres = SupabasePostgresStore(self.settings)  # always Supabase REST
        self.neo4j = Neo4jAuraGraphStore(self.settings) if self.settings.enable_neo4j else None
        self.celery = RedisCeleryQueue(self.settings) if self.settings.enable_celery else None
        self.multimodal = self._build_multimodal_adapter()
        # Lazy initialization: _initialized = False means _ensure_initialized()
        # will connect to external providers on first actual use, not at startup.
        # This cuts Lambda cold start from 60â€“150s to <5s.
        self._initialized = False
        self._checked_adapters: set[str] = set()
        # Circuit breaker: monotonic timestamp of the last failed check per provider.
        # While within the cooldown window we skip re-probing a known-down provider
        # so a persistently unavailable mirror does not add its connect/DNS timeout
        # to every single request. After the cooldown it is retried, so recovery is
        # automatic when the provider comes back.
        self._provider_failed_at: dict[str, float] = {}
        self._provider_retry_cooldown = float(os.getenv("JIMS_PROVIDER_RETRY_COOLDOWN", "60") or "60")
        # Pre-populate statuses as "not yet checked" so readiness() always works
        for name in ("r2", "vectorize", "supabase_postgres", "neo4j_aura", "redis_celery", "multimodal_encoders"):
            self.statuses[name] = ProviderStatus(
                name=name, configured=False, available=False, detail="pending"
            )

    def _ensure_initialized(self) -> None:
        """Connect to external providers on first use. Thread-safe for Lambda (single-process)."""
        if self._initialized:
            return
        self._initialized = True
        self._initialize()

    def _ensure_adapter(self, name: str, adapter: Any | None, enforce_strict: bool = False) -> None:
        """Connect one provider without blocking hot paths on unrelated providers.

        Successfully checked adapters are cached permanently.
        Failed adapters are retried on subsequent calls so transient startup
        errors (e.g. first-request cold-start) don't permanently disable a provider.

        ``enforce_strict`` only applies to the explicit startup/readiness path
        (``_initialize``). When set with ``JIMS_STRICT_PROVIDER_STARTUP=true`` a
        provider check failure is fatal — a deliberate *deploy-time* gate. Runtime
        request paths call this with enforce_strict=False so a non-critical mirror
        provider that pauses mid-life (e.g. an auto-paused Neo4j Aura / Vectorize
        instance) degrades gracefully to in-memory operation instead of failing the
        whole request. Availability-first is the correct posture for a runtime that
        must keep handling tasks even while a secondary provider is unreachable.
        """
        # Always skip if already confirmed available
        if name in self._checked_adapters and self.statuses.get(name) and self.statuses[name].available:
            return
        # Also skip if adapter is None (will never change)
        if name in self._checked_adapters and adapter is None:
            return
        # Circuit breaker: if this provider failed recently, stay degraded without
        # paying its connect/DNS timeout again until the cooldown elapses.
        failed_at = self._provider_failed_at.get(name)
        if failed_at is not None and (time.monotonic() - failed_at) < self._provider_retry_cooldown:
            return
        self._checked_adapters.add(name)
        if adapter is None:
            self.statuses[name] = ProviderStatus(name=name, configured=False, available=False, detail="disabled")
            return
        configured = bool(adapter.configured)
        try:
            detail = adapter.check()
            self.statuses[name] = ProviderStatus(name=name, configured=configured, available=configured, detail=detail)
            self._provider_failed_at.pop(name, None)  # recovered — clear breaker
        except Exception as exc:
            self.statuses[name] = ProviderStatus(name=name, configured=configured, available=False, detail=str(exc))
            # Remove from checked set so failed adapters are retried after cooldown
            self._checked_adapters.discard(name)
            self._provider_failed_at[name] = time.monotonic()
            # Only the authoritative store (Supabase signatures) may be fatal under
            # strict mode. Secondary mirrors/indexes (Neo4j graph, Vectorize, R2,
            # Redis) always degrade gracefully — a paused mirror must never take the
            # whole runtime down, otherwise the system cannot keep handling tasks
            # while a non-critical provider is unreachable.
            if enforce_strict and self.settings.strict_provider_startup and name == "supabase_postgres":
                raise

    @property
    def enabled(self) -> bool:
        return any([self.r2, self.vectorize, self.postgres, self.neo4j, self.celery, self.multimodal])

    def _build_multimodal_adapter(self) -> Any | None:
        if not self.settings.enable_multimodal_encoders:
            return None
        mode = self.settings.effective_multimodal_encoder_mode
        if mode == "external":
            return ExternalMultimodalEncoderAdapter(self.settings)
        if mode == "kaggle_batch":
            return KaggleBatchMultimodalAdapter(self.settings)
        return None

    def _initialize(self) -> None:
        for name, adapter in [
            ("r2", self.r2),
            ("vectorize", self.vectorize),
            ("supabase_postgres", self.postgres),
            ("neo4j_aura", self.neo4j),
            ("redis_celery", self.celery),
            ("multimodal_encoders", self.multimodal),
        ]:
            # Startup/readiness path honors JIMS_STRICT_PROVIDER_STARTUP as a deploy gate.
            self._ensure_adapter(name, adapter, enforce_strict=True)

    def readiness(self) -> dict[str, str | bool]:
        # Trigger lazy init so readiness() always reflects actual state
        self._ensure_initialized()
        data: dict[str, str | bool] = {
            "storage_backend": "supabase_rest",
            "graph_provider": self.settings.graph_provider,
            "production_runtime_enabled": self.enabled,
            "cloud_authoritative": self.settings.cloud_authoritative,
            "multimodal_encoder_mode": self.settings.effective_multimodal_encoder_mode,
            "multimodal_configured": bool(self.multimodal and self.multimodal.configured),
        }
        for name, status in self.statuses.items():
            data[f"{name}_configured"] = status.configured
            data[f"{name}_available"] = status.available
            data[f"{name}_detail"] = status.detail
        return data

    def save_training_ingest(
        self,
        signature: MemorySignature,
        raw_content: str,
        panel_items: list[TrainingPanelItem],
    ) -> None:
        object_ref: str | None = None
        self._ensure_adapter("r2", self.r2)
        if self.r2 and self.statuses["r2"].available:
            object_ref = self._attempt("r2", lambda: self.r2.put_text(f"training/{signature.id}.txt", raw_content))
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt("supabase_postgres", lambda: self.postgres.save_signature(signature))
            if panel_items:
                self._attempt("supabase_postgres", lambda: self.postgres.save_panel_items(panel_items))
        self._ensure_adapter("neo4j_aura", self.neo4j)
        if self.neo4j and self.statuses["neo4j_aura"].available:
            self._attempt("neo4j_aura", lambda: self.neo4j.upsert_signature(signature))
        self._ensure_adapter("vectorize", self.vectorize)
        if self.vectorize and self.statuses["vectorize"].available and signature.latent_embedding:
            self._attempt("vectorize", lambda: self.vectorize.insert_signature(signature, object_ref=object_ref))

    def save_memory_signature(self, signature: MemorySignature) -> None:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt("supabase_postgres", lambda: self.postgres.save_signature(signature))
        self._ensure_adapter("vectorize", self.vectorize)
        if self.vectorize and self.statuses["vectorize"].available and signature.latent_embedding:
            self._attempt("vectorize", lambda: self.vectorize.insert_signature(signature, object_ref=None))

    def save_panel_items(self, panel_items: list[TrainingPanelItem]) -> None:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt("supabase_postgres", lambda: self.postgres.save_panel_items(panel_items))

    def save_user_feedback(self, feedback: dict[str, Any]) -> None:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt("supabase_postgres", lambda: self.postgres.save_user_feedback(feedback))

    def save_chat_exchange(
        self,
        user_id: str,
        workspace_id: str | None,
        thread_id: str,
        query: str,
        answer: str,
        trace_id: str,
        confidence: float,
        sources: list[str],
    ) -> None:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt(
                "supabase_postgres",
                lambda: self.postgres.save_chat_exchange(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    query=query,
                    answer=answer,
                    trace_id=trace_id,
                    confidence=confidence,
                    sources=sources,
                ),
            )

    def list_chat_threads(self, user_id: str, workspace_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self._attempt("supabase_postgres", lambda: self.postgres.list_chat_threads(user_id, workspace_id, limit)) or []
        return []

    def list_chat_messages(self, thread_id: str, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self._attempt("supabase_postgres", lambda: self.postgres.list_chat_messages(thread_id, user_id, limit)) or []
        return []

    def delete_chat_thread(self, thread_id: str, user_id: str) -> int:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self._attempt("supabase_postgres", lambda: self.postgres.delete_chat_thread(thread_id, user_id)) or 0
        return 0

    def delete_signature(self, signature_id: str) -> None:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            self._attempt("supabase_postgres", lambda: self.postgres.delete_signature(signature_id))
        if self.vectorize and self.statuses["vectorize"].available:
            self._attempt("vectorize", lambda: self.vectorize.delete_signature(signature_id))

    def delete_panel_items_for_signature(self, signature_id: str) -> int:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self._attempt("supabase_postgres", lambda: self.postgres.delete_panel_items_for_signature(signature_id)) or 0
        return 0

    def review_world_model_candidate(self, provenance: str, rule: str, action: str, corrected_rule: str | None = None) -> int:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            return (
                self._attempt(
                    "supabase_postgres",
                    lambda: self.postgres.review_world_model_candidate(provenance, rule, action, corrected_rule),
                )
                or 0
            )
        return 0

    def list_panel_items(self, panel: str, cursor: str | None, limit: int) -> TrainingPanelPage | None:
        self._ensure_initialized()
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self.postgres.list_panel_items(panel, cursor, limit)
        return None

    def load_recent_signatures(self, limit: int = 500) -> list[MemorySignature]:
        self._ensure_adapter("supabase_postgres", self.postgres)
        if self.postgres and self.statuses["supabase_postgres"].available:
            return self._attempt("supabase_postgres", lambda: self.postgres.list_recent_signatures(limit)) or []
        return []

    def retrieve_similar(
        self,
        latent_embedding: list[float],
        limit: int = 8,
        workspace_id: str | None = None,
        user_id: str | None = None,
        exclude_ids: set[str] | None = None,
        vector_context_id: str | None = None,
    ) -> list[MemorySignature]:
        if not latent_embedding:
            return []
        # Retrieval only needs Vectorize + Supabase — multimodal adapter not required here
        self._ensure_adapter("vectorize", self.vectorize)
        self._ensure_adapter("supabase_postgres", self.postgres)
        if not (
            self.vectorize
            and self.statuses["vectorize"].available
            and self.postgres
            and self.statuses["supabase_postgres"].available
        ):
            return []
        exclude_ids = exclude_ids or set()
        matches = self._attempt("vectorize", lambda: self.vectorize.query_vectors(latent_embedding, top_k=max(limit * 3, limit)))
        if not matches:
            return []
        match_by_id: dict[str, dict[str, Any]] = {
            str(match.get("id") or ""): match
            for match in matches
            if str(match.get("id") or "")
        }
        ids = list(match_by_id.keys())
        if not ids:
            return []
        signatures = self._attempt("supabase_postgres", lambda: self.postgres.get_signatures_by_ids(ids)) or []
        rank_by_id = {sid: rank for rank, sid in enumerate(ids)}
        visible: list[MemorySignature] = []
        for signature in signatures:
            if signature.id in exclude_ids or not self._visible_to_scope(signature, workspace_id=workspace_id, user_id=user_id):
                continue
            hydrated = signature.model_copy(deep=True)
            hydrated.metadata = dict(hydrated.metadata or {})
            match = match_by_id.get(signature.id) or {}
            try:
                score = float(match.get("score", 0.0) or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            hydrated.metadata["vector_retrieved"] = True
            hydrated.metadata["vector_retrieval_score"] = score
            hydrated.metadata["vector_retrieval_rank"] = rank_by_id.get(signature.id, len(rank_by_id))
            if vector_context_id:
                hydrated.metadata["vector_retrieval_context"] = vector_context_id
            visible.append(hydrated)
        visible.sort(key=lambda signature: int(signature.metadata.get("vector_retrieval_rank", len(visible))))
        return visible[:limit]

    def enqueue(self, task_name: str, payload: dict[str, Any]) -> str | None:
        self._ensure_initialized()
        if self.celery and self.statuses["redis_celery"].available:
            return self._attempt("redis_celery", lambda: self.celery.enqueue(task_name, payload))
        return None

    def load_session(self, user_id: str) -> dict[str, str]:
        self._ensure_adapter("redis_celery", self.celery)
        if self.celery and self.statuses["redis_celery"].available:
            data = self._attempt("redis_celery", lambda: self.celery.get_json(f"session:{user_id}"))
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        return {}

    def save_session(self, user_id: str, session: dict[str, str]) -> None:
        self._ensure_adapter("redis_celery", self.celery)
        if self.celery and self.statuses["redis_celery"].available:
            self._attempt("redis_celery", lambda: self.celery.set_json(f"session:{user_id}", session))

    def _visible_to_scope(self, signature: MemorySignature, workspace_id: str | None, user_id: str | None) -> bool:
        if signature.metadata.get("validity") in {"superseded", "deleted", "invalid"}:
            return False
        if signature.workspace_id and workspace_id and signature.workspace_id != workspace_id:
            return False
        if signature.workspace_id and not workspace_id:
            return False
        if not signature.workspace_id and signature.user_id and user_id and signature.user_id != user_id:
            return False
        if not signature.workspace_id and signature.user_id and not user_id:
            return False
        return True

    def _attempt(self, provider: str, action: Any) -> Any:
        try:
            return action()
        except Exception as exc:
            status = self.statuses[provider]
            self.statuses[provider] = ProviderStatus(
                name=status.name,
                configured=status.configured,
                available=False,
                detail=str(exc),
            )
            return None

