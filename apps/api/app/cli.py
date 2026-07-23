from __future__ import annotations

import argparse
import asyncio
import getpass
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import delete, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.security import hash_password, normalize_email, validate_password
from app.db.database import Database
from app.db.models import User, UserRole, UserSession
from app.services.auth import add_audit, utcnow


async def create_admin(email: str, name: str) -> None:
    password = getpass.getpass("Пароль: ")
    confirmation = getpass.getpass("Повторите пароль: ")
    if password != confirmation:
        raise ValueError("Пароли не совпадают")
    settings = get_settings()
    validate_password(password, settings.password_min_length)
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Имя не может быть пустым")

    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            normalized_email = normalize_email(email)
            exists = (
                await session.execute(select(User.id).where(User.email == normalized_email))
            ).scalar_one_or_none()
            if exists:
                raise ValueError("Пользователь с таким email уже существует")
            user = User(
                email=normalized_email,
                full_name=normalized_name,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                is_active=True,
                must_change_password=False,
                password_changed_at=utcnow(),
            )
            session.add(user)
            try:
                await session.flush()
                await add_audit(
                    session,
                    "USER_CREATED",
                    user.id,
                    "user",
                    user.id,
                    None,
                    None,
                    {"bootstrap": True, "role": UserRole.ADMIN.value},
                )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("Пользователь с таким email уже существует") from exc
    finally:
        await database.close()
    print(f"Администратор {normalize_email(email)} создан")


async def cleanup_sessions() -> None:
    settings = get_settings()
    threshold = utcnow() - timedelta(days=settings.session_retention_days)
    database = Database(settings.database_url)
    try:
        async with database.session_factory() as session:
            result = await session.execute(
                delete(UserSession).where(
                    or_(
                        UserSession.expires_at < threshold,
                        UserSession.revoked_at < threshold,
                    )
                )
            )
            await session.commit()
            deleted = int(cast(CursorResult[Any], result).rowcount or 0)
            print(f"Удалено сессий: {deleted}")
    finally:
        await database.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TGLid auth maintenance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-admin")
    create.add_argument("email")
    create.add_argument("name")
    subparsers.add_parser("cleanup-sessions")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "create-admin":
        asyncio.run(create_admin(args.email, args.name))
    else:
        asyncio.run(cleanup_sessions())


if __name__ == "__main__":
    main()
