"""Обработка ошибок: единый JSON-формат ответа и корректные HTTP-коды."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_conf import logger, request_id_ctx


class ApiError(Exception):
    """Бизнес-ошибка, которую нужно вернуть клиенту в едином формате."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Собирает ответ об ошибке в едином формате ``{"error": {...}, "request_id": ...}``."""
    body: dict[str, Any] = {
        "error": {"code": code, "message": message},
        "request_id": request_id_ctx.get() or None,
    }
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "UNPROCESSABLE_ENTITY",
    429: "TOO_MANY_REQUESTS",
}


def _format_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for err in errors:
        location = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        # у json_invalid в loc лежит позиция символа, а не имя поля
        if err.get("type") == "json_invalid":
            location = []
        formatted.append(
            {
                "field": ".".join(location) or "<body>",
                "message": err.get("msg", "Некорректное значение"),
                "type": err.get("type", "value_error"),
            }
        )
    return formatted


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует обработчики, чтобы сервис никогда не отдавал stack trace клиенту."""

    @app.exception_handler(ApiError)
    async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:  # noqa: ANN001
        logger.warning(
            "api_error",
            extra={
                "event": "api_error",
                "status": exc.status_code,
                "code": exc.code,
                "error_message": exc.message,
            },
        )
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = _format_validation_errors(list(exc.errors()))

        # Битый JSON — это именно некорректный синтаксис запроса, а не валидация полей.
        if details and details[0].get("type") == "json_invalid":
            logger.warning("invalid_json", extra={"event": "invalid_json"})
            return error_response(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_JSON",
                "Тело запроса не является корректным JSON",
                details,
            )

        logger.warning("validation_error", extra={"event": "validation_error", "details": details})
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Некорректные данные в запросе",
            details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "Ошибка HTTP"
        logger.warning("http_error", extra={"event": "http_error", "status": exc.status_code, "code": code})
        return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        logger.error("database_operational_error", extra={"event": "db_error", "error": str(exc.orig)})
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "База данных временно недоступна, попробуйте позже",
        )

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        logger.error(
            "database_error",
            extra={"event": "db_error", "error_type": type(exc).__name__, "error": str(exc.orig)},
            exc_info=exc,
        )
        if isinstance(exc, ProgrammingError):
            return error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "DATABASE_SCHEMA_ERROR",
                "Ошибка схемы базы данных",
            )
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "База данных временно недоступна, попробуйте позже",
        )
