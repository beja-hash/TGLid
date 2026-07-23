from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    hash_password,
    hash_token,
    login_rate_limit_key,
    normalize_email,
    tokens_match,
    verify_password,
)


def test_email_normalization_and_password_hashing() -> None:
    assert normalize_email("  Admin@Example.COM ") == "admin@example.com"
    password_hash = hash_password("a sufficiently long password")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("a sufficiently long password", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_tokens_are_compared_to_one_way_hashes() -> None:
    token_hash = hash_token("secret-token")
    assert token_hash != "secret-token"
    assert tokens_match("secret-token", token_hash)
    assert not tokens_match("other-token", token_hash)


def test_rate_limit_key_does_not_expose_email() -> None:
    key = login_rate_limit_key("Admin@Example.com", "127.0.0.1")
    assert "admin@example.com" not in key
    assert key == login_rate_limit_key(" admin@example.COM ", "127.0.0.1")
    assert key != login_rate_limit_key("admin@example.com", "127.0.0.2")


def test_production_rejects_insecure_session_cookie() -> None:
    try:
        Settings(
            app_env="production",
            app_name="TGLid API",
            api_host="0.0.0.0",
            api_port=8000,
            database_url="postgresql+asyncpg://example",
            redis_url="redis://example",
            cors_origins="https://crm.example.test",
            session_cookie_secure=False,
        )
    except ValidationError as error:
        assert "SESSION_COOKIE_SECURE" in str(error)
    else:
        raise AssertionError("production settings accepted an insecure cookie")
