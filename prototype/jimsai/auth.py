from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .provider_adapters import env_bool


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthSettings:
    required: bool
    provider: str
    supabase_url: str
    supabase_anon_key: str
    supabase_default_scopes: list[str]

    @classmethod
    def from_env(cls) -> "AuthSettings":
        return cls(
            required=True,          # always required
            provider="supabase",    # always supabase
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY", ""),
            supabase_default_scopes=os.getenv(
                "JIMS_SUPABASE_DEFAULT_SCOPES",
                "runtime:query training:read feedback:write",
            ).split(),
        )


class Principal(BaseModel):
    subject: str
    scopes: list[str]


def supabase_auth_configured(settings: AuthSettings | None = None) -> bool:
    settings = settings or AuthSettings.from_env()
    return bool(settings.supabase_url and settings.supabase_anon_key)


async def supabase_password_auth(email: str, password: str, mode: str, settings: AuthSettings | None = None) -> dict:
    settings = settings or AuthSettings.from_env()
    if not supabase_auth_configured(settings):
        raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_ANON_KEY are required for Supabase Auth")
    endpoint = "token?grant_type=password" if mode == "signin" else "signup"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{_supabase_base_url(settings.supabase_url)}/auth/v1/{endpoint}",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
    data = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = data.get("msg") or data.get("error_description") or data.get("error") or "Supabase authentication failed"
        raise HTTPException(status_code=response.status_code, detail=detail)
    return data


async def supabase_refresh_auth(refresh_token: str, settings: AuthSettings | None = None) -> dict:
    settings = settings or AuthSettings.from_env()
    if not supabase_auth_configured(settings):
        raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_ANON_KEY are required for Supabase Auth")
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{_supabase_base_url(settings.supabase_url)}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh_token},
        )
    data = response.json() if response.content else {}
    if response.status_code >= 400:
        detail = data.get("msg") or data.get("error_description") or data.get("error") or "Supabase refresh failed"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})
    return data


def verify_token(token: str, settings: AuthSettings | None = None) -> Principal:
    settings = settings or AuthSettings.from_env()
    if settings.provider != "supabase":
        raise HTTPException(status_code=500, detail="JIMS_AUTH_PROVIDER must be supabase in cloud-only mode")
    return verify_supabase_token(token, settings)


def verify_supabase_token(token: str, settings: AuthSettings) -> Principal:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=500, detail="SUPABASE_URL and SUPABASE_ANON_KEY are required for Supabase Auth")
    response = httpx.get(
        f"{_supabase_base_url(settings.supabase_url)}/auth/v1/user",
        headers={
            "apikey": settings.supabase_anon_key,
            "Authorization": f"Bearer {token}",
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired Supabase bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = response.json()
    scopes = _scopes_from_supabase_user(user, settings.supabase_default_scopes)
    return Principal(subject=str(user.get("id") or user.get("email") or "supabase-user"), scopes=scopes)


def _supabase_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    for suffix in ("/rest/v1", "/auth/v1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _scopes_from_supabase_user(user: dict, defaults: list[str]) -> list[str]:
    scopes: list[str] = []
    for metadata_key in ("app_metadata", "user_metadata"):
        metadata = user.get(metadata_key)
        if not isinstance(metadata, dict):
            continue
        value = metadata.get("scopes") or metadata.get("scope")
        if isinstance(value, str):
            scopes.extend(value.split())
        elif isinstance(value, list):
            scopes.extend(str(item) for item in value)
    return sorted(set(scopes or defaults))


def require_scope(scope: str):
    async def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Principal:
        settings = AuthSettings.from_env()
        if not settings.required:
            raise HTTPException(status_code=500, detail="JIMS_AUTH_REQUIRED must stay true in cloud-only mode")
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = verify_token(credentials.credentials, settings)
        if scope not in principal.scopes and "*" not in principal.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"missing scope: {scope}")
        return principal

    return dependency
