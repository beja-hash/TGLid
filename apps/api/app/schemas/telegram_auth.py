from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.db.models import TelegramAccountStatus


class TelegramAuthStartRequest(BaseModel):
    phone: str = Field(min_length=3, max_length=32)


class TelegramAuthVerifyCodeRequest(BaseModel):
    challenge_id: str = Field(min_length=32, max_length=128)
    phone: str = Field(min_length=3, max_length=32)
    code: str = Field(min_length=1, max_length=16)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = "".join(value.split())
        if not normalized:
            raise ValueError("code cannot be empty")
        return normalized


class TelegramAuthVerifyPasswordRequest(BaseModel):
    challenge_id: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class TelegramAuthChallengeResponse(BaseModel):
    challenge_id: str
    status: TelegramAccountStatus
    phone_masked: str
