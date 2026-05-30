from __future__ import annotations

import os
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from celery import Celery

from .provider_adapters import redis_url_from_env

REDIS_URL = redis_url_from_env()
if not REDIS_URL:
    raise RuntimeError("REDIS_URL or REDIS_PUBLIC_ENDPOINT/REDIS_API is required for Celery")
celery_app = Celery("jimsai", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_default_queue = "jimsai-training"
celery_app.conf.result_backend_transport_options = {
    "global_keyprefix": os.getenv("JIMS_CELERY_KEY_PREFIX", "jimsai_"),
    "retry_policy": {"timeout": 5.0},
}


@celery_app.task(name="jimsai.training.process_canvas")
def process_canvas(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "accepted",
        "task": "canvas",
        "dataset_ref": payload.get("dataset_ref"),
        "scope": payload.get("scope"),
    }


@celery_app.task(name="jimsai.training.process_invention")
def process_invention(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "accepted",
        "task": "invention",
        "goal": payload.get("goal"),
        "domain": payload.get("domain"),
    }
