"""Exception handlers mapping domain/application errors to the HTTP contract
(design ADR-03, ADR-13).

The category -> status map is resolved via `type(exc).__mro__`, so a new
concrete error needs no handler change as long as it subclasses one of the
four categories below.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.application.exceptions import AuthenticationError
from app.domain.exceptions import (
    AppError,
    BusinessRuleViolationError,
    ConflictError,
    NotFoundError,
)

logger = logging.getLogger(__name__)

_CATEGORY_STATUS: dict[type[AppError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    BusinessRuleViolationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
}


def _status_for(exc: AppError) -> int:
    for category, http_status in _CATEGORY_STATUS.items():
        if isinstance(exc, category):
            return http_status
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def _slug(detail: object) -> str:
    if not isinstance(detail, str) or not detail:
        return "http_error"
    return detail.lower().replace(" ", "_")


def register_exception_handlers(app: FastAPI) -> None:
    """Register the handler chain that keeps every error response uniform."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = (
            {"WWW-Authenticate": "Bearer"}
            if isinstance(exc, AuthenticationError)
            else None
        )
        return JSONResponse(
            status_code=_status_for(exc),
            content={"code": exc.code, "message": exc.message},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": details,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": _slug(exc.detail), "message": str(exc.detail)},
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception while processing request", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "internal_error", "message": "Internal server error"},
        )
