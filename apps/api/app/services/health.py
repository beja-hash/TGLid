from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis

from app.db.database import Database

logger = logging.getLogger(__name__)


class HealthService:
    """Checks infrastructure dependencies without exposing connection details."""

    def __init__(self, database: Database, redis: Redis) -> None:
        self._database = database
        self._redis = redis

    async def readiness(self) -> dict[str, str]:
        postgres, redis = await asyncio.gather(self._check_postgres(), self._check_redis())
        return {"postgres": postgres, "redis": redis}

    async def _check_postgres(self) -> str:
        try:
            await self._database.ping()
        except Exception:
            logger.warning("postgres_unavailable")
            return "unavailable"
        return "ok"

    async def _check_redis(self) -> str:
        try:
            await self._redis.ping()
        except Exception:
            logger.warning("redis_unavailable")
            return "unavailable"
        return "ok"
