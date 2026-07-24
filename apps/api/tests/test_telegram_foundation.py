from __future__ import annotations

import base64
import os
import uuid
from datetime import UTC, datetime

import pytest

from app.core.config import Settings, get_settings
from app.db.models import TelegramAccountStatus
from app.schemas.telegram import TelegramAccountStatusResponse
from app.telegram.session_crypto import TelegramSessionCrypto, TelegramSessionCryptoError


def encryption_key() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def test_string_session_encrypts_and_decrypts() -> None:
    crypto = TelegramSessionCrypto(encryption_key())
    ciphertext, nonce = crypto.encrypt("telethon-string-session")

    assert ciphertext != b"telethon-string-session"
    assert crypto.decrypt(ciphertext, nonce) == "telethon-string-session"


def test_string_session_encryption_uses_unique_nonces() -> None:
    crypto = TelegramSessionCrypto(encryption_key())
    _, first_nonce = crypto.encrypt("same-session")
    _, second_nonce = crypto.encrypt("same-session")

    assert first_nonce != second_nonce
    assert len(first_nonce) == 12
    assert len(second_nonce) == 12


def test_string_session_rejects_corrupted_ciphertext() -> None:
    crypto = TelegramSessionCrypto(encryption_key())
    ciphertext, nonce = crypto.encrypt("telethon-string-session")
    corrupted = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])

    with pytest.raises(TelegramSessionCryptoError, match="encryption data is invalid"):
        crypto.decrypt(corrupted, nonce)


def test_string_session_rejects_another_key() -> None:
    crypto = TelegramSessionCrypto(encryption_key())
    ciphertext, nonce = crypto.encrypt("telethon-string-session")

    with pytest.raises(TelegramSessionCryptoError, match="encryption data is invalid"):
        TelegramSessionCrypto(encryption_key()).decrypt(ciphertext, nonce)


def test_public_telegram_status_schema_excludes_secret_fields() -> None:
    response = TelegramAccountStatusResponse(
        id=uuid.uuid4(),
        telegram_user_id=123,
        phone_masked="+7 *** ***-12-34",
        username="telegram_user",
        first_name="Test",
        last_name=None,
        status=TelegramAccountStatus.DISCONNECTED,
        is_active=True,
        connected_at=None,
        disconnected_at=None,
        last_checked_at=None,
        last_error_code=None,
        last_error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    fields = response.model_dump()
    assert "encrypted_session" not in fields
    assert "session_nonce" not in fields
    assert "telegram_api_id" not in fields
    assert "telegram_api_hash" not in fields
    assert "telegram_session_encryption_key" not in fields
    assert "phone" not in fields


def test_api_can_be_created_without_telegram_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    try:
        assert Settings(
            app_env="test",
            app_name="TGLid API",
            api_host="127.0.0.1",
            api_port=8000,
            database_url="postgresql+asyncpg://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/0",
            cors_origins="http://localhost:3000",
        ).telegram_api_id is None

        from app.main import create_app

        assert create_app().title == "TGLid API"
    finally:
        get_settings.cache_clear()
