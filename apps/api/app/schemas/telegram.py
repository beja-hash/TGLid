from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import TelegramAccountStatus


class TelegramAccountStatusResponse(BaseModel):
    """Safe account status intended for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_user_id: int | None
    phone_masked: str | None
    username: str | None
    first_name: str | None
    last_name: str | None
    status: TelegramAccountStatus
    is_active: bool
    connected_at: datetime | None
    disconnected_at: datetime | None
    last_checked_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class TelegramAccountResponse(BaseModel):
    """Safe lifecycle status without session material or credentials."""

    configured: bool
    id: uuid.UUID | None = None
    telegram_user_id: int | None = None
    phone_masked: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: TelegramAccountStatus = TelegramAccountStatus.NOT_CONFIGURED
    is_active: bool = False
    connected_at: datetime | None = None
    disconnected_at: datetime | None = None
    last_checked_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
