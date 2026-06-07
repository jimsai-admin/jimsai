"""
Prometheus-compatible metrics collector for JIMS-AI Modal services.

Provides thread-safe counters and latency histograms used by all five
Modal AI services (Embedding, Classification, Intent, Renderer, Reasoning)
and the Backend. Exposes metrics in Prometheus text format (text/plain;
version=0.0.4) via render_prometheus_text().

Requirements: 29.1, 29.2, 29.3, 29.4, 29.5, 29.6, 29.7
"""

from __future__ import annotations

import statistics
import threading
from typing import Optional


class LatencyHistogram:
    """Thread-safe latency sample accumulator (milliseconds).

    Stores raw float samples and computes P50/P99 percentiles on demand.
    Suitable for embedding latency, first-token latency, total generation
    latency, TPS samples, and batch-size distributions.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[float] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def record(self, value_ms: float) -> None:
        """Append *value_ms* to the sample list (thread-safe)."""
        with self._lock:
            self._samples.append(value_ms)

    def reset(self) -> None:
        """Clear all samples (thread-safe)."""
        with self._lock:
            self._samples.clear()

    # ------------------------------------------------------------------
    # Read-only
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the number of recorded samples."""
        with self._lock:
            return len(self._samples)

    def p50(self) -> float:
        """Return the 50th percentile (median).

        Returns 0.0 when no samples have been recorded.
        """
        with self._lock:
            if not self._samples:
                return 0.0
            return statistics.median(self._samples)

    def p99(self) -> float:
        """Return the 99th percentile.

        Uses the floor index ``int(0.99 * len(samples))`` on the sorted
        sample list — consistent with the Prometheus summary convention.
        Returns 0.0 when no samples have been recorded.
        """
        with self._lock:
            if not self._samples:
                return 0.0
            sorted_samples = sorted(self._samples)
            idx = int(0.99 * len(sorted_samples))
            # Clamp to valid index range
            idx = min(idx, len(sorted_samples) - 1)
            return sorted_samples[idx]


