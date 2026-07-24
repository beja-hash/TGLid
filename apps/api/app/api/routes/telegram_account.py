from __future__ import annotations

from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.dependencies import DbSession, require_admin, require_csrf
from app.core.config import Settings, get_settings
from app.core.security import hash_token
from app.db.models import TelegramAccount, TelegramAccountStatus, User
from app.schemas.telegram import TelegramAccountResponse
from app.schemas.telegram_auth import (
    TelegramAuthChallengeResponse,
    TelegramAuthStartRequest,
    TelegramAuthVerifyCodeRequest,
    TelegramAuthVerifyPasswordRequest,
)
from app.services.auth import add_audit
from app.services.telegram_auth import (
    TelegramChallenge,
    TelegramChallengeAccessError,
    TelegramChallengeAttemptsExceededError,
    TelegramChallengeError,
    TelegramChallengeExpiredError,
    TelegramChallengeStore,
    TelegramChallengeUsedError,
    TelegramNotConfiguredError,
    TelegramRedisUnavailableError,
    crypto_from_settings,
    mask_phone,
    normalize_phone,
    phone_matches,
    save_authenticated_account,
)
from app.services.telegram_connection import (
    TelegramConnectionError,
    TelegramConnectionManager,
)
from app.telegram.adapter import (
    TelegramAdapter,
    TelegramAuthComplete,
    TelegramCodeExpiredError,
    TelegramCodeInvalidError,
    TelegramFloodWaitError,
    TelegramPasswordInvalidError,
    TelegramPasswordRequiredError,
    TelegramUnavailableError,
    TelethonTelegramAdapter,
)
from app.telegram.session_crypto import TelegramSessionCryptoError

router = APIRouter(prefix="/api/v1/telegram-account", tags=["telegram-account"])


def get_connection_manager(request: Request) -> TelegramConnectionManager:
    return cast(TelegramConnectionManager, request.app.state.telegram_connection_manager)


def lifecycle_response(
    account: TelegramAccount | None, settings: Settings
) -> TelegramAccountResponse:
    configured = (
        settings.telegram_api_id is not None
        and settings.telegram_api_hash is not None
        and settings.telegram_session_encryption_key is not None
    )
    if account is None:
        return TelegramAccountResponse(configured=configured)
    return TelegramAccountResponse(
        configured=configured,
        id=account.id,
        telegram_user_id=account.telegram_user_id,
        phone_masked=account.phone_masked,
        username=account.username,
        first_name=account.first_name,
        last_name=account.last_name,
        status=account.status,
        is_active=account.is_active,
        connected_at=account.connected_at,
        disconnected_at=account.disconnected_at,
        last_checked_at=account.last_checked_at,
        last_error_code=account.last_error_code,
        last_error_message=account.last_error_message,
    )


def raise_lifecycle_error(error: TelegramConnectionError) -> NoReturn:
    status_code = {
        "NO_ACTIVE_ACCOUNT": status.HTTP_404_NOT_FOUND,
        "NOT_CONFIGURED": status.HTTP_503_SERVICE_UNAVAILABLE,
        "TELEGRAM_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
        "FLOOD_WAIT": status.HTTP_429_TOO_MANY_REQUESTS,
    }.get(error.code, status.HTTP_409_CONFLICT)
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    raise HTTPException(status_code, error.message, headers=headers) from error


