"""CRUD-эндпоинты для работы с задачами."""

from __future__ import annotations

import enum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..errors import ApiError
from ..logging_conf import logger
from ..models import Task, TaskPriority, TaskStatus
from ..schemas import ErrorResponse, TaskCreate, TaskList, TaskRead, TaskStats, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["Задачи"])

TaskId = Annotated[int, Path(ge=1, le=2_147_483_647, description="Идентификатор задачи")]


def _get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            f"Задача с идентификатором {task_id} не найдена",
        )
    return task


def _normalise(data: dict[str, Any], *, drop_nulls: tuple[str, ...] = ()) -> dict[str, Any]:
    """Преобразует enum-значения в строки и убирает явные null для NOT NULL-полей."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, enum.Enum):
            value = value.value
        if value is None and key in drop_nulls:
            continue
        result[key] = value
    return result


def _commit(db: Session, conflict_message: str) -> None:
    """Коммит с переводом нарушения уникальности в понятную ошибку 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("integrity_error", extra={"event": "integrity_error", "error": str(exc.orig)})
        raise ApiError(status.HTTP_409_CONFLICT, "CONFLICT", conflict_message) from exc


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задачу",
    responses={
        409: {"model": ErrorResponse, "description": "Задача с таким названием уже существует"},
        422: {"model": ErrorResponse, "description": "Некорректные данные"},
    },
)
def create_task(payload: TaskCreate, response: Response, db: Session = Depends(get_db)) -> Task:
    task = Task(**_normalise(payload.model_dump()))
    db.add(task)
    _commit(db, "Задача с таким названием уже существует")
    db.refresh(task)

    response.headers["Location"] = f"/api/v1/tasks/{task.id}"
    logger.info("task_created", extra={"event": "task_created", "task_id": task.id})
    return task


@router.get(
    "",
    response_model=TaskList,
    summary="Список задач с фильтрацией и постраничной выдачей",
)
def list_tasks(
    db: Session = Depends(get_db),
    task_status: Annotated[TaskStatus | None, Query(alias="status", description="Фильтр по статусу")] = None,
    priority: Annotated[TaskPriority | None, Query(description="Фильтр по приоритету")] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=64, description="Поиск по названию")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 20,
    offset: Annotated[int, Query(ge=0, le=1_000_000, description="Смещение")] = 0,
) -> TaskList:
    stmt = select(Task)
    if task_status is not None:
        stmt = stmt.where(Task.status == task_status.value)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority.value)
    if search:
        stmt = stmt.where(Task.title.ilike(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).offset(offset)))
    return TaskList(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/stats",
    response_model=TaskStats,
    summary="Агрегированная статистика по задачам",
    description="Считается на стороне PostgreSQL (GROUP BY по статусу и приоритету).",
)
def tasks_stats(db: Session = Depends(get_db)) -> TaskStats:
    by_status = {item.value: 0 for item in TaskStatus}
    by_priority = {item.value: 0 for item in TaskPriority}

    for value, count in db.execute(select(Task.status, func.count()).group_by(Task.status)).all():
        by_status[value] = count
    for value, count in db.execute(select(Task.priority, func.count()).group_by(Task.priority)).all():
        by_priority[value] = count

    total = db.scalar(select(func.count()).select_from(Task)) or 0
    overdue = (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.due_date.is_not(None), Task.due_date < func.current_date(), Task.status != "done")
        )
        or 0
    )
    return TaskStats(total=total, by_status=by_status, by_priority=by_priority, overdue=overdue)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Получить задачу по идентификатору",
    responses={404: {"model": ErrorResponse, "description": "Задача не найдена"}},
)
def get_task(task_id: TaskId, db: Session = Depends(get_db)) -> Task:
    return _get_task_or_404(db, task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Частично обновить задачу",
    responses={
        404: {"model": ErrorResponse, "description": "Задача не найдена"},
        409: {"model": ErrorResponse, "description": "Конфликт названий"},
        422: {"model": ErrorResponse, "description": "Некорректные данные"},
    },
)
def update_task(task_id: TaskId, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = _get_task_or_404(db, task_id)
    changes = _normalise(payload.model_dump(exclude_unset=True), drop_nulls=("title", "status", "priority"))
    if not changes:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Нет полей для обновления: передайте хотя бы одно изменяемое поле",
            [{"field": "body", "message": "Все переданные поля содержат null"}],
        )

    for field_name, value in changes.items():
        setattr(task, field_name, value)

    _commit(db, "Задача с таким названием уже существует")
    db.refresh(task)

    logger.info(
        "task_updated",
        extra={"event": "task_updated", "task_id": task.id, "fields": sorted(changes)},
    )
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Удалить задачу",
    responses={
        204: {"description": "Задача удалена"},
        404: {"model": ErrorResponse, "description": "Задача не найдена"},
    },
)
def delete_task(task_id: TaskId, db: Session = Depends(get_db)) -> Response:
    task = _get_task_or_404(db, task_id)
    db.delete(task)
    db.commit()
    logger.info("task_deleted", extra={"event": "task_deleted", "task_id": task_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
