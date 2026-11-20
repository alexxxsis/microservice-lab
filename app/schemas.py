"""Pydantic-схемы: валидация входных данных и сериализация ответов."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    """Общие поля задачи.

    ``extra="forbid"`` — неизвестные поля в теле запроса считаются ошибкой
    (клиент сразу узнаёт, что отправил опечатку), вместо молчаливого игнорирования.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"title": "Подготовить отчёт", "priority": "high"}]},
    )

    title: str = Field(min_length=3, max_length=120, description="Краткое название задачи")
    description: str | None = Field(default=None, max_length=1000, description="Подробное описание")
    status: TaskStatus = Field(default=TaskStatus.todo, description="Статус задачи")
    priority: TaskPriority = Field(default=TaskPriority.medium, description="Приоритет задачи")
    due_date: date | None = Field(default=None, description="Срок выполнения (YYYY-MM-DD)")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Название задачи не может состоять только из пробелов")
        return value


class TaskCreate(TaskBase):
    """Тело запроса POST /api/v1/tasks."""


class TaskUpdate(BaseModel):
    """Тело запроса PATCH /api/v1/tasks/{id} — все поля необязательны."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "TaskUpdate":
        if not self.model_fields_set:
            raise ValueError("Нужно передать хотя бы одно изменяемое поле")
        return self


class TaskRead(BaseModel):
    """Задача в ответе API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    """Постраничный список задач."""

    items: list[TaskRead]
    total: int = Field(description="Всего задач по фильтру")
    limit: int
    offset: int


class TaskStats(BaseModel):
    """Агрегированная статистика по задачам."""

    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue: int = Field(description="Просроченные задачи (due_date < сегодня, статус не done)")


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str | None = None
    server_version: str | None = None


class ErrorItem(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Единый формат ошибки для всех эндпоинтов."""

    error: ErrorItem
    request_id: str | None = None
