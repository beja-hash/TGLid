from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli import cleanup_sessions, create_admin
from app.core.config import get_settings
from app.core.security import hash_password, hash_token, normalize_email
from app.db.models import AuditLog, TelegramAccount, User, UserRole, UserSession
from app.main import app
from app.services.auth import utcnow
from app.services.users import ensure_active_admin_remains, lock_user_for_admin_change

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="requires isolated PostgreSQL test database",
    ),
]

ORIGIN = "http://localhost:3000"
ADMIN_PASSWORD = "correct horse battery staple"


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


async def seed_user(
    email: str,
    password: str = ADMIN_PASSWORD,
    role: UserRole = UserRole.ADMIN,
    *,
    active: bool = True,
    must_change: bool = False,
) -> uuid.UUID:
    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            email=normalize_email(email),
            full_name=email.split("@")[0],
            password_hash=hash_password(password),
            role=role,
            is_active=active,
            must_change_password=must_change,
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    await engine.dispose()
    return user_id


async def count_active_admins() -> int:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(User)
                .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
            )
        ).scalar_one()
    await engine.dispose()
    return count


async def session_is_revoked(user_id: uuid.UUID) -> bool:
    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as session:
        sessions = (
            await session.execute(select(UserSession).where(UserSession.user_id == user_id))
        ).scalars()
        result = all(item.revoked_at is not None for item in sessions)
    await engine.dispose()
    return result


@pytest.fixture(autouse=True)
def clean_storage() -> None:
    asyncio.run(reset_storage())


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, email: str, password: str) -> object:
    return client.post(
        "/api/v1/auth/login",
        headers={"Origin": ORIGIN},
        json={"email": email, "password": password},
    )


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(get_settings().csrf_cookie_name)
    assert token
    return {"X-CSRF-Token": token, "Origin": ORIGIN}


