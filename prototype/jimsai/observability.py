from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from .models import TraceEvent


def configure_logging(service_name: str, level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return logging.getLogger(service_name)


class ExecutionTracer:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def add(self, stage: str, message: str, **data: Any) -> None:
        self.events.append(TraceEvent(stage=stage, message=message, data=data))

    def hash(self) -> str:
        payload = [
            {"stage": e.stage, "message": e.message, "data": e.data}
            for e in self.events
        ]
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
