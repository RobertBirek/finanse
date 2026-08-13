import uuid

WORK_TOOLS = [
    {
        "name": "get_projects",
        "description": "List all user projects with status",
        "autonomy_level": 0,
    },
    {
        "name": "get_today_schedule",
        "description": "Get today's time blocks and tasks due",
        "autonomy_level": 0,
    },
    {
        "name": "get_tasks",
        "description": "List tasks, optionally filtered by project or status",
        "autonomy_level": 0,
    },
    {
        "name": "create_task",
        "description": "Create a new task",
        "autonomy_level": 2,
        "requires_authorization": True,
    },
    {
        "name": "create_time_block",
        "description": "Schedule a new time block",
        "autonomy_level": 2,
        "requires_authorization": True,
    },
]


def get_work_tool_schemas() -> list[dict]:
    return WORK_TOOLS


async def execute_get_projects(db, user_id: str) -> dict:
    from app.work.service import get_projects

    projects = await get_projects(db, uuid.UUID(user_id))
    return {
        "projects": [
            {
                "id": str(p.id),
                "name": p.name,
                "status": p.status,
                "deadline": str(p.deadline) if p.deadline else None,
            }
            for p in projects
        ]
    }


async def execute_get_today_schedule(db, user_id: str) -> dict:
    from app.work.service import get_today_schedule

    schedule = await get_today_schedule(db, uuid.UUID(user_id))
    return {
        "date": schedule["date"],
        "time_blocks": [
            {
                "id": str(b.id),
                "title": b.title,
                "start_time": b.start_time.isoformat(),
                "end_time": b.end_time.isoformat(),
                "block_type": b.block_type,
            }
            for b in schedule["time_blocks"]
        ],
        "tasks_due": [
            {"id": str(t.id), "title": t.title, "status": t.status, "priority": t.priority}
            for t in schedule["tasks_due"]
        ],
    }


async def execute_get_tasks(
    db, user_id: str, project_id: str | None = None, status: str | None = None
) -> dict:
    import uuid as uuid_mod

    from app.work.service import get_tasks

    tasks = await get_tasks(
        db,
        uuid_mod.UUID(user_id),
        project_id=uuid_mod.UUID(project_id) if project_id else None,
        status=status,
    )
    return {
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "project_id": str(t.project_id) if t.project_id else None,
            }
            for t in tasks
        ]
    }
