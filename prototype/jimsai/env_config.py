"""
env_config.py — Strict environment variable loader for JIMS-AI backend.

Raises RuntimeError at import time if any required variable is absent,
so missing config is caught at startup, not buried in a runtime None check.
"""
from __future__ import annotations

import os
from typing import Optional


def require_env(key: str) -> str:
    """Return the value of env var *key*, or raise RuntimeError if absent/empty."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file or Modal Secrets."
        )
    return value


def get_env(key: str, default: str = "") -> str:
    """Return env var *key* or *default* (for optional/tunable vars)."""
    return os.environ.get(key, default).strip()


# ---------------------------------------------------------------------------
# Required configuration — loaded at module import
# Any missing key raises RuntimeError immediately (fail-fast at startup)
# ---------------------------------------------------------------------------

class RequiredConfig:
    """Container for all required runtime configuration.
    
    Instantiated once at module level. Any missing required var raises
    RuntimeError before any service can accept requests.
    """
    
    def __init__(self) -> None:
        # Supabase
        self.supabase_url = require_env("SUPABASE_URL")
        self.supabase_service_key = require_env("SUPABASE_SERVICE_KEY")
        self.supabase_anon_key = require_env("SUPABASE_ANON_KEY")
        
        # Modal AI services
        self.modal_api_key = require_env("JIMS_MODAL_API_KEY")
        self.embedding_service_url = require_env("JIMS_EMBEDDING_SERVICE_URL")
        self.classification_service_url = require_env("JIMS_CLASSIFICATION_SERVICE_URL")
        self.intent_service_url = require_env("JIMS_INTENT_SERVICE_URL")
        self.renderer_service_url = require_env("JIMS_RENDERER_SERVICE_URL")
        self.reasoning_service_url = require_env("JIMS_REASONING_SERVICE_URL")
        
        # Cloudflare
        self.cf_account_id = require_env("CF_ACCOUNT_ID")
        self.cf_vectorize_index = require_env("CF_VECTORIZE_INDEX")
        self.cf_vectorize_api_token = require_env("CF_VECTORIZE_API_TOKEN")
        self.cf_r2_bucket = require_env("CF_R2_BUCKET")
        self.cf_r2_access_key = require_env("CF_R2_ACCESS_KEY")
        self.cf_r2_secret_key = require_env("CF_R2_SECRET_KEY")
        
        # Neo4j
        self.neo4j_uri = require_env("NEO4J_URI")
        self.neo4j_password = require_env("NEO4J_PASSWORD")
        
        # HuggingFace (needed for Modal volume population)
        self.hf_token = require_env("HF_TOKEN")
        
        # Optional tunables with safe defaults
        self.neo4j_user: str = get_env("NEO4J_USER", "neo4j")
        self.neo4j_database: str = get_env("NEO4J_DATABASE", "neo4j")
        self.embedding_timeout: int = int(get_env("JIMS_EMBEDDING_TIMEOUT", "8"))
        self.generation_timeout: int = int(get_env("JIMS_GENERATION_TIMEOUT", "120"))
        self.reasoning_confidence_threshold: float = float(get_env("JIMS_REASONING_CONFIDENCE_THRESHOLD", "0.6"))
        self.reasoning_depth_threshold: int = int(get_env("JIMS_REASONING_DEPTH_THRESHOLD", "3"))
        self.t1_skip_confidence: float = float(get_env("JIMS_T1_SKIP_CONFIDENCE", "0.60"))
        self.t2_skip_confidence: float = float(get_env("JIMS_T2_SKIP_CONFIDENCE", "0.95"))
        self.embedding_dimensions: int = int(get_env("JIMS_EMBEDDING_DIMENSIONS", "768"))
        self.cf_vectorize_dimensions: int = int(get_env("CF_VECTORIZE_DIMENSIONS", "768"))
        self.redis_url: str = get_env("REDIS_URL", "")
        self.cors_origins: str = get_env("CORS_ORIGINS", "http://localhost:3000")
        self.log_level: str = get_env("LOG_LEVEL", "INFO")
        self.environment: str = get_env("ENVIRONMENT", "production")


# Singleton — raises on first import if any required var is missing
_config: Optional[RequiredConfig] = None


def get_config() -> RequiredConfig:
    """Return the singleton RequiredConfig, loading it on first call."""
    global _config
    if _config is None:
        _config = RequiredConfig()
    return _config
