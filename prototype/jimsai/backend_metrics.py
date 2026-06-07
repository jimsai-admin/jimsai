"""
backend_metrics.py — Lightweight metrics singleton for the JIMS-AI FastAPI backend.

Tracks request count, latency, and first-token latency relayed from Renderer_Service.
Exposes Prometheus text format via render_backend_metrics().

Requirements: 14.4, 24.6, 28.1, 29.6, 29.8
"""
from __future__ import annotations

import statistics
import threading
import time

_start_time = time.time()
_lock = threading.Lock()
_request_count: int = 0
_latency_samples: list[float] = []
_first_token_samples: list[float] = []


def record_request(latency_ms: float) -> None:
    """Record an end-to-end request latency sample."""
    global _request_count
    with _lock:
        _request_count += 1
        _latency_samples.append(latency_ms)


def record_first_token(latency_ms: float) -> None:
    """Record a first-token latency sample relayed from Renderer_Service."""
    with _lock:
        _first_token_samples.append(latency_ms)


def get_uptime() -> int:
    """Return seconds since backend process started."""
    return int(time.time() - _start_time)


def _pct(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = min(int(p * len(s)), len(s) - 1)
    return s[idx]


def render_backend_metrics() -> str:
    """Render Prometheus text format metrics for the backend service."""
    with _lock:
        rc = _request_count
        lat_p50 = statistics.median(_latency_samples) if _latency_samples else 0.0
        lat_p99 = _pct(_latency_samples, 0.99)
        ft_p50 = statistics.median(_first_token_samples) if _first_token_samples else 0.0
        ft_p99 = _pct(_first_token_samples, 0.99)

    lines = [
        "# HELP jimsai_requests_total Total requests processed by backend",
        "# TYPE jimsai_requests_total counter",
        f'jimsai_requests_total{{service="backend"}} {rc}',
        "# HELP jimsai_request_latency_p50_ms P50 backend request latency ms",
        "# TYPE jimsai_request_latency_p50_ms gauge",
        f'jimsai_request_latency_p50_ms{{service="backend"}} {lat_p50:.2f}',
        "# HELP jimsai_request_latency_p99_ms P99 backend request latency ms",
        "# TYPE jimsai_request_latency_p99_ms gauge",
        f'jimsai_request_latency_p99_ms{{service="backend"}} {lat_p99:.2f}',
        "# HELP jimsai_first_token_ms_p50 P50 first-token latency ms (from Renderer)",
        "# TYPE jimsai_first_token_ms_p50 gauge",
        f'jimsai_first_token_ms_p50{{service="backend"}} {ft_p50:.2f}',
        "# HELP jimsai_first_token_ms_p99 P99 first-token latency ms (from Renderer)",
        "# TYPE jimsai_first_token_ms_p99 gauge",
        f'jimsai_first_token_ms_p99{{service="backend"}} {ft_p99:.2f}',
    ]
    return "\n".join(lines) + "\n"


def get_health_payload() -> dict:
    """Return extended health payload for the backend. Requirements: 28.1, 28.2"""
    return {
        "status": "healthy",
        "service": "backend",
        "models_loaded": True,   # backend has no models — always True
        "container_uptime": get_uptime(),
        "gpu_available": False,  # backend is CPU-only
        "volume_mounted": False, # backend has no volume
    }
