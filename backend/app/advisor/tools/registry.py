"""Unified tool registry for Advisor. Each tool has an OpenAI function schema + executor."""
from typing import Any, Callable, Coroutine

from sqlalchemy.ext.asyncio import AsyncSession

# Type for async executor functions: takes db + user_id + kwargs, returns serializable dict
ToolExecutor = Callable[[AsyncSession, str, ...], Coroutine[Any, Any, dict]]


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        executor: ToolExecutor,
        autonomy_level: int = 0,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor
        self.autonomy_level = autonomy_level

    @property
    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ============================================================
# Executor functions
# ============================================================

async def _execute_get_accounts(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_accounts
    import uuid as _uuid
    accounts = await get_accounts(db, _uuid.UUID(user_id))
    return {
        "accounts": [
            {
                "id": str(a.id),
                "name": a.name,
                "type": a.type,
                "currency": a.currency,
                "balance_pln": getattr(a, "_balance", 0),
            }
            for a in accounts
        ]
    }


async def _execute_get_financial_summary(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_financial_summary
    import uuid as _uuid
    summary = await get_financial_summary(db, _uuid.UUID(user_id))
    return {
        "accounts": summary.accounts,
        "income_total_pln": summary.income_total_pln,
        "expense_total_pln": summary.expense_total_pln,
        "net_total_pln": summary.net_total_pln,
        "month": summary.month,
        "year": summary.year,
    }


async def _execute_get_transactions(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.finance.service import get_transactions
    import uuid as _uuid
    txn_type = kwargs.get("type")
    limit = kwargs.get("limit", 20)
    txns = await get_transactions(db, _uuid.UUID(user_id), limit=limit, txn_type=txn_type)
    return {
        "transactions": [
            {
                "id": str(t.id),
                "date": str(t.date),
                "description": t.description,
                "type": t.type,
                "amount": sum(p.source_amount for p in t.postings if p.direction == "credit"),
            }
            for t in txns
        ]
    }


async def _execute_get_today_schedule(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_today_schedule
    import uuid as _uuid
    schedule = await get_today_schedule(db, _uuid.UUID(user_id))
    return {
        "time_blocks": [
            {
                "id": str(b.id),
                "title": b.title,
                "start_time": b.start_time.isoformat() if b.start_time else None,
                "end_time": b.end_time.isoformat() if b.end_time else None,
                "block_type": b.block_type,
            }
            for b in schedule.time_blocks
        ],
        "tasks_due": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "project_name": getattr(t, "project_name", None),
            }
            for t in schedule.tasks_due
        ],
    }


async def _execute_get_tasks(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_tasks
    import uuid as _uuid
    status = kwargs.get("status")
    project_id = kwargs.get("project_id")
    if project_id:
        import uuid as _uuid2
        project_id = _uuid2.UUID(project_id)
    tasks = await get_tasks(db, _uuid.UUID(user_id), status=status, project_id=project_id)
    return {
        "tasks": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "due_date": str(t.due_date) if t.due_date else None,
            }
            for t in tasks
        ]
    }


async def _execute_get_projects(db: AsyncSession, user_id: str, **kwargs) -> dict:
    from app.work.service import get_projects
    import uuid as _uuid
    projects = await get_projects(db, _uuid.UUID(user_id))
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


# ============================================================
# Registry
# ============================================================

TOOLS = [
    Tool(
        name="get_accounts",
        description="Pobiera listę wszystkich kont użytkownika wraz z aktualnymi saldami w PLN.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_accounts,
    ),
    Tool(
        name="get_financial_summary",
        description="Pobiera podsumowanie finansowe za bieżący miesiąc: salda kont, suma przychodów, suma wydatków, bilans netto.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_financial_summary,
    ),
    Tool(
        name="get_transactions",
        description="Pobiera ostatnie transakcje użytkownika. Można filtrować po typie (income/expense/transfer).",
        parameters={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["income", "expense", "transfer"], "description": "Filtruj transakcje po typie"},
                "limit": {"type": "integer", "description": "Liczba transakcji do zwrócenia (domyślnie 20)"},
            },
            "required": [],
        },
        executor=_execute_get_transactions,
    ),
    Tool(
        name="get_today_schedule",
        description="Pobiera dzisiejszy harmonogram: zaplanowane bloki czasu (time blocks) i zadania do wykonania.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_today_schedule,
    ),
    Tool(
        name="get_tasks",
        description="Pobiera listę zadań użytkownika. Można filtrować po statusie (todo/in_progress/done/cancelled) i ID projektu.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["todo", "in_progress", "done", "cancelled"], "description": "Filtruj zadania po statusie"},
                "project_id": {"type": "string", "description": "UUID projektu do filtrowania zadań"},
            },
            "required": [],
        },
        executor=_execute_get_tasks,
    ),
    Tool(
        name="get_projects",
        description="Pobiera listę wszystkich projektów użytkownika z ich statusami.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor=_execute_get_projects,
    ),
]


def get_tool_by_name(name: str) -> Tool | None:
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None


def get_openai_tools() -> list[dict]:
    return [tool.openai_schema for tool in TOOLS]
