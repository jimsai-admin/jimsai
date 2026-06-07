"""
Bearer token authentication middleware for JIMS-AI Modal services.

This module provides a FastAPI dependency that validates the Authorization header
against the JIMS_MODAL_API_KEY environment variable using a timing-safe comparison.

Usage in any Modal service:
    from shared.auth_middleware import require_bearer_token

    @app.post("/embed", dependencies=[Depends(require_bearer_token)])
    async def embed(...): ...

    # Or inject as a parameter to receive the token value:
    @app.post("/generate")
    async def generate(token: str = Depends(require_bearer_token), ...): ...
"""

# Usage in any Modal service:
# from shared.auth_middleware import require_bearer_token
# @app.post("/generate", dependencies=[Depends(require_bearer_token)])
# async def generate(...): ...

import os
import secrets

from fastapi import Header, HTTPException


def require_bearer_token(authorization: str = Header(None)) -> str:
    """
    FastAPI dependency that validates a Bearer token in the Authorization header.

    Reads the expected token from the ``JIMS_MODAL_API_KEY`` environment variable.
    Performs a timing-safe comparison using :func:`secrets.compare_digest` to
    prevent timing-based token enumeration attacks.

    This dependency MUST be declared before any body-parsing parameters in the
    route signature so that FastAPI resolves it — and can return HTTP 401 — before
    the request body is parsed.  When used via ``dependencies=[Depends(...)]``,
    FastAPI guarantees the dependency is resolved before the handler body runs.

    Args:
        authorization: The raw ``Authorization`` header value, injected by FastAPI.

    Returns:
        The validated Bearer token string.

    Raises:
        RuntimeError: If ``JIMS_MODAL_API_KEY`` is not set in the environment.
            This is a startup configuration error, not a per-request error.
        HTTPException(401): If the ``Authorization`` header is absent, empty, does
            not start with ``"Bearer "``, or if the token does not match.
    """
    expected_key = os.environ.get("JIMS_MODAL_API_KEY", "")
    if not expected_key:
        raise RuntimeError("JIMS_MODAL_API_KEY not configured")

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization[7:]

    if not secrets.compare_digest(token, expected_key):
        raise HTTPException(status_code=401, detail="Invalid token")

    return token
