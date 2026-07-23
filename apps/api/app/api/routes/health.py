from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_health_service, require_password_changed
from app.core.config import Settings, get_settings
from app.db.models import User
from app.schemas.health import (
    DependencyResponse,
    HealthResponse,
    ReadinessResponse,
    SystemStatusResponse,
)
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="api")


async def get_readiness(service: HealthService) -> ReadinessResponse:
    dependencies = await service.readiness()
    is_ready = all(value == "ok" for value in dependencies.values())
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        dependencies={
            name: DependencyResponse(status=value) for name, value in dependencies.items()
        },
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response, service: HealthService = Depends(get_health_service)
) -> ReadinessResponse:
    result = await get_readiness(service)
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("/api/v1/system/status", response_model=SystemStatusResponse)
async def system_status(
    _user: Annotated[User, Depends(require_password_changed)],
    service: HealthService = Depends(get_health_service),
    settings: Settings = Depends(get_settings),
) -> SystemStatusResponse:
    dependencies = await service.readiness()
    return SystemStatusResponse(
        api="ok",
        postgres=dependencies["postgres"],
        redis=dependencies["redis"],
        environment=settings.app_env,
    )
