"""Unified tool registry for Advisor. Each tool has an OpenAI function schema + executor."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# Type for async executor functions: takes db + user_id + kwargs, returns serializable dict
ToolExecutor = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


def _local_now() -> datetime:
    """Return a naive wall-clock time for legacy local calendar inputs."""
    return datetime.now(UTC).astimezone().replace(tzinfo=None)


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        executor: ToolExecutor,
        autonomy_level: int = 0,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.executor = executor
        self.autonomy_level = autonomy_level

    @property
    def openai_schema(self) -> dict[str, Any]:
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


async def _execute_get_accounts(db: AsyncSession, user_id: str, **kwargs: Any) -> dict[str, Any]:
    import uuid as _uuid

    from app.finance.service import get_accounts

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


async def _execute_get_financial_summary(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    import uuid as _uuid

    from app.finance.service import get_financial_summary

    summary = await get_financial_summary(db, _uuid.UUID(user_id))
    return {
        "accounts": summary.accounts,
        "income_total_pln": summary.income_total_pln,
        "expense_total_pln": summary.expense_total_pln,
        "net_total_pln": summary.net_total_pln,
        "month": summary.month,
        "year": summary.year,
    }


async def _execute_get_transactions(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    import uuid as _uuid

    from app.finance.service import get_transactions

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


async def _execute_get_today_schedule(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    import uuid as _uuid

    from app.work.service import get_today_schedule

    schedule: dict[str, Any] = await get_today_schedule(db, _uuid.UUID(user_id))
    return {
        "time_blocks": [
            {
                "id": str(b.id),
                "title": b.title,
                "start_time": b.start_time.isoformat() if b.start_time else None,
                "end_time": b.end_time.isoformat() if b.end_time else None,
                "block_type": b.block_type,
            }
            for b in schedule["time_blocks"]
        ],
        "tasks_due": [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "project_name": getattr(t, "project_name", None),
            }
            for t in schedule["tasks_due"]
        ],
    }


async def _execute_get_tasks(db: AsyncSession, user_id: str, **kwargs: Any) -> dict[str, Any]:
    import uuid as _uuid

    from app.work.service import get_tasks

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


async def _execute_get_projects(db: AsyncSession, user_id: str, **kwargs: Any) -> dict[str, Any]:
    import uuid as _uuid

    from app.work.service import get_projects

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


async def _execute_create_task(db: AsyncSession, user_id: str, **kwargs: Any) -> dict[str, Any]:
    import uuid as _uuid
    from datetime import date

    from app.work.schemas import TaskCreate
    from app.work.service import create_task

    title = kwargs.get("title", "Nowe zadanie")
    priority = kwargs.get("priority", "medium")
    due_date_str = kwargs.get("due_date")
    due_date = date.fromisoformat(due_date_str) if due_date_str else None
    project_id = _uuid.UUID(kwargs["project_id"]) if kwargs.get("project_id") else None

    data = TaskCreate(
        title=title,
        priority=priority,
        due_date=due_date,
        project_id=project_id,
        source="advisor",
    )
    task = await create_task(db, _uuid.UUID(user_id), data)
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
    }


async def _execute_create_time_block(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    import uuid as _uuid

    from app.work.schemas import TimeBlockCreate
    from app.work.service import create_time_block

    title = kwargs.get("title", "Nowy blok")
    start_str = kwargs.get("start_time")
    end_str = kwargs.get("end_time")
    block_type = kwargs.get("block_type", "shallow")

    start_time = datetime.fromisoformat(start_str) if start_str else _local_now()
    end_time = datetime.fromisoformat(end_str) if end_str else _local_now()

    data = TimeBlockCreate(
        title=title,
        start_time=start_time,
        end_time=end_time,
        block_type=block_type,
    )
    block = await create_time_block(db, _uuid.UUID(user_id), data)
    return {
        "id": str(block.id),
        "title": block.title,
        "start_time": str(block.start_time),
        "end_time": str(block.end_time),
    }


async def _execute_create_transaction(
    db: AsyncSession, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    import uuid as _uuid

    from app.finance.schemas import PostingCreate, TransactionCreate
    from app.finance.service import create_transaction, get_accounts, get_categories

    uid = _uuid.UUID(user_id)
    txn_type = kwargs.get("type", "expense")
    amount = kwargs.get("amount", 0)
    currency = str(kwargs.get("currency", "PLN")).upper()
    description = kwargs.get("description", "Nowa transakcja")
    account_name = kwargs.get("account_name")
    category_name = kwargs.get("category_name", "")

    if type(amount) is not int or amount <= 0:
        return {"error": "Amount must be a positive integer"}

    if currency != "PLN":
        return {"error": f"Advisor transactions in {currency} require a verified FX rate"}

    accounts = await get_accounts(db, uid)
    if account_name:
        matching_accounts = [a for a in accounts if a.name.lower() == account_name.lower()]
        if not matching_accounts:
            return {"error": f"Account '{account_name}' not found"}
        if len(matching_accounts) > 1:
            return {"error": f"Account '{account_name}' is ambiguous"}
        selected_account = matching_accounts[0]
    elif not accounts:
        return {"error": "No accounts found; account_name is required"}
    elif len(accounts) > 1:
        return {"error": "account_name is required when multiple accounts exist"}
    else:
        return {"error": "account_name is required"}

    account_currency = str(selected_account.currency).upper()
    if currency != account_currency:
        return {"error": f"Currency {currency} does not match account currency {account_currency}"}
    account_id = selected_account.id

    categories = await get_categories(db, uid)
    category_id = None
    for c in categories:
        if c.type == txn_type and (c.name.lower() == category_name.lower() or not category_name):
            category_id = c.id
            break

    if not category_id and categories:
        matching = [c for c in categories if c.type == txn_type]
        if matching:
            category_id = matching[0].id

    if category_id is None:
        return {"error": f"No {txn_type} category found"}

    try:
        txn = await create_transaction(
            db,
            uid,
            TransactionCreate(
                description=f"[AI] {description}",
                type=txn_type,
                source="advisor",
                postings=[
                    PostingCreate(
                        account_id=account_id,
                        source_amount=amount,
                        source_currency=currency,
                        base_amount_pln=amount,
                        fx_rate=1.0,
                        fx_rate_source="manual",
                        direction="debit" if txn_type == "expense" else "credit",
                    ),
                    PostingCreate(
                        account_id=None,
                        category_id=category_id,
                        source_amount=amount,
                        source_currency=currency,
                        base_amount_pln=amount,
                        fx_rate=1.0,
                        fx_rate_source="manual",
                        direction="credit" if txn_type == "expense" else "debit",
                    ),
                ],
            ),
        )
        return {
            "id": str(txn.id),
            "type": txn.type,
            "description": txn.description,
            "date": str(txn.date),
        }
    except (SQLAlchemyError, ValidationError, ValueError, KeyError, TypeError, RuntimeError) as e:
        return {"error": str(e)}


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
                "type": {
                    "type": "string",
                    "enum": ["income", "expense", "transfer"],
                    "description": "Filtruj transakcje po typie",
                },
                "limit": {
                    "type": "integer",
                    "description": "Liczba transakcji do zwrócenia (domyślnie 20)",
                },
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
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done", "cancelled"],
                    "description": "Filtruj zadania po statusie",
                },
                "project_id": {
                    "type": "string",
                    "description": "UUID projektu do filtrowania zadań",
                },
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
    Tool(
        name="create_task",
        description="Tworzy nowe zadanie. Wymaga potwierdzenia użytkownika.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tytuł zadania"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "urgent"],
                    "description": "Priorytet",
                },
                "due_date": {"type": "string", "description": "Termin w formacie YYYY-MM-DD"},
                "project_id": {"type": "string", "description": "UUID projektu (opcjonalnie)"},
            },
            "required": ["title"],
        },
        executor=_execute_create_task,
        autonomy_level=2,
    ),
    Tool(
        name="create_time_block",
        description="Tworzy nowy blok czasu w kalendarzu. Wymaga potwierdzenia użytkownika.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Tytuł bloku"},
                "start_time": {"type": "string", "description": "Czas startu ISO format"},
                "end_time": {"type": "string", "description": "Czas końca ISO format"},
                "block_type": {
                    "type": "string",
                    "enum": ["deep_work", "shallow", "meeting", "break"],
                    "description": "Typ bloku",
                },
            },
            "required": ["title", "start_time", "end_time"],
        },
        executor=_execute_create_time_block,
        autonomy_level=2,
    ),
    Tool(
        name="create_transaction",
        description="Tworzy nową transakcję finansową (wydatek lub przychód). Wymaga potwierdzenia użytkownika.",
        parameters={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["expense", "income"],
                    "description": "Typ transakcji",
                },
                "amount": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Kwota w groszach/centach (np. 50 PLN = 5000)",
                },
                "currency": {
                    "type": "string",
                    "enum": ["PLN", "EUR", "USD"],
                    "description": "Waluta",
                },
                "description": {"type": "string", "description": "Opis transakcji"},
                "account_name": {"type": "string", "description": "Nazwa konta (np. ING, Gotowka)"},
                "category_name": {
                    "type": "string",
                    "description": "Nazwa kategorii (np. Jedzenie, Transport)",
                },
            },
            "required": ["type", "amount", "description"],
        },
        executor=_execute_create_transaction,
        autonomy_level=2,
    ),
]


def get_tool_by_name(name: str) -> Tool | None:
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None


def get_openai_tools() -> list[dict[str, Any]]:
    return [tool.openai_schema for tool in TOOLS]
