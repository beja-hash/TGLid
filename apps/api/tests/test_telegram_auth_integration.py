from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.models import AuditLog, TelegramAccount, User, UserRole, UserSession
from app.main import app
from app.telegram.adapter import FakeTelegramAdapter
from app.telegram.session_crypto import TelegramSessionCrypto

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="requires isolated PostgreSQL test database",
    ),
]

TEST_KEY = base64.b64encode(b"t" * 32).decode("ascii")
PHONE = "+79991234567"


def auth_settings() -> Settings:
    return Settings(
        app_env="test",
        app_name="TGLid API",
        api_host="127.0.0.1",
        api_port=8000,
        database_url=get_settings().database_url,
        redis_url=get_settings().redis_url,
        cors_origins="http://localhost:3000",
        telegram_api_id=1,
        telegram_api_hash="test-api-hash",
        telegram_session_encryption_key=TEST_KEY,
        telegram_auth_challenge_ttl_seconds=2,
        telegram_auth_max_attempts=2,
    )


async def reset_storage() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        await connection.execute(delete(AuditLog))
        await connection.execute(delete(UserSession))
        await connection.execute(delete(TelegramAccount))
        await connection.execute(delete(User))
    await engine.dispose()
    redis = Redis.from_url(settings.redis_url)
    await redis.flushdb()
    await redis.aclose()


async def seed_user(role: UserRole = UserRole.ADMIN) -> tuple[uuid.UUID, str]:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        password = "correct horse battery staple"
        user = User(
            email=f"telegram-{uuid.uuid4()}@example.com",
            full_name="Telegram admin",
            password_hash=hash_password(password),
            role=role,
        )
        session.add(user)
        await session.commit()
        result = (user.id, password)
    await engine.dispose()
    return result


@pytest.fixture(autouse=True)
def clean_storage() -> Iterator[None]:
    asyncio.run(reset_storage())
    yield
    asyncio.run(reset_storage())


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = auth_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.state.telegram_adapter = None


def login(client: TestClient, role: UserRole = UserRole.ADMIN) -> uuid.UUID:
    user_id, password = asyncio.run(seed_user(role))
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:3000"},
        json={"email": asyncio.run(read_email(user_id)), "password": password},
    )
    assert response.status_code == 200
    return user_id


async def read_email(user_id: uuid.UUID) -> str:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as session:
        email = (await session.execute(select(User.email).where(User.id == user_id))).scalar_one()
    await engine.dispose()
    return email


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("tglid_csrf")
    assert token
    return {"Origin": "http://localhost:3000", "X-CSRF-Token": token}


def start(client: TestClient, adapter: FakeTelegramAdapter) -> dict[str, object]:
    app.state.telegram_adapter = adapter
    response = client.post(
        "/api/v1/telegram-account/auth/start",
        headers=csrf_headers(client),
        json={"phone": PHONE},
    )
    assert response.status_code == 200, response.text
    return response.json()


def verify_code(client: TestClient, challenge_id: str) -> object:
    return client.post(
        "/api/v1/telegram-account/auth/verify-code",
        headers=csrf_headers(client),
        json={"challenge_id": challenge_id, "phone": PHONE, "code": "12345"},
    )


def test_successful_flow_persists_only_encrypted_session(client: TestClient) -> None:
    login(client)
    challenge = start(client, FakeTelegramAdapter())
    result = verify_code(client, str(challenge["challenge_id"]))
    assert result.status_code == 200
    assert result.json()["status"] == "DISCONNECTED"

    async def read_account() -> TelegramAccount:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            account = (await session.execute(select(TelegramAccount))).scalar_one()
        await engine.dispose()
        return account

    account = asyncio.run(read_account())
    assert account.is_active
    assert account.encrypted_session != b"fake-permanent-string-session"
    assert account.session_nonce is not None
    assert TelegramSessionCrypto(TEST_KEY).decrypt(
        account.encrypted_session or b"", account.session_nonce
    ) == ("fake-permanent-string-session")


