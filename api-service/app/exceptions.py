"""Custom exception classes + FastAPI handlers.

Response envelope follows INTEGRATION_CONTRACT section 7:

    { "success": false, "error": { "code": ..., "message": ..., ... } }
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_logger

log = get_logger(__name__)


_STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    410: "GONE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    451: "BLOCKED",
}


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    code: str = "INTERNAL"

    def __init__(self, message: str, *, code: str | None = None, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.extra = extra


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class BadRequest(AppError):
    status_code = 400
    code = "BAD_REQUEST"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"


def _envelope(code: str, message: str, **extra: Any) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    err.update({k: v for k, v in extra.items() if v is not None})
    return {"success": False, "error": err}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, **exc.extra),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_: Request, exc: StarletteHTTPException) -> ORJSONResponse:
        code = _STATUS_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        return ORJSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> ORJSONResponse:
        # Strip the raw `input` value from each error dict — for sensitive
        # bodies (RegisterIn/LoginIn/PasswordChange) this would otherwise
        # surface the user's password in logs + 422 responses. `ctx` can
        # also carry regex/error objects that don't serialise cleanly.
        details = []
        for err in exc.errors():
            d = dict(err)
            d.pop("input", None)
            d.pop("ctx", None)
            details.append(d)
        return ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope("VALIDATION_ERROR", "Invalid payload", details=details),
        )

    @app.exception_handler(IntegrityError)
    async def _integ(_: Request, exc: IntegrityError) -> ORJSONResponse:
        log.warning("integrity_error", err=str(exc.orig))
        return ORJSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_envelope("CONFLICT", "Resource conflict"),
        )

    @app.exception_handler(Exception)
    async def _catch_all(request: Request, exc: Exception) -> ORJSONResponse:
        log.exception("unhandled_exception", path=request.url.path, err=str(exc))
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL", "Internal server error"),
        )
