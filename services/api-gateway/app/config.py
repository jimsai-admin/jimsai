from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "api-gateway"
    log_level: str = "INFO"
    redis_url: str = ""
    neo4j_uri: str = ""
    postgres_url: str = ""
    otel_exporter_otlp_endpoint: str = ""
    cors_origins: str = "http://127.0.0.1:3001,http://localhost:3001,http://127.0.0.1:3000,http://localhost:3000,https://jimsai.vercel.app"
    jims_auth_required: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

