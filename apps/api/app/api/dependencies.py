from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import timedelta
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import tokens_match
from app.db.database import Database
from app.db.models import User, UserRole, UserSession
from app.services.auth import find_active_session, utcnow
from app.services.health import HealthService


def get_health_service(request: Request) -> HealthService:
    return cast(HealthService, request.app.state.health_service)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    database = cast(Database, request.app.state.database)
    async with database.session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_session(
    request: Request, db: DbSession, settings: Annotated[Settings, Depends(get_settings)]
) -> UserSession:
    cached = getattr(request.state, "current_session", None)
    if cached is not None:
        return cast(UserSession, cached)
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется авторизация")
    result = await find_active_session(db, token)
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    session, user = result
    if session.last_seen_at < utcnow() - timedelta(
        minutes=settings.session_last_seen_update_minutes
    ):
        session.last_seen_at = utcnow()
        await db.commit()
    request.state.current_session = session
    request.state.current_user = user
    return session


async def get_current_user(
    request: Request, session: Annotated[UserSession, Depends(get_current_session)]
) -> User:
    cached = getattr(request.state, "current_user", None)
    if cached is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    return cast(User, cached)


async def require_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия недействительна")
    return user


async def require_password_changed(
    user: Annotated[User, Depends(require_active_user)],
) -> User:
    if user.must_change_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Требуется смена временного пароля",
        )
    return user


def require_role(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def checker(user: Annotated[User, Depends(require_password_changed)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return checker


require_admin = require_role(UserRole.ADMIN)


async def require_csrf(
    request: Request,
    session: Annotated[UserSession, Depends(get_current_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origin_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недопустимый источник запроса")
    token = request.headers.get(settings.csrf_header_name)
    if token is None or not tokens_match(token, session.csrf_token_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недействительный CSRF token")
