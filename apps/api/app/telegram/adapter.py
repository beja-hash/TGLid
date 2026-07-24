from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from telethon import TelegramClient, errors
from telethon.sessions import StringSession


@dataclass(frozen=True)
class TelegramProfile:
    user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


@dataclass(frozen=True)
class TelegramAuthStart:
    string_session: str
    phone_code_hash: str


@dataclass(frozen=True)
class TelegramAuthComplete:
    string_session: str
    profile: TelegramProfile


class TelegramAuthError(Exception):
    """Base class for safe Telegram authorization errors."""


class TelegramCodeInvalidError(TelegramAuthError):
    pass


class TelegramCodeExpiredError(TelegramAuthError):
    pass


class TelegramPasswordRequiredError(TelegramAuthError):
    pass


class TelegramPasswordInvalidError(TelegramAuthError):
    pass


class TelegramFloodWaitError(TelegramAuthError):
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds


class TelegramUnavailableError(TelegramAuthError):
    pass


class TelegramInvalidSessionError(TelegramAuthError):
    pass


class TelegramConnectionClient(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def is_user_authorized(self) -> bool: ...

    async def get_me(self) -> TelegramProfile: ...

    def is_connected(self) -> bool: ...

    def save_session(self) -> str: ...


class TelegramAdapter(Protocol):
    """Abstract boundary for a future Telegram implementation."""

    async def start_auth(self, phone: str) -> TelegramAuthStart: ...

    async def verify_code(
        self, string_session: str, phone: str, phone_code_hash: str, code: str
    ) -> TelegramAuthComplete: ...

    async def verify_password(self, string_session: str, password: str) -> TelegramAuthComplete: ...

    def create_connection_client(self, string_session: str) -> TelegramConnectionClient: ...


class FakeTelegramConnectionClient(TelegramConnectionClient):
    def __init__(self, adapter: FakeTelegramAdapter, string_session: str) -> None:
        self._adapter = adapter
        self._string_session = string_session
        self._connected = False

    async def connect(self) -> None:
        self._adapter.connection_attempts += 1
        if self._adapter.connection_result == "timeout":
            raise TimeoutError
        if self._adapter.connection_result == "unavailable":
            raise TelegramUnavailableError
        if self._adapter.connection_result == "flood_wait":
            raise TelegramFloodWaitError(60)
        if self._adapter.connection_result == "invalid_session":
            raise TelegramInvalidSessionError
        self._connected = True

    async def disconnect(self) -> None:
        self._adapter.disconnect_calls += 1
        self._connected = False

    async def is_user_authorized(self) -> bool:
        return self._adapter.connection_result != "unauthorized"

    async def get_me(self) -> TelegramProfile:
        self._adapter.get_me_calls += 1
        outcome = (
            self._adapter.check_result
            if self._adapter.get_me_calls > 1
            else self._adapter.connection_result
        )
        if outcome == "invalid_session" or outcome == "unauthorized":
            raise TelegramInvalidSessionError
        if outcome == "timeout":
            raise TimeoutError
        if outcome == "unavailable":
            raise TelegramUnavailableError
        if outcome == "flood_wait":
            raise TelegramFloodWaitError(60)
        return self._adapter.profile

    def is_connected(self) -> bool:
        return self._connected

    def save_session(self) -> str:
        return self._adapter.connection_session or self._string_session


class FakeTelegramAdapter(TelegramAdapter):
    """Configurable test double that never performs Telegram network operations."""

    def __init__(
        self,
        *,
        code_result: str = "success",
        password_result: str = "success",
        connection_result: str = "success",
        check_result: str = "success",
        connection_session: str | None = None,
        profile: TelegramProfile | None = None,
    ) -> None:
        self.code_result = code_result
        self.password_result = password_result
        self.connection_result = connection_result
        self.check_result = check_result
        self.connection_session = connection_session
        self.profile = profile or TelegramProfile(100_001, "fake_user", "Fake", None)
        self.connection_clients_created = 0
        self.connection_attempts = 0
        self.disconnect_calls = 0
        self.get_me_calls = 0

    async def start_auth(self, phone: str) -> TelegramAuthStart:
        del phone
        if self.code_result == "unavailable":
            raise TelegramUnavailableError
        if self.code_result == "flood_wait":
            raise TelegramFloodWaitError(60)
        return TelegramAuthStart("fake-temporary-string-session", "fake-phone-code-hash")

    async def verify_code(
        self, string_session: str, phone: str, phone_code_hash: str, code: str
    ) -> TelegramAuthComplete:
        del string_session, phone, phone_code_hash, code
        if self.code_result == "invalid_code":
            raise TelegramCodeInvalidError
        if self.code_result == "expired_code":
            raise TelegramCodeExpiredError
        if self.code_result == "password_required":
            raise TelegramPasswordRequiredError
        if self.code_result == "flood_wait":
            raise TelegramFloodWaitError(60)
        if self.code_result == "unavailable":
            raise TelegramUnavailableError
        return TelegramAuthComplete("fake-permanent-string-session", self.profile)

    async def verify_password(self, string_session: str, password: str) -> TelegramAuthComplete:
        del string_session, password
        if self.password_result == "invalid_password":
            raise TelegramPasswordInvalidError
        if self.password_result == "flood_wait":
            raise TelegramFloodWaitError(60)
        if self.password_result == "unavailable":
            raise TelegramUnavailableError
        return TelegramAuthComplete("fake-permanent-string-session", self.profile)

    def create_connection_client(self, string_session: str) -> TelegramConnectionClient:
        self.connection_clients_created += 1
        return FakeTelegramConnectionClient(self, string_session)


class TelethonConnectionClient(TelegramConnectionClient):
    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    async def connect(self) -> None:
        try:
            await self._client.connect()
        except errors.FloodWaitError as error:
            raise TelegramFloodWaitError(error.seconds) from error
        except (
            errors.AuthKeyUnregisteredError,
            errors.SessionRevokedError,
        ) as error:
            raise TelegramInvalidSessionError from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error

    async def is_user_authorized(self) -> bool:
        try:
            return bool(await self._client.is_user_authorized())
        except (
            errors.AuthKeyUnregisteredError,
            errors.SessionRevokedError,
        ) as error:
            raise TelegramInvalidSessionError from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error

    async def get_me(self) -> TelegramProfile:
        try:
            user = await self._client.get_me()
        except (
            errors.AuthKeyUnregisteredError,
            errors.SessionRevokedError,
        ) as error:
            raise TelegramInvalidSessionError from error
        except errors.FloodWaitError as error:
            raise TelegramFloodWaitError(error.seconds) from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error
        if user is None:
            raise TelegramInvalidSessionError
        return TelethonTelegramAdapter._profile(user)

    def is_connected(self) -> bool:
        return bool(self._client.is_connected())

    def save_session(self) -> str:
        return cast(str, self._client.session.save())


class TelethonTelegramAdapter(TelegramAdapter):
    """Short-lived Telethon client used only for the authorization exchange."""

    def __init__(self, api_id: int, api_hash: str, timeout_seconds: int) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._timeout_seconds = timeout_seconds

    def _client(self, string_session: str | None = None) -> TelegramClient:
        return TelegramClient(
            StringSession(string_session),
            self._api_id,
            self._api_hash,
            timeout=self._timeout_seconds,
            connection_retries=0,
            retry_delay=0,
        )

    @staticmethod
    def _profile(user: Any) -> TelegramProfile:
        return TelegramProfile(
            user_id=int(user.id),
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )

    async def start_auth(self, phone: str) -> TelegramAuthStart:
        client = self._client()
        try:
            await client.connect()
            sent_code = await client.send_code_request(phone)
            return TelegramAuthStart(client.session.save(), sent_code.phone_code_hash)
        except errors.FloodWaitError as error:
            raise TelegramFloodWaitError(error.seconds) from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error
        finally:
            await client.disconnect()

    async def verify_code(
        self, string_session: str, phone: str, phone_code_hash: str, code: str
    ) -> TelegramAuthComplete:
        client = self._client(string_session)
        try:
            await client.connect()
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            user = await client.get_me()
            if user is None:
                raise TelegramUnavailableError
            return TelegramAuthComplete(client.session.save(), self._profile(user))
        except errors.PhoneCodeInvalidError as error:
            raise TelegramCodeInvalidError from error
        except errors.PhoneCodeExpiredError as error:
            raise TelegramCodeExpiredError from error
        except errors.SessionPasswordNeededError as error:
            raise TelegramPasswordRequiredError from error
        except errors.FloodWaitError as error:
            raise TelegramFloodWaitError(error.seconds) from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error
        finally:
            await client.disconnect()

    async def verify_password(self, string_session: str, password: str) -> TelegramAuthComplete:
        client = self._client(string_session)
        try:
            await client.connect()
            await client.sign_in(password=password)
            user = await client.get_me()
            if user is None:
                raise TelegramUnavailableError
            return TelegramAuthComplete(client.session.save(), self._profile(user))
        except errors.PasswordHashInvalidError as error:
            raise TelegramPasswordInvalidError from error
        except errors.FloodWaitError as error:
            raise TelegramFloodWaitError(error.seconds) from error
        except (OSError, errors.RPCError) as error:
            raise TelegramUnavailableError from error
        finally:
            await client.disconnect()

    def create_connection_client(self, string_session: str) -> TelegramConnectionClient:
        return TelethonConnectionClient(self._client(string_session))
