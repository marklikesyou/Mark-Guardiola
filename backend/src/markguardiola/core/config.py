from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_prefix="MARK_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://markguardiola:markguardiola@localhost:5432/markguardiola"
    )
    migration_database_url: str = (
        "postgresql+psycopg://markguardiola:markguardiola@localhost:5432/markguardiola"
    )
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    data_root: Path = Path("../data")
    artifact_root: Path = Path("../artifacts")
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    api_football_key: SecretStr | None = None
    football_data_org_key: SecretStr | None = None
    api_football_daily_limit: int = Field(default=100, ge=1)
    upload_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024)
    default_simulations: int = Field(default=10_000, ge=100, le=1_000_000)
    app_name: str = "MarkGuardiola"
    api_version: str = "v1"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError()
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError()
        return origins

    @field_validator("api_football_key", "football_data_org_key", mode="before")
    @classmethod
    def blank_secrets_are_unconfigured(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
