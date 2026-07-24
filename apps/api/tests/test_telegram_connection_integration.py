from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.models import (
    AuditLog,
    TelegramAccount,
    TelegramAccountStatus,
    User,
    UserRole,
    UserSession,
)
from app.main import create_app
from app.telegram.adapter import FakeTelegramAdapter
from app.telegram.session_crypto import TelegramSessionCrypto

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="requires isolated PostgreSQL test database",
    ),
]

TEST_KEY = base64.b64encode(b"c" * 32).decode("ascii")
PLAIN_SESSION = "persistent-test-string-session"
PASSWORD = "correct horse battery staple"
ORIGIN = "http://localhost:3000"


def connection_settings(*, configured: bool = True) -> Settings:
    return Settings(
        app_env="test",
        app_name="TGLid API",
        api_host="127.0.0.1",
        api_port=8000,
        database_url=get_settings().database_url,
        redis_url=get_settings().redis_url,
        cors_origins=ORIGIN,
        telegram_api_id=1 if configured else None,
        telegram_api_hash="test-api-hash" if configured else None,
        telegram_session_encryption_key=TEST_KEY if configured else None,
        telegram_connect_timeout_seconds=1,
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


async def seed_user(role: UserRole = UserRole.ADMIN) -> User:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        user = User(
            email=f"connection-{uuid.uuid4()}@example.com",
            full_name="Connection operator",
            password_hash=hash_password(PASSWORD),
            role=role,
        )
        session.add(user)
        await session.commit()
    await engine.dispose()
    return user


async def seed_account(
    creator_id: uuid.UUID,
    *,
    encrypted_session: bytes | None = None,
    session_nonce: bytes | None = None,
) -> uuid.UUID:
    if encrypted_session is None and session_nonce is None:
        encrypted_session, session_nonce = TelegramSessionCrypto(TEST_KEY).encrypt(PLAIN_SESSION)
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        account = TelegramAccount(
            telegram_user_id=100_001,
            phone_masked="+7 *** ***-67",
            username="before_connect",
            first_name="Before",
            status=TelegramAccountStatus.DISCONNECTED,
            encrypted_session=encrypted_session,
            session_nonce=session_nonce,
            is_active=True,
            created_by_user_id=creator_id,
        )
        session.add(account)
        await session.commit()
        account_id = account.id
    await engine.dispose()
    return account_id


async def read_account(account_id: uuid.UUID) -> TelegramAccount:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as session:
        account = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.id == account_id))
        ).scalar_one()
    await engine.dispose()
    return account


async def read_audits() -> list[AuditLog]:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as session:
        audits = list((await session.execute(select(AuditLog))).scalars())
    await engine.dispose()
    return audits


@pytest.fixture(autouse=True)
def clean_storage() -> Iterator[None]:
    asyncio.run(reset_storage())
    yield
    asyncio.run(reset_storage())


@dataclass
class AppHarness:
    app: FastAPI
    client: TestClient
    settings: Settings
    adapter: FakeTelegramAdapter


def application(
    adapter: FakeTelegramAdapter | None = None,
    *,
    configured: bool = True,
) -> tuple[FastAPI, Settings, FakeTelegramAdapter]:
    settings = connection_settings(configured=configured)
    fake = adapter or FakeTelegramAdapter()
    app = create_app(settings)
    app.state.telegram_adapter = fake
    app.dependency_overrides[get_settings] = lambda: settings
    return app, settings, fake


def login(client: TestClient, user: User) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": user.email, "password": PASSWORD},
    )
    assert response.status_code == 200
    csrf = client.cookies.get("tglid_csrf")
    assert csrf
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def test_connect_duplicate_check_disconnect_and_reconnect() -> None:
    app, settings, adapter = application(
        FakeTelegramAdapter(connection_session="rotated-persistent-session")
    )
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        account_id = asyncio.run(seed_account(administrator.id))
        headers = login(client, administrator)

        connected = client.post("/api/v1/telegram-account/connect", headers=headers)
        assert connected.status_code == 200
        assert connected.json()["status"] == "CONNECTED"
        duplicate = client.post("/api/v1/telegram-account/connect", headers=headers)
        assert duplicate.status_code == 200
        assert adapter.connection_clients_created == 1

        checked = client.post("/api/v1/telegram-account/check", headers=headers)
        assert checked.status_code == 200
        assert checked.json()["last_checked_at"] is not None

        disconnected = client.post("/api/v1/telegram-account/disconnect", headers=headers)
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "DISCONNECTED"
        stored = asyncio.run(read_account(account_id))
        assert stored.encrypted_session != b"rotated-persistent-session"
        assert stored.session_nonce is not None
        assert (
            TelegramSessionCrypto(TEST_KEY).decrypt(
                stored.encrypted_session or b"", stored.session_nonce
            )
            == "rotated-persistent-session"
        )

        reconnected = client.post("/api/v1/telegram-account/connect", headers=headers)
        assert reconnected.status_code == 200
        assert adapter.connection_clients_created == 2

    events = {event.event_type for event in asyncio.run(read_audits())}
    assert {
        "TELEGRAM_ACCOUNT_CONNECTED",
        "TELEGRAM_CONNECTION_CHECKED",
        "TELEGRAM_ACCOUNT_DISCONNECTED",
        "TELEGRAM_ACCOUNT_RECONNECTED",
    } <= events


