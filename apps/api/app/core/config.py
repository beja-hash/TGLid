from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded only from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str
    app_name: str
    api_host: str
    api_port: int
    database_url: str
    redis_url: str
    cors_origins: str
    session_cookie_name: str = "tglid_session"
    csrf_cookie_name: str = "tglid_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    session_ttl_hours: int = 24
    session_cookie_secure: bool = False
    session_cookie_domain: str | None = None
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 300
    password_min_length: int = 10
    session_retention_days: int = 30
    session_last_seen_update_minutes: int = 5
    trusted_proxy_count: int = 0
    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    telegram_session_encryption_key: SecretStr | None = None
    telegram_connect_timeout_seconds: int = 15
    telegram_auth_challenge_ttl_seconds: int = 600
    telegram_auth_max_attempts: int = 5

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        if "*" in origins:
            raise ValueError("CORS_ORIGINS cannot contain a wildcard origin")
        return ",".join(origins)

    @field_validator(
        "session_ttl_hours",
        "login_rate_limit_attempts",
        "login_rate_limit_window_seconds",
        "password_min_length",
        "session_retention_days",
        "session_last_seen_update_minutes",
        "telegram_connect_timeout_seconds",
        "telegram_auth_challenge_ttl_seconds",
        "telegram_auth_max_attempts",
    )
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be positive")
        return value

    @field_validator("session_cookie_domain", mode="before")
    @classmethod
    def normalize_optional_domain(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        if self.app_env.casefold() == "production" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if not 10 <= self.password_min_length <= 128:
            raise ValueError("PASSWORD_MIN_LENGTH must be between 10 and 128")
        if self.trusted_proxy_count < 0:
            raise ValueError("TRUSTED_PROXY_COUNT cannot be negative")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
