from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.router import router
from app.core.config import Settings, get_settings
from app.core.errors import http_exception_handler, validation_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, SecurityHeadersMiddleware
from app.db.database import Database
from app.services.health import HealthService
from app.services.telegram_connection import TelegramConnectionManager
from app.telegram.adapter import TelegramAdapter, TelethonTelegramAdapter

logger = logging.getLogger(__name__)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings.database_url)
        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        app.state.health_service = HealthService(database, redis)
        app.state.database = database
        app.state.redis = redis

        def adapter_provider() -> TelegramAdapter | None:
            configured_adapter = getattr(app.state, "telegram_adapter", None)
            if configured_adapter is not None:
                return cast(TelegramAdapter, configured_adapter)
            if settings.telegram_api_id is None or settings.telegram_api_hash is None:
                return None
            return TelethonTelegramAdapter(
                settings.telegram_api_id,
                settings.telegram_api_hash.get_secret_value(),
                settings.telegram_connect_timeout_seconds,
            )

        connection_manager = TelegramConnectionManager(database, settings, adapter_provider)
        app.state.telegram_connection_manager = connection_manager
        try:
            try:
                await connection_manager.startup_recovery()
            except Exception:
                logger.warning("telegram_startup_recovery_failed")
            yield
        finally:
            await connection_manager.shutdown()
            await redis.aclose()
            await database.close()

    app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID", settings.csrf_header_name],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(router)
    return app


app = create_app()
