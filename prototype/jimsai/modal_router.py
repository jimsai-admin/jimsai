"""
modal_router.py — Cost-aware routing for Modal AI services.

Routes generation requests to Intent / Renderer / Reasoning based on:
  (a) explicit_model == "qwen-8b"
  (b) invention_active is True
  (c) planning_depth > JIMS_REASONING_DEPTH_THRESHOLD (default 3)
  (d) capability_confidence < JIMS_REASONING_CONFIDENCE_THRESHOLD (default 0.6)

T1 (qwen-1.7b) routes to Intent_Service.
All other generation defaults to Renderer_Service (qwen-4b).
Reasoning_Service (qwen-8b) is only activated by the conditions above.

Requirements: 25.1–25.5, 21.5, 21.6
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def get_generation_service_url(
    *,
    explicit_model: str | None = None,
    invention_active: bool = False,
    planning_depth: int = 0,
    capability_confidence: float = 1.0,
) -> tuple[str, str]:
    """Return (service_url, reason_string) for the appropriate generation service.

    Logs routing decision at INFO level for every call (Req 25.5).

    Args:
        explicit_model: "qwen-1.7b", "qwen-4b", "qwen-8b", or None (default path).
        invention_active: True when the invention engine is running for this session.
        planning_depth: Current planning recursion depth.
        capability_confidence: Confidence score from capability classifier (0–1).

    Returns:
        Tuple of (URL string, human-readable reason string).
    """
    intent_url = os.getenv("JIMS_INTENT_SERVICE_URL", "")
    renderer_url = os.getenv("JIMS_RENDERER_SERVICE_URL", "")
    reasoning_url = os.getenv("JIMS_REASONING_SERVICE_URL", "")
    threshold_conf = float(os.getenv("JIMS_REASONING_CONFIDENCE_THRESHOLD", "0.6"))  # default: 0.6
    threshold_depth = int(os.getenv("JIMS_REASONING_DEPTH_THRESHOLD", "3"))  # default: 3

    # T1 path — always to Intent_Service
    if explicit_model == "qwen-1.7b":
        reason = "explicit model=qwen-1.7b"
        logger.info("Modal routing → Intent_Service: %s", reason)
        return intent_url, reason

    # Reasoning activation conditions (Req 25.1)
    use_reasoning = (
        explicit_model == "qwen-8b"
        or invention_active
        or planning_depth > threshold_depth
        or capability_confidence < threshold_conf
    )

    if use_reasoning:
        if explicit_model == "qwen-8b":
            reason = "explicit model=qwen-8b"
        elif invention_active:
            reason = "invention_active=True"
        elif planning_depth > threshold_depth:
            reason = f"planning_depth={planning_depth} > threshold={threshold_depth}"
        else:
            reason = (
                f"capability_confidence={capability_confidence:.3f} "
                f"< threshold={threshold_conf}"
            )
        logger.info("Modal routing → Reasoning_Service: %s", reason)
        return reasoning_url, reason

    # Default: Renderer (T2, qwen-4b)
    reason = "default renderer path"
    logger.info("Modal routing → Renderer_Service: %s", reason)
    return renderer_url, reason


def get_modal_auth_headers() -> dict[str, str]:
    """Return the Authorization header for Modal inter-service calls.

    Requirements: 15.4
    """
    key = os.getenv("JIMS_MODAL_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}