class Counter:
    """Thread-safe monotonically incrementing integer counter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: int = 0

    def increment(self, n: int = 1) -> None:
        """Add *n* to the counter (thread-safe, default n=1)."""
        with self._lock:
            self._value += n

    def value(self) -> int:
        """Return the current counter value."""
        with self._lock:
            return self._value

    def reset(self) -> None:
        """Reset the counter to zero (thread-safe)."""
        with self._lock:
            self._value = 0


# ---------------------------------------------------------------------------
# ServiceMetrics
# ---------------------------------------------------------------------------

class ServiceMetrics:
    """Per-service metrics container.

    Instantiate once at module level via :func:`create_metrics`.  The
    ``is_gpu_service`` flag controls whether first-token and generation
    latency histograms are allocated (Renderer_Service, Reasoning_Service).
    The ``is_embedding_service`` flag controls whether the batch-size
    histogram is allocated (Embedding_Service).

    Parameters
    ----------
    service_name:
        Human-readable service identifier used as the ``service`` label in
        Prometheus metric lines (e.g. ``"embedding"``, ``"renderer"``).
    is_gpu_service:
        Set to ``True`` for Renderer_Service and Reasoning_Service so that
        first-token latency, total generation latency, and TPS histograms
        are created.
    is_embedding_service:
        Set to ``True`` for Embedding_Service so that the batch-size
        histogram is created.
    """

    def __init__(
        self,
        service_name: str,
        *,
        is_gpu_service: bool = False,
        is_embedding_service: bool = False,
    ) -> None:
        self.service_name = service_name

        # Universal metrics (all services)
        self.request_count = Counter()
        self.request_latency = LatencyHistogram()

        # model_key → load duration in ms; populated once at container startup
        self.model_load_duration: dict[str, float] = {}

        # GPU-service-only metrics (Renderer, Reasoning)
        self._is_gpu_service = is_gpu_service
        if is_gpu_service:
            self.first_token_latency = LatencyHistogram()
            self.total_generation_latency = LatencyHistogram()
            self.tokens_per_second = LatencyHistogram()  # stores TPS samples

        # Embedding-service-only metrics
        self._is_embedding_service = is_embedding_service
        if is_embedding_service:
            self.batch_size_histogram = LatencyHistogram()  # records batch sizes

    # ------------------------------------------------------------------
    # Convenience recording methods
    # ------------------------------------------------------------------

    def record_request(self, latency_ms: float) -> None:
        """Increment the request counter and record end-to-end latency."""
        self.request_count.increment()
        self.request_latency.record(latency_ms)

    def record_model_load(self, model_key: str, duration_ms: float) -> None:
        """Store the model load duration for *model_key*.

        Called once per model per container startup.  Satisfies Req 29.7.
        """
        self.model_load_duration[model_key] = duration_ms

    def record_first_token(self, latency_ms: float) -> None:
        """Record time-to-first-token in ms.

        No-op if this is not a GPU service (Renderer / Reasoning).
        """
        if self._is_gpu_service:
            self.first_token_latency.record(latency_ms)

    def record_generation(self, total_ms: float, tokens: int) -> None:
        """Record total generation latency and derive tokens-per-second.

        Parameters
        ----------
        total_ms:
            Wall-clock time from request start to last token (milliseconds).
        tokens:
            Number of tokens produced in the generation pass.

        No-op if this is not a GPU service.
        """
        if not self._is_gpu_service:
            return
        self.total_generation_latency.record(total_ms)
        if total_ms > 0 and tokens > 0:
            tps = tokens / (total_ms / 1000.0)
            self.tokens_per_second.record(tps)


# ---------------------------------------------------------------------------
# Prometheus text renderer
# ---------------------------------------------------------------------------

def render_prometheus_text(metrics: ServiceMetrics) -> str:
    """Render *metrics* as a Prometheus text exposition document.

    Output format: ``text/plain; version=0.0.4``.
    Each metric block consists of a ``# HELP`` line, a ``# TYPE`` line,
    and one or more metric lines.  The document always ends with a
    trailing newline.

    Requirements: 29.1–29.7
    """
    service = metrics.service_name
    lines: list[str] = []

    def _gauge(name: str, help_text: str, value: float, extra_labels: str = "") -> None:
        label_str = f'service="{service}"'
        if extra_labels:
            label_str = f'{label_str},{extra_labels}'
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{{{label_str}}} {value}")

    def _counter(name: str, help_text: str, value: int) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f'{name}{{service="{service}"}} {value}')

    # ---- request count ----
    _counter(
        "jimsai_requests_total",
        "Total number of requests processed",
        metrics.request_count.value(),
    )

    # ---- request latency ----
    _gauge(
        "jimsai_request_latency_p50_ms",
        "P50 request latency in milliseconds",
        metrics.request_latency.p50(),
    )
    _gauge(
        "jimsai_request_latency_p99_ms",
        "P99 request latency in milliseconds",
        metrics.request_latency.p99(),
    )

    # ---- model load durations (one line per model key) ----
    if metrics.model_load_duration:
        lines.append("# HELP jimsai_model_load_duration_ms Model loading duration in milliseconds")
        lines.append("# TYPE jimsai_model_load_duration_ms gauge")
        for model_key, duration_ms in sorted(metrics.model_load_duration.items()):
            lines.append(
                f'jimsai_model_load_duration_ms{{service="{service}",model="{model_key}"}} {duration_ms}'
            )

    # ---- GPU-service metrics (Renderer / Reasoning) ----
    if metrics._is_gpu_service and metrics.first_token_latency.count() > 0:
        _gauge(
            "jimsai_first_token_latency_p50_ms",
            "P50 first-token latency in milliseconds",
            metrics.first_token_latency.p50(),
        )
        _gauge(
            "jimsai_first_token_latency_p99_ms",
            "P99 first-token latency in milliseconds",
            metrics.first_token_latency.p99(),
        )

    if metrics._is_gpu_service and metrics.total_generation_latency.count() > 0:
        _gauge(
            "jimsai_generation_latency_p50_ms",
            "P50 total generation latency in milliseconds",
            metrics.total_generation_latency.p50(),
        )
        _gauge(
            "jimsai_generation_latency_p99_ms",
            "P99 total generation latency in milliseconds",
            metrics.total_generation_latency.p99(),
        )

    if metrics._is_gpu_service and metrics.tokens_per_second.count() > 0:
        _gauge(
            "jimsai_tokens_per_second_p50",
            "P50 tokens-per-second throughput",
            metrics.tokens_per_second.p50(),
        )
        _gauge(
            "jimsai_tokens_per_second_p99",
            "P99 tokens-per-second throughput",
            metrics.tokens_per_second.p99(),
        )

    # ---- Embedding-service batch size distribution ----
    if metrics._is_embedding_service and metrics.batch_size_histogram.count() > 0:
        _gauge(
            "jimsai_batch_size_p50",
            "P50 embedding request batch size",
            metrics.batch_size_histogram.p50(),
        )
        _gauge(
            "jimsai_batch_size_p99",
            "P99 embedding request batch size",
            metrics.batch_size_histogram.p99(),
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def create_metrics(
    service_name: str,
    *,
    is_gpu_service: bool = False,
    is_embedding_service: bool = False,
) -> ServiceMetrics:
    """Factory function — create a :class:`ServiceMetrics` singleton.

    Parameters
    ----------
    service_name:
        Short name used as the ``service`` label in all Prometheus metrics.
        Typical values: ``"embedding"``, ``"classification"``, ``"intent"``,
        ``"renderer"``, ``"reasoning"``.
    is_gpu_service:
        Enable first-token, total generation, and TPS histograms.
    is_embedding_service:
        Enable batch-size histogram.

    Example
    -------
    .. code-block:: python

        # At module level in modal_embedding_service.py
        from shared.metrics import create_metrics
        metrics = create_metrics("embedding", is_embedding_service=True)
    """
    return ServiceMetrics(
        service_name,
        is_gpu_service=is_gpu_service,
        is_embedding_service=is_embedding_service,
    )
