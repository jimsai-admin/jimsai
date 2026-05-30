from __future__ import annotations

import logging
from time import perf_counter
from typing import Callable

from fastapi import Request, Response


def configure_logger(name: str, level: str = "INFO") -> logging.Logger:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    return logging.getLogger(name)


async def trace_middleware(request: Request, call_next: Callable):
    start = perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = (perf_counter() - start) * 1000
    response.headers["x-jimsai-trace-ms"] = f"{elapsed_ms:.3f}"
    response.headers["x-jimsai-deterministic"] = "true"
    return response