@router.get("", response_model=TelegramAccountResponse)
async def get_telegram_account(
    db: DbSession,
    _administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TelegramAccountResponse:
    account = (
        (
            await db.execute(
                select(TelegramAccount).order_by(
                    TelegramAccount.is_active.desc(), TelegramAccount.created_at.desc()
                )
            )
        )
        .scalars()
        .first()
    )
    return lifecycle_response(account, settings)


@router.post(
    "/connect",
    response_model=TelegramAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def connect_account(
    request: Request,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    manager: Annotated[TelegramConnectionManager, Depends(get_connection_manager)],
) -> TelegramAccountResponse:
    try:
        result = await manager.connect(administrator.id, *request_context(request))
    except TelegramConnectionError as error:
        raise_lifecycle_error(error)
    return lifecycle_response(result.account, settings)


@router.post(
    "/disconnect",
    response_model=TelegramAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def disconnect_account(
    request: Request,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    manager: Annotated[TelegramConnectionManager, Depends(get_connection_manager)],
) -> TelegramAccountResponse:
    try:
        result = await manager.disconnect(administrator.id, *request_context(request))
    except TelegramConnectionError as error:
        raise_lifecycle_error(error)
    return lifecycle_response(result.account, settings)


@router.post(
    "/check",
    response_model=TelegramAccountResponse,
    dependencies=[Depends(require_csrf)],
)
async def check_account(
    request: Request,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    manager: Annotated[TelegramConnectionManager, Depends(get_connection_manager)],
) -> TelegramAccountResponse:
    try:
        result = await manager.check(administrator.id, *request_context(request))
    except TelegramConnectionError as error:
        raise_lifecycle_error(error)
    return lifecycle_response(result.account, settings)


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def remove_account_session(
    request: Request,
    administrator: Annotated[User, Depends(require_admin)],
    manager: Annotated[TelegramConnectionManager, Depends(get_connection_manager)],
) -> None:
    try:
        await manager.remove_session(administrator.id, *request_context(request))
    except TelegramConnectionError as error:
        raise_lifecycle_error(error)


def request_context(request: Request) -> tuple[str | None, str | None]:
    return (
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


def get_adapter(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> TelegramAdapter:
    adapter = getattr(request.app.state, "telegram_adapter", None)
    if adapter is not None:
        return cast(TelegramAdapter, adapter)
    if settings.telegram_api_id is None or settings.telegram_api_hash is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен")
    return TelethonTelegramAdapter(
        settings.telegram_api_id,
        settings.telegram_api_hash.get_secret_value(),
        settings.telegram_connect_timeout_seconds,
    )


def challenge_response(challenge: TelegramChallenge) -> TelegramAuthChallengeResponse:
    return TelegramAuthChallengeResponse(
        challenge_id=challenge.challenge_id,
        status=challenge.status,
        phone_masked=challenge.phone_masked,
    )


async def audit(
    db: DbSession,
    request: Request,
    administrator: User,
    event_type: str,
    metadata: dict[str, object] | None = None,
) -> None:
    ip_address, user_agent = request_context(request)
    await add_audit(
        db,
        event_type,
        administrator.id,
        "telegram_account",
        None,
        ip_address,
        user_agent,
        metadata,
    )
    await db.commit()


async def challenge_or_error(
    store: TelegramChallengeStore, challenge_id: str, administrator: User
) -> TelegramChallenge:
    try:
        return await store.get(challenge_id, administrator.id)
    except TelegramChallengeAccessError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Challenge не найден") from error
    except TelegramChallengeExpiredError as error:
        raise HTTPException(status.HTTP_410_GONE, "Challenge истёк") from error
    except TelegramChallengeUsedError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "Challenge уже использован") from error
    except TelegramChallengeAttemptsExceededError as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток") from error
    except TelegramRedisUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Redis временно недоступен"
        ) from error


async def failed_attempt(
    store: TelegramChallengeStore,
    challenge: TelegramChallenge,
    db: DbSession,
    request: Request,
    administrator: User,
    event_type: str,
    message: str,
) -> NoReturn:
    try:
        blocked = await store.record_failed_attempt(challenge)
    except TelegramRedisUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Redis временно недоступен"
        ) from error
    await audit(db, request, administrator, event_type)
    if blocked:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток")
    raise HTTPException(status.HTTP_400_BAD_REQUEST, message)


async def flood_wait(
    db: DbSession,
    request: Request,
    administrator: User,
    error: TelegramFloodWaitError,
) -> None:
    await audit(db, request, administrator, "TELEGRAM_FLOOD_WAIT", {"wait_seconds": error.seconds})
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Telegram временно ограничил попытки",
        headers={"Retry-After": str(error.seconds)},
    )


@router.post(
    "/auth/start",
    response_model=TelegramAuthChallengeResponse,
    dependencies=[Depends(require_csrf)],
)
async def start_auth(
    payload: TelegramAuthStartRequest,
    request: Request,
    db: DbSession,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[TelegramAdapter, Depends(get_adapter)],
) -> TelegramAuthChallengeResponse:
    try:
        phone = normalize_phone(payload.phone)
        crypto = crypto_from_settings(settings)
        started = await adapter.start_auth(phone)
        encrypted_session, nonce = crypto.encrypt(started.string_session)
        challenge = await TelegramChallengeStore(
            cast(Redis, request.app.state.redis), settings
        ).create(
            administrator.id,
            mask_phone(phone),
            phone_hash=hash_token(phone),
            encrypted_session=encrypted_session,
            session_nonce=nonce,
            phone_code_hash=started.phone_code_hash,
        )
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Неверный формат номера телефона"
        ) from error
    except TelegramNotConfiguredError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    except TelegramRedisUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Redis временно недоступен"
        ) from error
    except TelegramFloodWaitError as error:
        await flood_wait(db, request, administrator, error)
    except TelegramUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    await audit(db, request, administrator, "TELEGRAM_AUTH_STARTED")
    return challenge_response(challenge)


