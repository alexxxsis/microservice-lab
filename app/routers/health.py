"""Служебные эндпоинты: проверка живости и готовности сервиса."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy.exc import SQLAlchemyError

from ..config import settings
from ..db import check_database
from ..errors import ApiError
from ..logging_conf import logger
from ..schemas import HealthResponse

router = APIRouter(tags=["Служебные"])


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Проверка живости процесса",
    description="Отвечает 200, если процесс сервиса запущен. Используется в Docker HEALTHCHECK.",
)
def liveness() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        environment=settings.app_env,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Проверка готовности (включая БД)",
    description="Проверяет соединение с PostgreSQL. Если БД недоступна — возвращает 503.",
    responses={503: {"description": "База данных недоступна"}},
)
def readiness(response: Response) -> HealthResponse:
    try:
        info = check_database()
    except SQLAlchemyError as exc:
        logger.error("healthcheck_database_failed", extra={"event": "health_db_failed", "error": str(exc)})
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATABASE_UNAVAILABLE",
            "База данных недоступна: сервис запущен, но не может отвечать на запросы к данным",
        ) from exc

    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        environment=settings.app_env,
        database=info["database"],
        server_version=info["server_version"],
    )
