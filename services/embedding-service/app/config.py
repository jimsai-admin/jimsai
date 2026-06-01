from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "embedding-service"
    log_level: str = "INFO"
    jims_render_agent_token: str = ""
    jims_embedding_model: str = "intfloat/multilingual-e5-small"
    jims_embedding_dimensions: int = 768
    jims_embedding_device: str = "cpu"
    jims_embedding_preload_on_startup: bool = True
    jims_embedding_torch_dtype: str = "auto"
    jims_embedding_hash_fallback_enabled: bool = True
    jims_active_artifact_id: str = "base_encoder"
    jims_active_artifact_path: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
