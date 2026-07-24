from __future__ import annotations

import base64
import json
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_token
from app.db.models import TelegramAccount, TelegramAccountStatus, User
from app.services.auth import utcnow
from app.telegram.adapter import TelegramAuthComplete
from app.telegram.session_crypto import TelegramSessionCrypto, TelegramSessionCryptoError

_KEY_PREFIX = "telegram_auth_challenge:"
_USED_PREFIX = "telegram_auth_challenge_used:"
_BLOCKED_PREFIX = "telegram_auth_challenge_blocked:"
_ATTEMPTS_PREFIX = "telegram_auth_challenge_attempts:"


class TelegramChallengeError(Exception):
    """Base class for safe temporary authorization state errors."""


class TelegramChallengeExpiredError(TelegramChallengeError):
    pass


class TelegramChallengeUsedError(TelegramChallengeError):
    pass


class TelegramChallengeAttemptsExceededError(TelegramChallengeError):
    pass


class TelegramChallengeAccessError(TelegramChallengeError):
    pass


class TelegramChallengeStageError(TelegramChallengeError):
    pass


class TelegramRedisUnavailableError(TelegramChallengeError):
    pass


class TelegramNotConfiguredError(TelegramChallengeError):
    pass


@dataclass(frozen=True)
class TelegramChallenge:
    challenge_id: str
    administrator_id: uuid.UUID
    status: TelegramAccountStatus
    phone_masked: str
    phone_hash: str
    encrypted_session: bytes
    session_nonce: bytes
    phone_code_hash: str
    ttl_seconds: int


def normalize_phone(phone: str) -> str:
    stripped = phone.strip()
    normalized = "+" + "".join(character for character in stripped if character.isdigit())
    if len(normalized) < 8 or len(normalized) > 17:
        raise ValueError("Неверный формат номера телефона")
    return normalized


def mask_phone(phone: str) -> str:
    return f"{phone[:2]} *** ***-{phone[-2:]}"


def crypto_from_settings(settings: Settings) -> TelegramSessionCrypto:
    key = settings.telegram_session_encryption_key
    if key is None:
        raise TelegramNotConfiguredError
    try:
        return TelegramSessionCrypto(key.get_secret_value())
    except TelegramSessionCryptoError as error:
        raise TelegramNotConfiguredError from error


