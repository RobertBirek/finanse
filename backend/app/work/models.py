import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'on_hold', 'completed', 'cancelled')", name="ck_project_status"),
    )

    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    time_blocks: Mapped[list["TimeBlock"]] = relationship("TimeBlock", back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")

    __table_args__ = (
        CheckConstraint("status IN ('todo', 'in_progress', 'done', 'cancelled')", name="ck_task_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="ck_task_priority"),
    )

    project: Mapped["Project | None"] = relationship("Project", back_populates="tasks")
    time_blocks: Mapped[list["TimeBlock"]] = relationship("TimeBlock", back_populates="task")


class TimeBlock(Base):
    __tablename__ = "time_blocks"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    block_type: Mapped[str] = mapped_column(String(20), nullable=False, default="deep_work")
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    __table_args__ = (
        CheckConstraint("start_time < end_time", name="ck_timeblock_start_before_end"),
        CheckConstraint("block_type IN ('deep_work', 'shallow', 'meeting', 'break')", name="ck_timeblock_type"),
    )

    task: Mapped["Task | None"] = relationship("Task", back_populates="time_blocks")
    project: Mapped["Project | None"] = relationship("Project", back_populates="time_blocks")
