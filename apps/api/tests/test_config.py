import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="wildcard"):
        Settings(
            app_env="test",
            app_name="TGLid API",
            api_host="127.0.0.1",
            api_port=8000,
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            cors_origins="*",
        )
