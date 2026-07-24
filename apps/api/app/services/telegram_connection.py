from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.database import Database
from app.db.models import TelegramAccount, TelegramAccountStatus
from app.services.auth import add_audit, utcnow
from app.services.telegram_auth import TelegramNotConfiguredError, crypto_from_settings
from app.telegram.adapter import (
    TelegramAdapter,
    TelegramConnectionClient,
    TelegramFloodWaitError,
    TelegramInvalidSessionError,
    TelegramProfile,
    TelegramUnavailableError,
)
from app.telegram.session_crypto import TelegramSessionCryptoError


class TelegramConnectionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


@dataclass(frozen=True)
class TelegramConnectionResult:
    account: TelegramAccount
    changed: bool
    reconnected: bool = False


class TelegramConnectionManager:
    """Owns at most one process-local persistent Telegram client."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        adapter_provider: Callable[[], TelegramAdapter | None],
    ) -> None:
        self._database = database
        self._settings = settings
        self._adapter_provider = adapter_provider
        self._lock = asyncio.Lock()
        self._client: TelegramConnectionClient | None = None
        self._account_id: uuid.UUID | None = None

    @property
    def client(self) -> TelegramConnectionClient | None:
        return self._client

    async def _active_account(
        self, session: AsyncSession, *, lock: bool = False
    ) -> TelegramAccount | None:
        query = select(TelegramAccount).where(TelegramAccount.is_active.is_(True))
        if lock:
            query = query.with_for_update()
        return (await session.execute(query)).scalar_one_or_none()

    async def _audit(
        self,
        session: AsyncSession,
        event_type: str,
        account: TelegramAccount,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await add_audit(
            session,
            event_type,
            actor_id,
            "telegram_account",
            account.id,
            ip_address,
            user_agent,
            metadata,
        )

    async def _safe_close(self, client: TelegramConnectionClient | None) -> None:
        if client is None:
            return
        try:
            await asyncio.wait_for(
                client.disconnect(), timeout=self._settings.telegram_connect_timeout_seconds
            )
        except Exception:
            pass

    async def _record_failure(
        self,
        account_id: uuid.UUID,
        error: TelegramConnectionError,
        actor_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        async with self._database.session_factory() as session:
            account = (
                await session.execute(
                    select(TelegramAccount)
                    .where(TelegramAccount.id == account_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if account is None:
                return
            account.status = (
                TelegramAccountStatus.NOT_CONFIGURED
                if error.code == "NOT_CONFIGURED"
                else TelegramAccountStatus.ERROR
            )
            account.last_checked_at = utcnow()
            account.last_error_code = error.code
            account.last_error_message = error.message[:500]
            await self._audit(
                session,
                "TELEGRAM_CONNECTION_FAILED",
                account,
                actor_id,
                ip_address,
                user_agent,
                {"failure_code": error.code},
            )
            await session.commit()

    def _configuration_error(self) -> TelegramConnectionError | None:
        if (
            self._settings.telegram_api_id is None
            or self._settings.telegram_api_hash is None
            or self._settings.telegram_session_encryption_key is None
            or self._adapter_provider() is None
        ):
            return TelegramConnectionError("NOT_CONFIGURED", "Telegram не настроен")
        return None

    @staticmethod
    def _profile_matches(account: TelegramAccount, profile: TelegramProfile) -> bool:
        return account.telegram_user_id is not None and account.telegram_user_id == profile.user_id

    @staticmethod
    def _update_profile(account: TelegramAccount, profile: TelegramProfile) -> None:
        account.username = profile.username
        account.first_name = profile.first_name
        account.last_name = profile.last_name

    async def connect(
        self,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TelegramConnectionResult:
        async with self._lock:
            async with self._database.session_factory() as session:
                account = await self._active_account(session, lock=True)
                if account is None:
                    raise TelegramConnectionError(
                        "NO_ACTIVE_ACCOUNT", "Активный Telegram-аккаунт отсутствует"
                    )
                if (
                    self._client is not None
                    and self._account_id == account.id
                    and self._client.is_connected()
                ):
                    return TelegramConnectionResult(account=account, changed=False)
                account_id = account.id
                configuration_error = self._configuration_error()
                if configuration_error is not None:
                    await session.rollback()
                    await self._record_failure(
                        account_id,
                        configuration_error,
                        actor_id,
                        ip_address,
                        user_agent,
                    )
                    raise configuration_error
                if account.encrypted_session is None or account.session_nonce is None:
                    error = TelegramConnectionError(
                        "SESSION_MISSING", "Требуется новая авторизация Telegram"
                    )
                    await session.rollback()
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error
                account.status = TelegramAccountStatus.CONNECTING
                await session.commit()
                reconnected = account.connected_at is not None
                encrypted_session = account.encrypted_session
                session_nonce = account.session_nonce

            client: TelegramConnectionClient | None = None
            try:
                try:
                    string_session = crypto_from_settings(self._settings).decrypt(
                        encrypted_session, session_nonce
                    )
                except (TelegramNotConfiguredError, TelegramSessionCryptoError) as cause:
                    raise TelegramConnectionError(
                        "INVALID_SESSION_DATA", "Сохранённая Telegram-сессия недействительна"
                    ) from cause
                adapter = self._adapter_provider()
                if adapter is None:
                    raise TelegramConnectionError("NOT_CONFIGURED", "Telegram не настроен")
                client = adapter.create_connection_client(string_session)

                async def handshake() -> TelegramProfile:
                    await client.connect()
                    if not await client.is_user_authorized():
                        raise TelegramConnectionError(
                            "UNAUTHORIZED_SESSION", "Требуется новая авторизация Telegram"
                        )
                    return await client.get_me()

                profile = await asyncio.wait_for(
                    handshake(), timeout=self._settings.telegram_connect_timeout_seconds
                )
                async with self._database.session_factory() as session:
                    account = (
                        await session.execute(
                            select(TelegramAccount)
                            .where(TelegramAccount.id == account_id)
                            .with_for_update()
                        )
                    ).scalar_one()
                    if not self._profile_matches(account, profile):
                        raise TelegramConnectionError(
                            "TELEGRAM_USER_MISMATCH",
                            "Telegram-сессия принадлежит другому аккаунту",
                        )
                    self._update_profile(account, profile)
                    account.status = TelegramAccountStatus.CONNECTED
                    account.connected_at = utcnow()
                    account.last_checked_at = utcnow()
                    account.last_error_code = None
                    account.last_error_message = None
                    await self._audit(
                        session,
                        (
                            "TELEGRAM_ACCOUNT_RECONNECTED"
                            if reconnected
                            else "TELEGRAM_ACCOUNT_CONNECTED"
                        ),
                        account,
                        actor_id,
                        ip_address,
                        user_agent,
                    )
                    await session.commit()
                self._client = client
                self._account_id = account_id
                return TelegramConnectionResult(
                    account=account, changed=True, reconnected=reconnected
                )
            except TelegramConnectionError as error:
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                await self._record_failure(account_id, error, actor_id, ip_address, user_agent)
                raise
            except TelegramInvalidSessionError as cause:
                failure = TelegramConnectionError(
                    "INVALID_SESSION", "Требуется новая авторизация Telegram"
                )
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                await self._record_failure(
                    account_id, failure, actor_id, ip_address, user_agent
                )
                raise failure from cause
            except TelegramFloodWaitError as cause:
                failure = TelegramConnectionError(
                    "FLOOD_WAIT",
                    "Telegram временно ограничил запросы",
                    retry_after=cause.seconds,
                )
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                await self._record_failure(
                    account_id, failure, actor_id, ip_address, user_agent
                )
                raise failure from cause
            except TimeoutError as cause:
                failure = TelegramConnectionError("TIMEOUT", "Превышен timeout Telegram")
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                await self._record_failure(
                    account_id, failure, actor_id, ip_address, user_agent
                )
                raise failure from cause
            except TelegramUnavailableError as cause:
                failure = TelegramConnectionError(
                    "TELEGRAM_UNAVAILABLE", "Telegram временно недоступен"
                )
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                await self._record_failure(
                    account_id, failure, actor_id, ip_address, user_agent
                )
                raise failure from cause

    async def disconnect(
        self,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TelegramConnectionResult:
        async with self._lock:
            async with self._database.session_factory() as session:
                account = await self._active_account(session, lock=True)
                if account is None:
                    raise TelegramConnectionError(
                        "NO_ACTIVE_ACCOUNT", "Активный Telegram-аккаунт отсутствует"
                    )
                client = self._client if self._account_id == account.id else None
                account_id = account.id
                if client is None or not client.is_connected():
                    account.status = TelegramAccountStatus.DISCONNECTED
                    await session.commit()
                    self._client = None
                    self._account_id = None
                    return TelegramConnectionResult(account=account, changed=False)
                try:
                    await asyncio.wait_for(
                        client.disconnect(),
                        timeout=self._settings.telegram_connect_timeout_seconds,
                    )
                    string_session = client.save_session()
                    encrypted_session, nonce = crypto_from_settings(self._settings).encrypt(
                        string_session
                    )
                except TimeoutError as cause:
                    error = TelegramConnectionError("TIMEOUT", "Превышен timeout Telegram")
                    await session.rollback()
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                except TelegramUnavailableError as cause:
                    error = TelegramConnectionError(
                        "TELEGRAM_UNAVAILABLE", "Telegram временно недоступен"
                    )
                    await session.rollback()
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                except (TelegramNotConfiguredError, TelegramSessionCryptoError) as cause:
                    error = TelegramConnectionError(
                        "INVALID_SESSION_DATA",
                        "Не удалось безопасно сохранить Telegram-сессию",
                    )
                    await session.rollback()
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                account.encrypted_session = encrypted_session
                account.session_nonce = nonce
                account.status = TelegramAccountStatus.DISCONNECTED
                account.disconnected_at = utcnow()
                account.last_error_code = None
                account.last_error_message = None
                await self._audit(
                    session,
                    "TELEGRAM_ACCOUNT_DISCONNECTED",
                    account,
                    actor_id,
                    ip_address,
                    user_agent,
                )
                await session.commit()
                self._client = None
                self._account_id = None
                return TelegramConnectionResult(account=account, changed=True)

    async def check(
        self,
        actor_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TelegramConnectionResult:
        async with self._lock:
            async with self._database.session_factory() as session:
                account = await self._active_account(session, lock=True)
                if account is None:
                    raise TelegramConnectionError(
                        "NO_ACTIVE_ACCOUNT", "Активный Telegram-аккаунт отсутствует"
                    )
                client = self._client if self._account_id == account.id else None
                account_id = account.id
                if client is None or not client.is_connected():
                    raise TelegramConnectionError("NOT_CONNECTED", "Telegram-аккаунт не подключён")
                try:

                    async def inspect_connection() -> TelegramProfile:
                        if not await client.is_user_authorized():
                            raise TelegramInvalidSessionError
                        return await client.get_me()

                    profile = await asyncio.wait_for(
                        inspect_connection(),
                        timeout=self._settings.telegram_connect_timeout_seconds,
                    )
                    if not self._profile_matches(account, profile):
                        raise TelegramInvalidSessionError
                except TelegramInvalidSessionError as cause:
                    error = TelegramConnectionError(
                        "INVALID_SESSION", "Требуется новая авторизация Telegram"
                    )
                    await session.rollback()
                    await self._safe_close(client)
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                except TelegramFloodWaitError as cause:
                    error = TelegramConnectionError(
                        "FLOOD_WAIT",
                        "Telegram временно ограничил запросы",
                        retry_after=cause.seconds,
                    )
                    await session.rollback()
                    await self._safe_close(client)
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                except TimeoutError as cause:
                    error = TelegramConnectionError("TIMEOUT", "Превышен timeout Telegram")
                    await session.rollback()
                    await self._safe_close(client)
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                except TelegramUnavailableError as cause:
                    error = TelegramConnectionError(
                        "TELEGRAM_UNAVAILABLE", "Telegram временно недоступен"
                    )
                    await session.rollback()
                    await self._safe_close(client)
                    self._client = None
                    self._account_id = None
                    await self._record_failure(
                        account_id, error, actor_id, ip_address, user_agent
                    )
                    raise error from cause
                self._update_profile(account, profile)
                account.status = TelegramAccountStatus.CONNECTED
                account.last_checked_at = utcnow()
                account.last_error_code = None
                account.last_error_message = None
                await self._audit(
                    session,
                    "TELEGRAM_CONNECTION_CHECKED",
                    account,
                    actor_id,
                    ip_address,
                    user_agent,
                )
                await session.commit()
                return TelegramConnectionResult(account=account, changed=False)

    async def remove_session(
        self,
        actor_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TelegramAccount:
        async with self._lock:
            async with self._database.session_factory() as session:
                account = await self._active_account(session, lock=True)
                if account is None:
                    raise TelegramConnectionError(
                        "NO_ACTIVE_ACCOUNT", "Активный Telegram-аккаунт отсутствует"
                    )
                client = self._client if self._account_id == account.id else None
                await self._safe_close(client)
                self._client = None
                self._account_id = None
                account.encrypted_session = None
                account.session_nonce = None
                account.is_active = False
                account.status = TelegramAccountStatus.DISCONNECTED
                account.disconnected_at = utcnow()
                account.last_error_code = None
                account.last_error_message = None
                await self._audit(
                    session,
                    "TELEGRAM_SESSION_REMOVED",
                    account,
                    actor_id,
                    ip_address,
                    user_agent,
                )
                await session.commit()
                return account

    async def startup_recovery(self) -> None:
        async with self._database.session_factory() as session:
            account = await self._active_account(session)
            if account is None or account.encrypted_session is None:
                return
        try:
            await self.connect()
        except TelegramConnectionError:
            return

    async def shutdown(self) -> None:
        if self._client is None:
            return
        try:
            await self.disconnect()
        except TelegramConnectionError:
            await self._safe_close(self._client)
            self._client = None
            self._account_id = None