class TelegramChallengeStore:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._ttl_seconds = settings.telegram_auth_challenge_ttl_seconds
        self._max_attempts = settings.telegram_auth_max_attempts

    @staticmethod
    def _key(challenge_id: str) -> str:
        return f"{_KEY_PREFIX}{challenge_id}"

    @staticmethod
    def _used_key(challenge_id: str) -> str:
        return f"{_USED_PREFIX}{challenge_id}"

    @staticmethod
    def _blocked_key(challenge_id: str) -> str:
        return f"{_BLOCKED_PREFIX}{challenge_id}"

    @staticmethod
    def _attempts_key(challenge_id: str) -> str:
        return f"{_ATTEMPTS_PREFIX}{challenge_id}"

    @staticmethod
    def _serialize(challenge: TelegramChallenge) -> str:
        return json.dumps(
            {
                "administrator_id": str(challenge.administrator_id),
                "status": challenge.status.value,
                "phone_masked": challenge.phone_masked,
                "phone_hash": challenge.phone_hash,
                "encrypted_session": base64.b64encode(challenge.encrypted_session).decode("ascii"),
                "session_nonce": base64.b64encode(challenge.session_nonce).decode("ascii"),
                "phone_code_hash": challenge.phone_code_hash,
            },
            separators=(",", ":"),
        )

    @staticmethod
    def _deserialize(challenge_id: str, raw: bytes, ttl_seconds: int) -> TelegramChallenge:
        try:
            payload: dict[str, Any] = json.loads(raw)
            return TelegramChallenge(
                challenge_id=challenge_id,
                administrator_id=uuid.UUID(payload["administrator_id"]),
                status=TelegramAccountStatus(payload["status"]),
                phone_masked=str(payload["phone_masked"]),
                phone_hash=str(payload["phone_hash"]),
                encrypted_session=base64.b64decode(payload["encrypted_session"], validate=True),
                session_nonce=base64.b64decode(payload["session_nonce"], validate=True),
                phone_code_hash=str(payload["phone_code_hash"]),
                ttl_seconds=ttl_seconds,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise TelegramChallengeExpiredError from error

    async def create(
        self,
        administrator_id: uuid.UUID,
        phone_masked: str,
        phone_hash: str,
        encrypted_session: bytes,
        session_nonce: bytes,
        phone_code_hash: str,
    ) -> TelegramChallenge:
        challenge = TelegramChallenge(
            challenge_id=secrets.token_urlsafe(32),
            administrator_id=administrator_id,
            status=TelegramAccountStatus.AUTH_CODE_REQUIRED,
            phone_masked=phone_masked,
            phone_hash=phone_hash,
            encrypted_session=encrypted_session,
            session_nonce=session_nonce,
            phone_code_hash=phone_code_hash,
            ttl_seconds=self._ttl_seconds,
        )
        try:
            await self._redis.set(
                self._key(challenge.challenge_id), self._serialize(challenge), ex=self._ttl_seconds
            )
        except Exception as error:
            raise TelegramRedisUnavailableError from error
        return challenge

    async def get(self, challenge_id: str, administrator_id: uuid.UUID) -> TelegramChallenge:
        try:
            raw = await self._redis.get(self._key(challenge_id))
            if raw is None:
                if await self._redis.exists(self._used_key(challenge_id)):
                    raise TelegramChallengeUsedError
                if await self._redis.exists(self._blocked_key(challenge_id)):
                    raise TelegramChallengeAttemptsExceededError
                raise TelegramChallengeExpiredError
            ttl_seconds = max(int(await self._redis.ttl(self._key(challenge_id))), 1)
        except TelegramChallengeError:
            raise
        except Exception as error:
            raise TelegramRedisUnavailableError from error
        challenge = self._deserialize(challenge_id, raw, ttl_seconds)
        if challenge.administrator_id != administrator_id:
            raise TelegramChallengeAccessError
        return challenge

    async def set_status(
        self, challenge: TelegramChallenge, status: TelegramAccountStatus
    ) -> TelegramChallenge:
        updated = TelegramChallenge(
            challenge_id=challenge.challenge_id,
            administrator_id=challenge.administrator_id,
            status=status,
            phone_masked=challenge.phone_masked,
            phone_hash=challenge.phone_hash,
            encrypted_session=challenge.encrypted_session,
            session_nonce=challenge.session_nonce,
            phone_code_hash=challenge.phone_code_hash,
            ttl_seconds=challenge.ttl_seconds,
        )
        try:
            await self._redis.set(
                self._key(updated.challenge_id),
                self._serialize(updated),
                ex=updated.ttl_seconds,
            )
        except Exception as error:
            raise TelegramRedisUnavailableError from error
        return updated

    async def record_failed_attempt(self, challenge: TelegramChallenge) -> bool:
        try:
            count = int(await self._redis.incr(self._attempts_key(challenge.challenge_id)))
            if count == 1:
                await self._redis.expire(
                    self._attempts_key(challenge.challenge_id), challenge.ttl_seconds
                )
            if count < self._max_attempts:
                return False
            await self._redis.delete(
                self._key(challenge.challenge_id), self._attempts_key(challenge.challenge_id)
            )
            await self._redis.set(
                self._blocked_key(challenge.challenge_id), "1", ex=challenge.ttl_seconds
            )
            return True
        except Exception as error:
            raise TelegramRedisUnavailableError from error

    async def consume(self, challenge: TelegramChallenge) -> None:
        try:
            await self._redis.delete(
                self._key(challenge.challenge_id), self._attempts_key(challenge.challenge_id)
            )
            await self._redis.set(
                self._used_key(challenge.challenge_id), "1", ex=challenge.ttl_seconds
            )
        except Exception as error:
            raise TelegramRedisUnavailableError from error


async def save_authenticated_account(
    db: AsyncSession,
    administrator: User,
    challenge: TelegramChallenge,
    result: TelegramAuthComplete,
    crypto: TelegramSessionCrypto,
) -> TelegramAccount:
    encrypted_session, nonce = crypto.encrypt(result.string_session)
    account = (
        await db.execute(
            select(TelegramAccount).where(TelegramAccount.is_active.is_(True)).with_for_update()
        )
    ).scalar_one_or_none()
    if account is None:
        account = TelegramAccount(created_by_user_id=administrator.id)
        db.add(account)
    account.telegram_user_id = result.profile.user_id
    account.phone_masked = challenge.phone_masked
    account.username = result.profile.username
    account.first_name = result.profile.first_name
    account.last_name = result.profile.last_name
    account.status = TelegramAccountStatus.DISCONNECTED
    account.encrypted_session = encrypted_session
    account.session_nonce = nonce
    account.is_active = True
    account.connected_at = None
    account.disconnected_at = utcnow()
    account.last_checked_at = utcnow()
    account.last_error_code = None
    account.last_error_message = None
    account.created_by_user_id = administrator.id
    return account


def phone_matches(challenge: TelegramChallenge, phone: str) -> bool:
    return secrets.compare_digest(challenge.phone_hash, hash_token(normalize_phone(phone)))
