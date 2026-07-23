from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import DbSession, require_admin, require_csrf
from app.api.routes.auth import client_ip, profile
from app.core.security import generate_temporary_password, hash_password, normalize_email
from app.db.models import AuditLog, User, UserRole
from app.schemas.auth import (
    AuditLogResponse,
    CreateUserRequest,
    PaginatedAuditLogs,
    PaginatedUsers,
    TemporaryPasswordResponse,
    UpdateUserRequest,
    UserProfile,
)
from app.services.auth import (
    add_audit,
    revoke_user_sessions,
    sanitize_audit_metadata,
    sanitize_audit_text,
    utcnow,
)
from app.services.users import ensure_active_admin_remains, lock_user_for_admin_change

router = APIRouter(prefix="/api/v1", tags=["users"])


def request_context(request: Request) -> tuple[str | None, str | None]:
    return client_ip(request), request.headers.get("user-agent")


@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> PaginatedUsers:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
    if role is not None:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active == is_active)
    total = (await db.execute(select(func.count()).select_from(User).where(*filters))).scalar_one()
    users = (
        await db.execute(
            select(User)
            .where(*filters)
            .order_by(User.created_at.asc(), User.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    return PaginatedUsers(
        items=[profile(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/users",
    response_model=TemporaryPasswordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> TemporaryPasswordResponse:
    temporary_password = generate_temporary_password()
    user = User(
        email=normalize_email(str(payload.email)),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(temporary_password),
        role=payload.role,
        is_active=True,
        must_change_password=True,
    )
    ip, user_agent = request_context(request)
    db.add(user)
    try:
        await db.flush()
        await add_audit(
            db,
            "USER_CREATED",
            admin.id,
            "user",
            user.id,
            ip,
            user_agent,
            {"role": user.role.value},
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует"
        ) from exc
    return TemporaryPasswordResponse(user=profile(user), temporary_password=temporary_password)


@router.patch(
    "/users/{user_id}",
    response_model=UserProfile,
    dependencies=[Depends(require_csrf)],
)
async def update_user(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> UserProfile:
    target = await lock_user_for_admin_change(db, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")

    role_changed = payload.role is not None and payload.role != target.role
    active_changed = payload.is_active is not None and payload.is_active != target.is_active
    name_changed = payload.full_name is not None and payload.full_name.strip() != target.full_name

    if not any((role_changed, active_changed, name_changed)):
        return profile(target)
    if target.id == admin.id and active_changed and payload.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя деактивировать себя")

    removes_active_admin = (
        target.role == UserRole.ADMIN
        and target.is_active
        and (
            (role_changed and payload.role != UserRole.ADMIN)
            or (active_changed and payload.is_active is False)
        )
    )
    if removes_active_admin:
        await ensure_active_admin_remains(db, target)

    ip, user_agent = request_context(request)
    if name_changed:
        assert payload.full_name is not None
        target.full_name = payload.full_name.strip()
    if role_changed:
        assert payload.role is not None
        previous_role = target.role
        target.role = payload.role
        await add_audit(
            db,
            "USER_ROLE_CHANGED",
            admin.id,
            "user",
            target.id,
            ip,
            user_agent,
            {"from": previous_role.value, "to": target.role.value},
        )
    if active_changed:
        target.is_active = bool(payload.is_active)
        event = "USER_ACTIVATED" if target.is_active else "USER_DEACTIVATED"
        await add_audit(db, event, admin.id, "user", target.id, ip, user_agent)
        if not target.is_active:
            revoked = await revoke_user_sessions(db, target.id)
            if revoked:
                await add_audit(
                    db,
                    "SESSION_REVOKED",
                    admin.id,
                    "user",
                    target.id,
                    ip,
                    user_agent,
                    {"count": revoked, "reason": "user_deactivated"},
                )
    await add_audit(db, "USER_UPDATED", admin.id, "user", target.id, ip, user_agent)
    await db.commit()
    return profile(target)


@router.post(
    "/users/{user_id}/reset-password",
    response_model=TemporaryPasswordResponse,
    dependencies=[Depends(require_csrf)],
)
async def reset_password(
    user_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
) -> TemporaryPasswordResponse:
    target = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    temporary_password = generate_temporary_password()
    target.password_hash = hash_password(temporary_password)
    target.must_change_password = True
    target.password_changed_at = utcnow()
    revoked = await revoke_user_sessions(db, target.id)
    ip, user_agent = request_context(request)
    await add_audit(db, "USER_PASSWORD_RESET", admin.id, "user", target.id, ip, user_agent)
    if revoked:
        await add_audit(
            db,
            "SESSION_REVOKED",
            admin.id,
            "user",
            target.id,
            ip,
            user_agent,
            {"count": revoked, "reason": "password_reset"},
        )
    await db.commit()
    return TemporaryPasswordResponse(user=profile(target), temporary_password=temporary_password)


@router.get("/audit-logs", response_model=PaginatedAuditLogs)
async def list_audit_logs(
    db: DbSession,
    _admin: Annotated[User, Depends(require_admin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    event_type: str | None = Query(None, max_length=80),
    actor_user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedAuditLogs:
    filters = []
    if event_type:
        filters.append(AuditLog.event_type == event_type)
    if actor_user_id:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if date_from:
        filters.append(AuditLog.created_at >= date_from)
    if date_to:
        filters.append(AuditLog.created_at <= date_to)
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*filters))
    ).scalar_one()
    logs = (
        await db.execute(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    return PaginatedAuditLogs(
        items=[
            AuditLogResponse(
                id=log.id,
                actor_user_id=log.actor_user_id,
                event_type=log.event_type,
                target_type=log.target_type,
                target_id=log.target_id,
                ip_address=log.ip_address,
                user_agent=sanitize_audit_text(log.user_agent),
                metadata=sanitize_audit_metadata(log.metadata_),
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
