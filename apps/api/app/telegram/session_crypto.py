from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32
_ERROR_MESSAGE = "Telegram session encryption data is invalid."


class TelegramSessionCryptoError(ValueError):
    """Safe error for unusable Telegram session encryption data."""


class TelegramSessionCrypto:
    """Encrypts a Telethon StringSession using AES-256-GCM."""

    def __init__(self, encryption_key: str | bytes) -> None:
        self._key = self._decode_key(encryption_key)
        self._cipher = AESGCM(self._key)

    @staticmethod
    def _decode_key(encryption_key: str | bytes) -> bytes:
        encoded = (
            encryption_key.encode("ascii") if isinstance(encryption_key, str) else encryption_key
        )
        try:
            key = base64.b64decode(encoded, altchars=b"-_", validate=True)
        except (UnicodeEncodeError, ValueError, binascii.Error) as error:
            raise TelegramSessionCryptoError(_ERROR_MESSAGE) from error
        if len(key) != _KEY_BYTES:
            raise TelegramSessionCryptoError(_ERROR_MESSAGE)
        return key

    def encrypt(self, string_session: str) -> tuple[bytes, bytes]:
        nonce = os.urandom(_NONCE_BYTES)
        return self._cipher.encrypt(nonce, string_session.encode("utf-8"), None), nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        try:
            plaintext = self._cipher.decrypt(nonce, ciphertext, None)
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError) as error:
            raise TelegramSessionCryptoError(_ERROR_MESSAGE) from error
