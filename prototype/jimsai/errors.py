from __future__ import annotations


class CriticalServiceUnavailable(RuntimeError):
    """Raised when a required AI service is unavailable on a critical path."""

