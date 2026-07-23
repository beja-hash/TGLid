from __future__ import annotations

from typing import cast

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import request_id_context


def error_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "REQUEST_ERROR")


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    http_error = cast(HTTPException, exc)
    message = http_error.detail if isinstance(http_error.detail, str) else "Запрос не выполнен"
    response = JSONResponse(
        status_code=http_error.status_code,
        headers=http_error.headers,
        content={
            "error": {
                "code": error_code(http_error.status_code),
                "message": message,
                "request_id": request_id_context.get(),
            }
        },
    )
    if http_error.status_code == 401:
        settings = get_settings()
        if request.cookies.get(settings.session_cookie_name):
            response.delete_cookie(
                settings.session_cookie_name,
                path="/",
                domain=settings.session_cookie_domain,
            )
            response.delete_cookie(
                settings.csrf_cookie_name,
                path="/",
                domain=settings.session_cookie_domain,
            )
    return response


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    del request, exc
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Проверьте формат и значения полей",
                "request_id": request_id_context.get(),
            }
        },
    )
