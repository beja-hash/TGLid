from __future__ import annotations

import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import (
    DbSession,
    get_current_session,
    require_active_user,
    require_csrf,
)
from app.core.config import Settings, get_settings
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    login_rate_limit_key,
    normalize_email,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.db.models import User, UserSession
from app.schemas.auth import ChangePasswordRequest, LoginRequest, UserProfile
from app.services.auth import add_audit, create_session, revoke_user_sessions, utcnow

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)
_DUMMY_PASSWORD_HASH = hash_password("this-password-is-only-for-equalized-login-checks")


def profile(user: User) -> UserProfile:
    return UserProfile.model_validate(user)


def client_ip(request: Request) -> str | None:
    # Proxy headers are intentionally ignored until trusted proxies are explicitly configured.
    return request.client.host if request.client else None


def request_context(request: Request) -> tuple[str | None, str | None]:
    return client_ip(request), request.headers.get("user-agent")


def ensure_allowed_origin(request: Request, settings: Settings) -> None:
    if request.headers.get("origin") not in settings.cors_origin_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недопустимый источник запроса")


async def get_rate_limit_retry_after(
    redis: Redis,
    key: str,
    settings: Settings,
) -> int | None:
    try:
        count = await redis.get(key)
        if count is None or int(cast(bytes, count)) < settings.login_rate_limit_attempts:
            return None
        ttl = await redis.ttl(key)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Вход временно недоступен",
        ) from exc
    return max(int(ttl), 1)


async def record_failure(redis: Redis, key: str, settings: Settings) -> None:
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, settings.login_rate_limit_window_seconds)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Вход временно недоступен",
        ) from exc


async def best_effort_login_audit(
    db: DbSession,
    event_type: str,
    ip_address: str | None,
    user_agent: str | None,
    metadata: dict[str, object],
) -> None:
    try:
        await add_audit(
            db,
            event_type,
            None,
            "authentication",
            None,
            ip_address,
            user_agent,
            metadata,
        )
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        logger.warning("non_critical_auth_audit_failed")


def set_auth_cookies(
    response: Response,
    settings: Settings,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
        max_age=max_age,
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
        max_age=max_age,
    )


def set_csrf_cookie(response: Response, settings: Settings, csrf_token: str) -> None:
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
        max_age=settings.session_ttl_hours * 3600,
    )


@router.post("/login", response_model=UserProfile)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserProfile:
    ensure_allowed_origin(request, settings)
    email = normalize_email(str(payload.email))
    ip_address, user_agent = request_context(request)
    key = login_rate_limit_key(email, ip_address)
    redis = cast(Redis, request.app.state.redis)

    retry_after = await get_rate_limit_retry_after(redis, key, settings)
    if retry_after is not None:
        await best_effort_login_audit(
            db,
            "AUTH_RATE_LIMITED",
            ip_address,
            user_agent,
            {"email_hash": hash_token(email)},
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Слишком много попыток входа",
            headers={"Retry-After": str(retry_after)},
        )

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_matches = verify_password(payload.password, password_hash)
    if user is None or not user.is_active or not password_matches:
        await record_failure(redis, key, settings)
        await best_effort_login_audit(
            db,
            "AUTH_LOGIN_FAILED",
            ip_address,
            user_agent,
            {"email_hash": hash_token(email)},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    session_token, csrf_token = await create_session(
        db,
        user,
        settings.session_ttl_hours,
        ip_address,
        user_agent,
    )
    user.last_login_at = utcnow()
    await add_audit(
        db,
        "AUTH_LOGIN_SUCCEEDED",
        user.id,
        "user",
        user.id,
        ip_address,
        user_agent,
    )
    await db.commit()
    try:
        await redis.delete(key)
    except Exception:
        logger.warning("login_rate_limit_reset_failed")
    set_auth_cookies(response, settings, session_token, csrf_token)
    return profile(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    request: Request,
    response: Response,
    db: DbSession,
    session: Annotated[UserSession, Depends(get_current_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    user = cast(User, request.state.current_user)
    session.revoked_at = utcnow()
    ip_address, user_agent = request_context(request)
    await add_audit(
        db,
        "SESSION_REVOKED",
        user.id,
        "session",
        session.id,
        ip_address,
        user_agent,
        {"reason": "logout"},
    )
    await add_audit(
        db,
        "AUTH_LOGOUT",
        user.id,
        "session",
        session.id,
        ip_address,
        user_agent,
    )
    await db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )


@router.get("/me", response_model=UserProfile)
async def me(user: Annotated[User, Depends(require_active_user)]) -> UserProfile:
    return profile(user)


@router.post(
    "/change-password",
    response_model=UserProfile,
    dependencies=[Depends(require_csrf)],
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: DbSession,
    session: Annotated[UserSession, Depends(get_current_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserProfile:
    user = cast(User, request.state.current_user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Текущий пароль неверен",
        )
    try:
        validate_password(payload.new_password, settings.password_min_length)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Новый пароль должен отличаться от текущего",
        )

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.password_changed_at = utcnow()
    revoked = await revoke_user_sessions(db, user.id, session.id)
    csrf_token = generate_token()
    session.csrf_token_hash = hash_token(csrf_token)
    ip_address, user_agent = request_context(request)
    await add_audit(
        db,
        "AUTH_PASSWORD_CHANGED",
        user.id,
        "user",
        user.id,
        ip_address,
        user_agent,
    )
    if revoked:
        await add_audit(
            db,
            "SESSION_REVOKED",
            user.id,
            "user",
            user.id,
            ip_address,
            user_agent,
            {"count": revoked, "reason": "password_changed"},
        )
    await db.commit()
    set_csrf_cookie(response, settings, csrf_token)
    return profile(user)
