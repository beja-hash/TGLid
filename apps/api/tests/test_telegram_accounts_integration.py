from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import TelegramAccount, User, UserRole

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        "TEST_DATABASE_URL" not in os.environ,
        reason="requires isolated PostgreSQL test database",
    ),
]


def test_postgresql_allows_only_one_active_telegram_account() -> None:
    async def scenario() -> None:
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.execute(delete(TelegramAccount))
                await session.execute(delete(User))
                creator = User(
                    email=f"telegram-{uuid.uuid4()}@example.com",
                    full_name="Telegram test creator",
                    password_hash=hash_password("correct horse battery staple"),
                    role=UserRole.ADMIN,
                )
                session.add(creator)
                await session.flush()
                session.add(TelegramAccount(created_by_user_id=creator.id, is_active=True))
                await session.commit()

            async with factory() as session:
                session.add(TelegramAccount(created_by_user_id=creator.id, is_active=True))
                with pytest.raises(IntegrityError):
                    await session.commit()
        finally:
            async with factory() as session:
                await session.execute(delete(TelegramAccount))
                await session.execute(delete(User))
                await session.commit()
            await engine.dispose()

    asyncio.run(scenario())
