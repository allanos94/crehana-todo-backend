"""Application settings, loaded from the environment."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration sourced from environment variables / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/todo_api"
    jwt_secret_key: SecretStr = SecretStr("insecure-default-change-me-change-me-32")

    #: Explicit CORS allow-list (security-hardening spec). Empty by default
    #: so no origin is granted cross-origin access until configured.
    cors_allowed_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    """Return the cached, process-wide `Settings` instance."""
    return Settings()