def test_parallel_duplicate_connect_uses_one_client() -> None:
    app, _, adapter = application()
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        asyncio.run(seed_account(administrator.id))
        headers = login(client, administrator)
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda _: client.post("/api/v1/telegram-account/connect", headers=headers),
                    range(2),
                )
            )
        assert {response.status_code for response in responses} == {200}
        assert adapter.connection_clients_created == 1


def test_startup_recovery_and_shutdown_preserve_session() -> None:
    administrator = asyncio.run(seed_user())
    account_id = asyncio.run(seed_account(administrator.id))
    app, _, adapter = application()
    with TestClient(app) as client:
        status_response = client.get(
            "/api/v1/telegram-account", headers=login(client, administrator)
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "CONNECTED"
        assert adapter.connection_clients_created == 1
        assert client.get("/health/ready").status_code == 200
    stored = asyncio.run(read_account(account_id))
    assert stored.status == TelegramAccountStatus.DISCONNECTED
    assert stored.encrypted_session is not None
    assert adapter.disconnect_calls == 1


@pytest.mark.parametrize(
    ("outcome", "status_code", "error_code"),
    [
        ("invalid_session", 409, "INVALID_SESSION"),
        ("unauthorized", 409, "UNAUTHORIZED_SESSION"),
        ("timeout", 504, "TIMEOUT"),
        ("unavailable", 503, "TELEGRAM_UNAVAILABLE"),
        ("flood_wait", 429, "FLOOD_WAIT"),
    ],
)
def test_connection_failures_are_safe(outcome: str, status_code: int, error_code: str) -> None:
    app, _, _ = application(FakeTelegramAdapter(connection_result=outcome))
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        account_id = asyncio.run(seed_account(administrator.id))
        response = client.post(
            "/api/v1/telegram-account/connect", headers=login(client, administrator)
        )
        assert response.status_code == status_code
        assert PLAIN_SESSION not in response.text
        assert client.get("/health/ready").status_code == 200
        account = asyncio.run(read_account(account_id))
        assert account.status == TelegramAccountStatus.ERROR
        assert account.last_error_code == error_code


def test_corrupted_ciphertext_and_missing_configuration_are_safe() -> None:
    app, _, _ = application()
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        account_id = asyncio.run(
            seed_account(administrator.id, encrypted_session=b"corrupt", session_nonce=b"0" * 12)
        )
        response = client.post(
            "/api/v1/telegram-account/connect", headers=login(client, administrator)
        )
        assert response.status_code == 409
        assert asyncio.run(read_account(account_id)).last_error_code == "INVALID_SESSION_DATA"

    asyncio.run(reset_storage())
    administrator = asyncio.run(seed_user())
    account_id = asyncio.run(seed_account(administrator.id))
    app, _, _ = application(configured=False)
    with TestClient(app) as client:
        response = client.get("/api/v1/telegram-account", headers=login(client, administrator))
        assert response.status_code == 200
        assert response.json()["configured"] is False
        assert response.json()["status"] == "NOT_CONFIGURED"
    assert asyncio.run(read_account(account_id)).status == TelegramAccountStatus.NOT_CONFIGURED


def test_delete_session_requires_new_authorization() -> None:
    app, _, _ = application()
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        account_id = asyncio.run(seed_account(administrator.id))
        headers = login(client, administrator)
        assert client.post("/api/v1/telegram-account/connect", headers=headers).status_code == 200
        removed = client.delete("/api/v1/telegram-account/session", headers=headers)
        assert removed.status_code == 204
        account = asyncio.run(read_account(account_id))
        assert account.encrypted_session is None
        assert account.session_nonce is None
        assert not account.is_active
        assert account.status == TelegramAccountStatus.DISCONNECTED
        assert client.post("/api/v1/telegram-account/connect", headers=headers).status_code == 404
    assert "TELEGRAM_SESSION_REMOVED" in {event.event_type for event in asyncio.run(read_audits())}


def test_lifecycle_requires_csrf_and_admin() -> None:
    app, _, adapter = application()
    with TestClient(app) as client:
        administrator = asyncio.run(seed_user())
        asyncio.run(seed_account(administrator.id))
        login(client, administrator)
        assert client.post("/api/v1/telegram-account/connect").status_code == 403
        employee = asyncio.run(seed_user(UserRole.EMPLOYEE))
        headers = login(client, employee)
        assert client.post("/api/v1/telegram-account/connect", headers=headers).status_code == 403
        assert adapter.connection_clients_created == 0


def test_startup_failure_does_not_break_readiness_and_audit_has_no_secrets() -> None:
    administrator = asyncio.run(seed_user())
    account_id = asyncio.run(seed_account(administrator.id))
    app, _, _ = application(FakeTelegramAdapter(connection_result="unavailable"))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        account = asyncio.run(read_account(account_id))
        assert account.status == TelegramAccountStatus.ERROR
    audit_text = json.dumps(
        [
            {"event": event.event_type, "metadata": event.metadata_}
            for event in asyncio.run(read_audits())
        ]
    )
    assert PLAIN_SESSION not in audit_text
    assert TEST_KEY not in audit_text
    assert "test-api-hash" not in audit_text
    assert "+79991234567" not in audit_text