def test_successful_flow_with_2fa(client: TestClient) -> None:
    login(client)
    challenge = start(client, FakeTelegramAdapter(code_result="password_required"))
    password_required = verify_code(client, str(challenge["challenge_id"]))
    assert password_required.status_code == 200
    assert password_required.json()["status"] == "AUTH_PASSWORD_REQUIRED"
    completed = client.post(
        "/api/v1/telegram-account/auth/verify-password",
        headers=csrf_headers(client),
        json={"challenge_id": challenge["challenge_id"], "password": "2fa-password"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "DISCONNECTED"


def test_invalid_code_password_and_attempt_limit(client: TestClient) -> None:
    login(client)
    challenge = start(client, FakeTelegramAdapter(code_result="invalid_code"))
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 400
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 429

    challenge = start(
        client,
        FakeTelegramAdapter(code_result="password_required", password_result="invalid_password"),
    )
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 200
    failed_password = client.post(
        "/api/v1/telegram-account/auth/verify-password",
        headers=csrf_headers(client),
        json={"challenge_id": challenge["challenge_id"], "password": "wrong-2fa"},
    )
    assert failed_password.status_code == 400


def test_challenge_ttl_other_admin_and_reuse(client: TestClient) -> None:
    login(client)
    challenge = start(client, FakeTelegramAdapter())
    time.sleep(2.1)
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 410

    first_admin, _ = asyncio.run(seed_user())
    first_login = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "http://localhost:3000"},
        json={
            "email": asyncio.run(read_email(first_admin)),
            "password": "correct horse battery staple",
        },
    )
    assert first_login.status_code == 200
    challenge = start(client, FakeTelegramAdapter())
    login(client)
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 404

    login(client)
    challenge = start(client, FakeTelegramAdapter())
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 200
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 409


def test_csrf_employee_redis_unavailable_and_flood_wait(client: TestClient) -> None:
    login(client)
    app.state.telegram_adapter = FakeTelegramAdapter()
    missing_csrf = client.post("/api/v1/telegram-account/auth/start", json={"phone": PHONE})
    assert missing_csrf.status_code == 403

    login(client, UserRole.EMPLOYEE)
    assert (
        client.post(
            "/api/v1/telegram-account/auth/start",
            headers=csrf_headers(client),
            json={"phone": PHONE},
        ).status_code
        == 403
    )

    login(client)

    class BrokenRedis:
        async def set(self, *args: object, **kwargs: object) -> None:
            del args, kwargs
            raise ConnectionError

    app.state.redis = BrokenRedis()
    assert (
        client.post(
            "/api/v1/telegram-account/auth/start",
            headers=csrf_headers(client),
            json={"phone": PHONE},
        ).status_code
        == 503
    )
    app.state.redis = Redis.from_url(get_settings().redis_url)
    app.state.telegram_adapter = FakeTelegramAdapter(code_result="flood_wait")
    assert (
        client.post(
            "/api/v1/telegram-account/auth/start",
            headers=csrf_headers(client),
            json={"phone": PHONE},
        ).status_code
        == 429
    )


def test_temporary_state_and_audit_do_not_contain_secrets(client: TestClient) -> None:
    login(client)
    challenge = start(
        client,
        FakeTelegramAdapter(code_result="password_required", password_result="invalid_password"),
    )
    assert verify_code(client, str(challenge["challenge_id"])).status_code == 200
    assert client.post(
        "/api/v1/telegram-account/auth/verify-password",
        headers=csrf_headers(client),
        json={"challenge_id": challenge["challenge_id"], "password": "2fa-password"},
    ).status_code == 400

    async def read_sensitive_data() -> tuple[bytes, list[AuditLog]]:
        settings = get_settings()
        redis = Redis.from_url(settings.redis_url)
        stored = await redis.get(f"telegram_auth_challenge:{challenge['challenge_id']}")
        await redis.aclose()
        engine = create_async_engine(settings.database_url)
        async with async_sessionmaker(engine)() as session:
            audits = (await session.execute(select(AuditLog))).scalars().all()
        await engine.dispose()
        assert stored is not None
        return stored, audits

    stored, audits = asyncio.run(read_sensitive_data())
    assert b"fake-temporary-string-session" not in stored
    assert PHONE.encode() not in stored
    audit_text = json.dumps([item.metadata_ for item in audits])
    assert "fake-temporary-string-session" not in audit_text
    assert PHONE not in audit_text
    assert "12345" not in audit_text
    assert "2fa-password" not in audit_text
