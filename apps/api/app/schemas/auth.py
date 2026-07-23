from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import UserRole


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    must_change_password: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: UserRole


class UpdateUserRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None


class CreatedUserResponse(UserProfile):
    temporary_password: str


class PaginatedUsers(BaseModel):
    items: list[UserProfile]
    total: int
    page: int
    page_size: int


class TemporaryPasswordResponse(BaseModel):
    user: UserProfile
    temporary_password: str


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    event_type: str
    target_type: str
    target_id: str | None
    ip_address: str | None
    user_agent: str | None
    metadata: dict[str, object]
    created_at: datetime


class PaginatedAuditLogs(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