@router.post(
    "/auth/verify-code",
    response_model=TelegramAuthChallengeResponse,
    dependencies=[Depends(require_csrf)],
)
async def verify_code(
    payload: TelegramAuthVerifyCodeRequest,
    request: Request,
    db: DbSession,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[TelegramAdapter, Depends(get_adapter)],
) -> TelegramAuthChallengeResponse:
    store = TelegramChallengeStore(cast(Redis, request.app.state.redis), settings)
    challenge = await challenge_or_error(store, payload.challenge_id, administrator)
    if challenge.status != TelegramAccountStatus.AUTH_CODE_REQUIRED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Challenge ожидает другой этап авторизации")
    try:
        phone = normalize_phone(payload.phone)
        if not phone_matches(challenge, phone):
            await failed_attempt(
                store,
                challenge,
                db,
                request,
                administrator,
                "TELEGRAM_AUTH_CODE_FAILED",
                "Неверный код Telegram",
            )
        session = crypto_from_settings(settings).decrypt(
            challenge.encrypted_session, challenge.session_nonce
        )
        completed = await adapter.verify_code(
            session,
            phone,
            challenge.phone_code_hash,
            payload.code,
        )
    except TelegramCodeInvalidError:
        await failed_attempt(
            store,
            challenge,
            db,
            request,
            administrator,
            "TELEGRAM_AUTH_CODE_FAILED",
            "Неверный код Telegram",
        )
    except TelegramCodeExpiredError:
        await failed_attempt(
            store,
            challenge,
            db,
            request,
            administrator,
            "TELEGRAM_AUTH_CODE_FAILED",
            "Код Telegram истёк",
        )
    except TelegramPasswordRequiredError:
        try:
            challenge = await store.set_status(
                challenge, TelegramAccountStatus.AUTH_PASSWORD_REQUIRED
            )
        except TelegramRedisUnavailableError as error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Redis временно недоступен"
            ) from error
        await audit(db, request, administrator, "TELEGRAM_AUTH_2FA_REQUIRED")
        return challenge_response(challenge)
    except TelegramFloodWaitError as error:
        await flood_wait(db, request, administrator, error)
    except (
        TelegramUnavailableError,
        TelegramNotConfiguredError,
        TelegramSessionCryptoError,
    ) as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    except TelegramChallengeError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    return await complete_auth(store, challenge, completed, db, request, administrator, settings)


@router.post(
    "/auth/verify-password",
    response_model=TelegramAuthChallengeResponse,
    dependencies=[Depends(require_csrf)],
)
async def verify_password(
    payload: TelegramAuthVerifyPasswordRequest,
    request: Request,
    db: DbSession,
    administrator: Annotated[User, Depends(require_admin)],
    settings: Annotated[Settings, Depends(get_settings)],
    adapter: Annotated[TelegramAdapter, Depends(get_adapter)],
) -> TelegramAuthChallengeResponse:
    store = TelegramChallengeStore(cast(Redis, request.app.state.redis), settings)
    challenge = await challenge_or_error(store, payload.challenge_id, administrator)
    if challenge.status != TelegramAccountStatus.AUTH_PASSWORD_REQUIRED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Challenge ожидает другой этап авторизации")
    try:
        session = crypto_from_settings(settings).decrypt(
            challenge.encrypted_session, challenge.session_nonce
        )
        completed = await adapter.verify_password(session, payload.password)
    except TelegramPasswordInvalidError:
        await failed_attempt(
            store,
            challenge,
            db,
            request,
            administrator,
            "TELEGRAM_AUTH_2FA_FAILED",
            "Неверный пароль 2FA",
        )
    except TelegramFloodWaitError as error:
        await flood_wait(db, request, administrator, error)
    except (
        TelegramUnavailableError,
        TelegramNotConfiguredError,
        TelegramSessionCryptoError,
    ) as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    except TelegramChallengeError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    return await complete_auth(store, challenge, completed, db, request, administrator, settings)


async def complete_auth(
    store: TelegramChallengeStore,
    challenge: TelegramChallenge,
    completed: TelegramAuthComplete,
    db: DbSession,
    request: Request,
    administrator: User,
    settings: Settings,
) -> TelegramAuthChallengeResponse:
    try:
        await save_authenticated_account(
            db,
            administrator,
            challenge,
            completed,
            crypto_from_settings(settings),
        )
        await audit(db, request, administrator, "TELEGRAM_AUTH_SUCCEEDED")
        await store.consume(challenge)
    except TelegramRedisUnavailableError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Redis временно недоступен"
        ) from error
    except TelegramNotConfiguredError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram временно недоступен"
        ) from error
    return TelegramAuthChallengeResponse(
        challenge_id=challenge.challenge_id,
        status=TelegramAccountStatus.DISCONNECTED,
        phone_masked=challenge.phone_masked,
    )
