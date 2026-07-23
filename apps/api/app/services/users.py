from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserRole

ADMIN_CHANGE_LOCK = 8_072_022


async def lock_user_for_admin_change(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User | None:
    return (
        await session.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()


async def ensure_active_admin_remains(session: AsyncSession, target: User) -> None:
    if target.role != UserRole.ADMIN or not target.is_active:
        return
    # Serialize only operations that can remove an active administrator.
    await session.execute(select(func.pg_advisory_xact_lock(ADMIN_CHANGE_LOCK)))
    active_admins = (
        await session.execute(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
    ).scalar_one()
    if active_admins <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "В системе должен оставаться хотя бы один активный администратор",
        )
