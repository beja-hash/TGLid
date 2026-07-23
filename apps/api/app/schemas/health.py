from typing import Literal

from pydantic import BaseModel

DependencyState = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["api"]


class DependencyResponse(BaseModel):
    status: DependencyState


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyResponse]


class SystemStatusResponse(BaseModel):
    api: Literal["ok"]
    postgres: DependencyState
    redis: DependencyState
    environment: str
