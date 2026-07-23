from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password(password: str, minimum_length: int) -> None:
    if not minimum_length <= len(password) <= 128 or not password.strip():
        raise ValueError(f"Пароль должен содержать от {minimum_length} до 128 символов")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), expected_hash)


def login_rate_limit_key(email: str, ip_address: str | None) -> str:
    material = f"{normalize_email(email)}\0{ip_address or 'unknown'}"
    return f"login:{hashlib.sha256(material.encode('utf-8')).hexdigest()}"


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(15)
