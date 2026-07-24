from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.db.models import AuditLog, User, UserSession

_SENSITIVE_AUDIT_KEYS = (
    "password",
    "cookie",
    "session_token",
    "csrf",
    "token_hash",
    "authorization",
    "connection_string",
    "database_url",
    "redis_url",
    "phone",
    "verification_code",
    "telegram_api",
)
_SENSITIVE_AUDIT_VALUE_MARKERS = (
    "authorization:",
    "bearer ",
    "postgresql://",
    "postgresql+asyncpg://",
    "redis://",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def sanitize_audit_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.casefold()
    if any(marker in normalized for marker in _SENSITIVE_AUDIT_VALUE_MARKERS):
        return "[REDACTED]"
    return value


def _sanitize_audit_value(value: object) -> object:
    if isinstance(value, dict):
        return sanitize_audit_metadata(value)
    if isinstance(value, list):
        return [_sanitize_audit_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_audit_text(value) or ""
    return value


def sanitize_audit_metadata(metadata: dict[str, object] | None) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in (metadata or {}).items():
        normalized_key = key.casefold().replace("-", "_")
        if any(fragment in normalized_key for fragment in _SENSITIVE_AUDIT_KEYS):
            continue
        sanitized[key] = _sanitize_audit_value(value)
    return sanitized


async def add_audit(
    session: AsyncSession,
    event_type: str,
    actor_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID | str | None,
    ip_address: str | None,
    user_agent: str | None,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_id,
            event_type=event_type,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            ip_address=ip_address,
            user_agent=(sanitize_audit_text(user_agent) or "")[:512] or None,
            metadata_=sanitize_audit_metadata(metadata),
        )
    )


async def create_session(
    session: AsyncSession,
    user: User,
    ttl_hours: int,
    ip: str | None,
    ua: str | None,
) -> tuple[str, str]:
    token, csrf = generate_token(), generate_token()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_token_hash=hash_token(csrf),
            expires_at=utcnow() + timedelta(hours=ttl_hours),
            ip_address=ip,
            user_agent=(ua or "")[:512] or None,
        )
    )
    return token, csrf


async def revoke_user_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
    except_session: uuid.UUID | None = None,
) -> int:
    query = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_session is not None:
        query = query.where(UserSession.id != except_session)
    result = await session.execute(query.values(revoked_at=utcnow()))
    return int(cast(CursorResult[Any], result).rowcount or 0)


async def find_active_session(session: AsyncSession, token: str) -> tuple[UserSession, User] | None:
    now = utcnow()
    result = await session.execute(
        select(UserSession, User)
        .join(User)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )
    row = result.one_or_none()
    return (row[0], row[1]) if row is not None else None