def test_bootstrap_admin_normalizes_email_and_rejects_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passwords = iter([ADMIN_PASSWORD, ADMIN_PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(passwords))
    asyncio.run(create_admin(" Bootstrap@Example.COM ", "Administrator"))

    async def read_user() -> User:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            user = (await session.execute(select(User))).scalar_one()
        await engine.dispose()
        return user

    user = asyncio.run(read_user())
    assert user.email == "bootstrap@example.com"
    assert user.role == UserRole.ADMIN
    assert user.is_active and not user.must_change_password
    duplicate_passwords = iter([ADMIN_PASSWORD, ADMIN_PASSWORD])
    monkeypatch.setattr("getpass.getpass", lambda _prompt: next(duplicate_passwords))
    with pytest.raises(ValueError, match="уже существует"):
        asyncio.run(create_admin("bootstrap@example.com", "Other"))


def test_citext_uniqueness_is_case_insensitive() -> None:
    asyncio.run(seed_user("MixedCase@Example.com"))

    async def insert_duplicate() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            session.add(
                User(
                    email="MIXEDCASE@example.COM",
                    full_name="Duplicate",
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=UserRole.EMPLOYEE,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
        await engine.dispose()

    asyncio.run(insert_duplicate())


def test_login_cookie_me_logout_and_revoked_session(client: TestClient) -> None:
    user_id = asyncio.run(seed_user("admin@example.com"))
    response = login(client, " ADMIN@example.com ", ADMIN_PASSWORD)
    assert response.status_code == 200
    session_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Secure" not in session_cookie
    assert "tglid_session" not in response.json()
    assert client.get("/api/v1/auth/me").json()["id"] == str(user_id)

    missing_csrf = client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
    assert missing_csrf.status_code == 403
    logout = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert asyncio.run(session_is_revoked(user_id))


def test_unknown_wrong_and_inactive_login_are_indistinguishable(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    asyncio.run(seed_user("inactive@example.com", active=False))
    responses = [
        login(client, "missing@example.com", "wrong password"),
        login(client, "admin@example.com", "wrong password"),
        login(client, "inactive@example.com", ADMIN_PASSWORD),
    ]
    assert {response.status_code for response in responses} == {401}
    assert {response.json()["error"]["message"] for response in responses} == {
        "Неверный email или пароль"
    }
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200


def test_login_origin_and_rate_limit_fail_closed(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    missing_origin = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    assert missing_origin.status_code == 403
    forbidden = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example"},
        json={"email": "admin@example.com", "password": ADMIN_PASSWORD},
    )
    assert forbidden.status_code == 403
    for _ in range(3):
        assert login(client, "admin@example.com", "wrong password").status_code == 401
    limited = login(client, "admin@example.com", ADMIN_PASSWORD)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0

    async def rate_limit_audit_exists() -> bool:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            exists = (
                await session.execute(
                    select(AuditLog.id).where(AuditLog.event_type == "AUTH_RATE_LIMITED")
                )
            ).scalar_one_or_none()
        await engine.dispose()
        return exists is not None

    assert asyncio.run(rate_limit_audit_exists())

    class BrokenRedis:
        async def get(self, _key: str) -> None:
            raise ConnectionError("redis unavailable")

    app.state.redis = BrokenRedis()
    unavailable = login(client, "other@example.com", "wrong password")
    assert unavailable.status_code == 503
    assert "redis" not in unavailable.text.casefold()


def test_successful_login_resets_only_its_rate_limit_key(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    assert login(client, "admin@example.com", "wrong password").status_code == 401
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200

    for _ in range(3):
        assert login(client, "admin@example.com", "wrong password").status_code == 401
    assert login(client, "other@example.com", "wrong password").status_code == 401
    assert login(client, "admin@example.com", "wrong password").status_code == 429


def test_admin_can_create_employee_and_employee_is_restricted(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    missing_csrf = client.post(
        "/api/v1/users",
        headers={"Origin": ORIGIN},
        json={
            "email": "employee@example.com",
            "full_name": "Employee",
            "role": "EMPLOYEE",
        },
    )
    assert missing_csrf.status_code == 403
    created = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={
            "email": " Employee@Example.COM ",
            "full_name": "Employee",
            "role": "EMPLOYEE",
        },
    )
    assert created.status_code == 201
    payload = created.json()
    temporary_password = payload["temporary_password"]
    assert "password_hash" not in created.text
    assert payload["user"]["email"] == "employee@example.com"
    assert payload["user"]["must_change_password"] is True
    duplicate = client.post(
        "/api/v1/users",
        headers=csrf_headers(client),
        json={
            "email": "EMPLOYEE@example.com",
            "full_name": "Duplicate",
            "role": "EMPLOYEE",
        },
    )
    assert duplicate.status_code == 409
    listed = client.get("/api/v1/users")
    assert listed.status_code == 200
    serialized_users = listed.text
    for secret_field in (
        "password_hash",
        "session_token",
        "token_hash",
        "csrf_token",
    ):
        assert secret_field not in serialized_users
    created_audit = client.get(
        "/api/v1/audit-logs",
        params={"event_type": "USER_CREATED"},
    )
    assert temporary_password not in created_audit.text

    client.cookies.clear()
    assert login(client, "employee@example.com", temporary_password).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/system/status").status_code == 403
    assert client.get("/api/v1/users", headers={"X-Role": "ADMIN"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 204
    assert login(client, "employee@example.com", temporary_password).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/change-password",
            headers={"Origin": ORIGIN},
            json={
                "current_password": temporary_password,
                "new_password": "employee permanent password",
            },
        ).status_code
        == 403
    )
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=csrf_headers(client),
        json={
            "current_password": temporary_password,
            "new_password": "employee permanent password",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    assert client.get("/api/v1/users").status_code == 403


def test_csrf_is_bound_to_session_and_get_does_not_require_it(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    asyncio.run(seed_user("second@example.com"))
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    first_csrf = client.cookies.get("tglid_csrf")
    assert client.get("/api/v1/users").status_code == 200

    client.cookies.clear()
    assert login(client, "second@example.com", ADMIN_PASSWORD).status_code == 200
    wrong_session = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": str(first_csrf), "Origin": ORIGIN},
    )
    assert wrong_session.status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": "tglid_session", "Origin": ORIGIN},
        ).status_code
        == 403
    )


def test_last_admin_self_deactivation_and_user_updates(client: TestClient) -> None:
    admin_id = asyncio.run(seed_user("admin@example.com"))
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    self_deactivate = client.patch(
        f"/api/v1/users/{admin_id}",
        headers=csrf_headers(client),
        json={"is_active": False},
    )
    assert self_deactivate.status_code == 400
    last_admin = client.patch(
        f"/api/v1/users/{admin_id}",
        headers=csrf_headers(client),
        json={"role": "EMPLOYEE"},
    )
    assert last_admin.status_code == 409

    other_id = asyncio.run(seed_user("employee@example.com", role=UserRole.EMPLOYEE))
    updated = client.patch(
        f"/api/v1/users/{other_id}",
        headers=csrf_headers(client),
        json={"full_name": "New Name", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "New Name"
    assert updated.json()["is_active"] is False
    activated_and_promoted = client.patch(
        f"/api/v1/users/{other_id}",
        headers=csrf_headers(client),
        json={"role": "ADMIN", "is_active": True},
    )
    assert activated_and_promoted.status_code == 200
    assert activated_and_promoted.json()["role"] == "ADMIN"
    assert activated_and_promoted.json()["is_active"] is True
    role_audits_before = client.get(
        "/api/v1/audit-logs",
        params={"event_type": "USER_ROLE_CHANGED"},
    ).json()["total"]
    no_op = client.patch(
        f"/api/v1/users/{other_id}",
        headers=csrf_headers(client),
        json={"role": "ADMIN"},
    )
    assert no_op.status_code == 200
    role_audits_after = client.get(
        "/api/v1/audit-logs",
        params={"event_type": "USER_ROLE_CHANGED"},
    ).json()["total"]
    assert role_audits_after == role_audits_before


def test_deactivation_revokes_employee_session(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    employee_id = asyncio.run(seed_user("employee@example.com", role=UserRole.EMPLOYEE))
    assert login(client, "employee@example.com", ADMIN_PASSWORD).status_code == 200
    employee_session = client.cookies.get("tglid_session")
    assert employee_session
    client.cookies.clear()
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    deactivated = client.patch(
        f"/api/v1/users/{employee_id}",
        headers=csrf_headers(client),
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    client.cookies.clear()
    client.cookies.set("tglid_session", employee_session)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_password_change_keeps_current_and_revokes_other_sessions(
    client: TestClient,
) -> None:
    asyncio.run(seed_user("employee@example.com", role=UserRole.EMPLOYEE))
    assert login(client, "employee@example.com", ADMIN_PASSWORD).status_code == 200
    old_session = client.cookies.get("tglid_session")
    assert old_session
    client.cookies.clear()
    assert login(client, "employee@example.com", ADMIN_PASSWORD).status_code == 200
    old_csrf = client.cookies.get("tglid_csrf")
    wrong_current = client.post(
        "/api/v1/auth/change-password",
        headers=csrf_headers(client),
        json={
            "current_password": "wrong password",
            "new_password": "a different permanent password",
        },
    )
    assert wrong_current.status_code == 400
    same_password = client.post(
        "/api/v1/auth/change-password",
        headers=csrf_headers(client),
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": ADMIN_PASSWORD,
        },
    )
    assert same_password.status_code == 400
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=csrf_headers(client),
        json={
            "current_password": ADMIN_PASSWORD,
            "new_password": "a different permanent password",
        },
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.cookies.get("tglid_csrf") != old_csrf
    client.cookies.clear()
    client.cookies.set("tglid_session", old_session)
    revoked_response = client.get("/api/v1/auth/me")
    assert revoked_response.status_code == 401
    assert "tglid_session=" in revoked_response.headers["set-cookie"]
    assert "Max-Age=0" in revoked_response.headers["set-cookie"]
    assert login(client, "employee@example.com", ADMIN_PASSWORD).status_code == 401
    assert (
        login(client, "employee@example.com", "a different permanent password").status_code == 200
    )


def test_user_and_audit_pagination_filters(client: TestClient) -> None:
    admin_id = asyncio.run(seed_user("admin@example.com"))
    asyncio.run(seed_user("employee-a@example.com", role=UserRole.EMPLOYEE))
    asyncio.run(
        seed_user(
            "employee-b@example.com",
            role=UserRole.EMPLOYEE,
            active=False,
        )
    )
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    users = client.get(
        "/api/v1/users",
        params={
            "search": "employee",
            "role": "EMPLOYEE",
            "is_active": "true",
            "page": 1,
            "page_size": 1,
        },
    )
    assert users.status_code == 200
    assert users.json()["total"] == 1
    audit = client.get(
        "/api/v1/audit-logs",
        params={
            "event_type": "AUTH_LOGIN_SUCCEEDED",
            "actor_user_id": str(admin_id),
            "date_from": (utcnow() - timedelta(days=1)).isoformat(),
            "date_to": (utcnow() + timedelta(days=1)).isoformat(),
            "page_size": 1,
        },
    )
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert len(audit.json()["items"]) == 1


def test_concurrent_admin_changes_leave_one_active_admin() -> None:
    first = asyncio.run(seed_user("first@example.com"))
    second = asyncio.run(seed_user("second@example.com"))

    async def demote(target_id: uuid.UUID) -> str:
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                try:
                    target = await lock_user_for_admin_change(session, target_id)
                    assert target is not None
                    await ensure_active_admin_remains(session, target)
                    target.role = UserRole.EMPLOYEE
                    await session.commit()
                    return "changed"
                except HTTPException:
                    await session.rollback()
                    return "conflict"
        finally:
            await engine.dispose()

    async def run_concurrently() -> list[str]:
        return list(await asyncio.gather(demote(first), demote(second)))

    results = asyncio.run(run_concurrently())
    assert sorted(results) == ["changed", "conflict"]
    assert asyncio.run(count_active_admins()) == 1


def test_reset_password_revokes_sessions_and_audit_hides_secret(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))
    employee_id = asyncio.run(seed_user("employee@example.com", role=UserRole.EMPLOYEE))
    assert login(client, "employee@example.com", ADMIN_PASSWORD).status_code == 200
    employee_session = client.cookies.get("tglid_session")
    assert employee_session
    client.cookies.clear()
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    reset = client.post(
        f"/api/v1/users/{employee_id}/reset-password",
        headers=csrf_headers(client),
    )
    assert reset.status_code == 200
    temporary_password = reset.json()["temporary_password"]
    assert temporary_password
    client.cookies.clear()
    client.cookies.set("tglid_session", employee_session)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200

    audit = client.get("/api/v1/audit-logs", params={"event_type": "USER_PASSWORD_RESET"})
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    serialized = audit.text
    assert temporary_password not in serialized
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    client.cookies.clear()
    assert login(client, "employee@example.com", temporary_password).status_code == 200
    assert client.get("/api/v1/system/status").status_code == 403


def test_audit_api_redacts_unsafe_legacy_metadata(client: TestClient) -> None:
    asyncio.run(seed_user("admin@example.com"))

    async def insert_unsafe_audit() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            session.add(
                AuditLog(
                    event_type="UNSAFE_TEST",
                    target_type="test",
                    user_agent="Authorization: Bearer exposed",
                    metadata_={
                        "password": "exposed",
                        "nested": {"csrf_token": "exposed", "safe": "visible"},
                        "dsn": "postgresql://user:password@database/app",
                    },
                )
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(insert_unsafe_audit())
    assert login(client, "admin@example.com", ADMIN_PASSWORD).status_code == 200
    response = client.get("/api/v1/audit-logs", params={"event_type": "UNSAFE_TEST"})
    assert response.status_code == 200
    serialized = response.text.casefold()
    assert "exposed" not in serialized
    assert "postgresql://" not in serialized
    assert "authorization:" not in serialized
    assert response.json()["items"][0]["metadata"]["nested"]["safe"] == "visible"


def test_expired_and_revoked_sessions_are_rejected_and_cleanup_runs(
    client: TestClient,
) -> None:
    user_id = asyncio.run(seed_user("admin@example.com"))

    async def add_old_sessions() -> None:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            old = utcnow() - timedelta(days=60)
            session.add_all(
                [
                    UserSession(
                        user_id=user_id,
                        token_hash=hash_token("expired"),
                        csrf_token_hash=hash_token("csrf-1"),
                        expires_at=old,
                    ),
                    UserSession(
                        user_id=user_id,
                        token_hash=hash_token("revoked"),
                        csrf_token_hash=hash_token("csrf-2"),
                        expires_at=utcnow() + timedelta(days=1),
                        revoked_at=old,
                    ),
                ]
            )
            await session.commit()
        await engine.dispose()

    asyncio.run(add_old_sessions())
    client.cookies.set("tglid_session", "expired")
    expired_response = client.get("/api/v1/auth/me")
    assert expired_response.status_code == 401
    assert "tglid_session=" in expired_response.headers["set-cookie"]
    assert "Max-Age=0" in expired_response.headers["set-cookie"]
    client.cookies.set("tglid_session", "revoked")
    assert client.get("/api/v1/auth/me").status_code == 401
    asyncio.run(cleanup_sessions())

    async def count_sessions() -> int:
        engine = create_async_engine(get_settings().database_url)
        async with async_sessionmaker(engine)() as session:
            count = (
                await session.execute(select(func.count()).select_from(UserSession))
            ).scalar_one()
        await engine.dispose()
        return count

    assert asyncio.run(count_sessions()) == 0
