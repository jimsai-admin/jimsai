from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "model-bridge"
    log_level: str = "INFO"
    redis_url: str = ""
    neo4j_uri: str = ""
    postgres_url: str = ""
    otel_exporter_otlp_endpoint: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

