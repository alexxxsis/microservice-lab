"""ORM-модели (SQLAlchemy 2.0) и перечисления предметной области."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TaskStatus(str, enum.Enum):
    """Статус задачи."""

    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriority(str, enum.Enum):
    """Приоритет задачи."""

    low = "low"
    medium = "medium"
    high = "high"


class Base(DeclarativeBase):
    pass


class Task(Base):
    """Задача в трекере."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="tasks_status_check"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="tasks_priority_check"),
        CheckConstraint("char_length(title) BETWEEN 3 AND 120", name="tasks_title_length_check"),
        Index("tasks_status_idx", "status"),
        Index("tasks_priority_idx", "priority"),
        {"comment": "Задачи трекера"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo", server_default="todo")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default="medium")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover - используется только в отладке
        return f"<Task id={self.id} title={self.title!r} status={self.status}>"
