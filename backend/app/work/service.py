import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.work.models import Project, Task, TimeBlock
from app.work.schemas import (
    ProjectCreate,
    ProjectUpdate,
    TaskCreate,
    TaskUpdate,
    TimeBlockCreate,
    TimeBlockUpdate,
)


async def create_project(db: AsyncSession, user_id: uuid.UUID, data: ProjectCreate) -> Project:
    project = Project(user_id=user_id, **data.model_dump())
    db.add(project)
    await db.flush()
    return project


async def get_projects(db: AsyncSession, user_id: uuid.UUID) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.name)
    )
    return list(result.scalars().all())


async def get_project(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_project(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, data: ProjectUpdate
) -> Project | None:
    project = await get_project(db, user_id, project_id)
    if project is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    await db.flush()
    return project


async def delete_project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    project = await get_project(db, user_id, project_id)
    if project is None:
        return False
    await db.delete(project)
    await db.flush()
    return True


async def create_task(db: AsyncSession, user_id: uuid.UUID, data: TaskCreate) -> Task:
    task = Task(user_id=user_id, **data.model_dump())
    db.add(task)
    await db.flush()
    return task


async def get_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user_id)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        statuses = [s.strip() for s in status.split(",")]
        if len(statuses) == 1:
            stmt = stmt.where(Task.status == statuses[0])
        else:
            from sqlalchemy import or_

            stmt = stmt.where(or_(*[Task.status == s for s in statuses]))
    stmt = (
        stmt.order_by(Task.priority.desc(), Task.due_date.asc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    return result.scalar_one_or_none()


async def update_task(
    db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, data: TaskUpdate
) -> Task | None:
    task = await get_task(db, user_id, task_id)
    if task is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] == "done" and task.status != "done":
        task.completed_at = datetime.now(timezone.utc)
    for key, value in update_data.items():
        if key == "completed_at":
            continue
        setattr(task, key, value)
    await db.flush()
    return task


async def delete_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> bool:
    task = await get_task(db, user_id, task_id)
    if task is None:
        return False
    await db.delete(task)
    await db.flush()
    return True


async def create_time_block(
    db: AsyncSession, user_id: uuid.UUID, data: TimeBlockCreate
) -> TimeBlock:
    if data.start_time >= data.end_time:
        raise ValueError("start_time must be before end_time")
    block = TimeBlock(user_id=user_id, **data.model_dump())
    db.add(block)
    await db.flush()
    return block


async def get_time_blocks(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TimeBlock]:
    stmt = select(TimeBlock).where(TimeBlock.user_id == user_id)
    if start_time:
        stmt = stmt.where(TimeBlock.end_time >= start_time)
    if end_time:
        stmt = stmt.where(TimeBlock.start_time <= end_time)
    stmt = stmt.order_by(TimeBlock.start_time).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_time_block(
    db: AsyncSession, user_id: uuid.UUID, block_id: uuid.UUID
) -> TimeBlock | None:
    result = await db.execute(
        select(TimeBlock).where(TimeBlock.id == block_id, TimeBlock.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_time_block(
    db: AsyncSession, user_id: uuid.UUID, block_id: uuid.UUID, data: TimeBlockUpdate
) -> TimeBlock | None:
    block = await get_time_block(db, user_id, block_id)
    if block is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(block, key, value)
    if block.start_time >= block.end_time:
        raise ValueError("start_time must be before end_time")
    await db.flush()
    return block


async def delete_time_block(db: AsyncSession, user_id: uuid.UUID, block_id: uuid.UUID) -> bool:
    block = await get_time_block(db, user_id, block_id)
    if block is None:
        return False
    await db.delete(block)
    await db.flush()
    return True


async def get_today_schedule(db: AsyncSession, user_id: uuid.UUID) -> dict:
    today = date.today()
    start_of_day = datetime(today.year, today.month, today.day, 0, 0, 0, tzinfo=timezone.utc)
    end_of_day = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)

    stmt = (
        select(TimeBlock)
        .where(
            TimeBlock.user_id == user_id,
            TimeBlock.start_time >= start_of_day,
            TimeBlock.start_time <= end_of_day,
        )
        .order_by(TimeBlock.start_time)
    )
    result = await db.execute(stmt)
    blocks = list(result.scalars().all())

    tasks_today_result = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.due_date == today,
            Task.status.in_(["todo", "in_progress"]),
        )
        .order_by(Task.priority.desc())
    )
    tasks_today = list(tasks_today_result.scalars().all())

    return {
        "date": today.isoformat(),
        "time_blocks": blocks,
        "tasks_due": tasks_today,
    }
