from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.advisor.router import router
from app.database import get_db
from app.identity.router import get_current_user


async def test_attention_ranks_open_sources_without_requiring_ai(monkeypatch):
    from app.advisor import decision_support as service

    owner = uuid4()
    date_today = date(2026, 11, 21)
    closed = SimpleNamespace(
        type="expense",
        due_date=date_today,
        status="matched_actual",
        source_key="already-paid",
        name="Already paid",
    )
    overdue = SimpleNamespace(
        type="expense",
        due_date=date(2026, 11, 20),
        status="overdue",
        source_key="late",
        name="Late payment",
    )
    upcoming = SimpleNamespace(
        type="expense",
        due_date=date(2026, 11, 22),
        status="due",
        source_key="tomorrow",
        name="Tomorrow",
    )
    doc = SimpleNamespace(id=uuid4(), original_name="Invoice")
    task = SimpleNamespace(
        id=uuid4(),
        title="Follow up",
        due_date=date(2026, 11, 19),
        project_id=None,
    )
    for name, result in [
        (
            "get_cashflow_forecast",
            SimpleNamespace(suggestions=[closed, upcoming, overdue, overdue]),
        ),
        ("get_documents", [doc]),
        ("get_overdue_tasks", [task]),
    ]:
        monkeypatch.setattr(service, name, AsyncMock(return_value=result))
    result = await service.get_attention(AsyncMock(), owner, today=date_today)
    assert [(row.kind, row.title) for row in result.items] == [
        ("payment", "Late payment"),
        ("document", "Invoice"),
        ("task", "Follow up"),
    ]
    assert [row.href for row in result.items] == [
        "/finances/cashflow",
        "/documents?worklist=review",
        "/today",
    ]


async def test_attention_requires_user(monkeypatch):
    from app.identity import router as identity

    monkeypatch.setattr(identity, "log_security_event", AsyncMock())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/decisions/attention")).status_code == 401


async def test_attention_empty_result_is_success(monkeypatch):
    from app.advisor import decision_support as service

    owner = uuid4()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=owner)
    for name, result in [
        ("get_cashflow_forecast", SimpleNamespace(suggestions=[])),
        ("get_documents", []),
        ("get_overdue_tasks", []),
    ]:
        monkeypatch.setattr(service, name, AsyncMock(return_value=result))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/decisions/attention")
        assert response.status_code == 200
        assert response.json()["items"] == []


@pytest.mark.integration
async def test_overdue_task_source_filters_before_limit_and_is_owner_scoped(db_session):
    from app.work.models import Task
    from app.work.service import get_overdue_tasks

    owner, stranger = uuid4(), uuid4()
    before = date(2026, 11, 21)
    due = date(2026, 11, 20)
    db_session.add_all(
        [
            Task(user_id=owner, title="Owned overdue", due_date=due, status="todo"),
            Task(user_id=owner, title="Closed", due_date=due, status="done", priority="urgent"),
            Task(user_id=owner, title="Today", due_date=before, status="todo", priority="urgent"),
            Task(user_id=stranger, title="Foreign overdue", due_date=due, status="todo"),
        ]
    )
    await db_session.flush()
    assert [
        task.title for task in await get_overdue_tasks(db_session, owner, before=before, limit=1)
    ] == [
        "Owned overdue",
    ]


@pytest.mark.integration
async def test_attention_uses_only_owned_documents_in_review_worklist(db_session, monkeypatch):
    from app.advisor import decision_support
    from app.documents.models import Document, DocumentText

    owner, stranger = uuid4(), uuid4()
    for user_id, name, archived_at, status in (
        (owner, "Needs review", None, "done"),
        (owner, "Archived", datetime(2026, 11, 20, tzinfo=UTC), "done"),
        (owner, "Failed", None, "error"),
        (stranger, "Foreign", None, "done"),
    ):
        db_session.add(
            Document(
                user_id=user_id,
                filename=name,
                original_name=name,
                mime_type="application/pdf",
                sha256_hash="0" * 64,
                size_bytes=1,
                storage_path="synthetic",
                archived_at=archived_at,
                status=status,
                text=DocumentText(extracted_text="synthetic"),
            )
        )
    await db_session.flush()
    monkeypatch.setattr(
        decision_support,
        "get_cashflow_forecast",
        AsyncMock(return_value=SimpleNamespace(suggestions=[])),
    )
    result = await decision_support.get_attention(db_session, owner, today=date(2026, 11, 21))
    assert [item.title for item in result.items] == ["Needs review"]


async def test_explanation_receives_no_user_titles_ids_or_links(monkeypatch):
    from app.advisor import router as routes
    from app.advisor.decision_schemas import AttentionItem, AttentionResult, DecisionExplanation

    owner = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    fetch = AsyncMock(
        return_value=AttentionResult(
            as_of=date(2026, 11, 21),
            items=[
                AttentionItem(
                    kind="document",
                    source_id="private-id",
                    title="private-title",
                    reason="Dokument czeka na przegląd.",
                    href="/documents?worklist=review",
                )
            ],
        )
    )
    capture = AsyncMock(return_value=DecisionExplanation(status="unavailable"))
    monkeypatch.setattr(routes, "get_attention", fetch)
    monkeypatch.setattr(routes, "explain_facts", capture)
    result = await routes.explain_attention_endpoint(owner, None, db)
    assert result.status == "unavailable"
    capture.assert_awaited_once_with(
        db,
        owner.id,
        {
            "topic": "priorytety",
            "items": [{"kind": "document", "reason": "Dokument czeka na przegląd."}],
        },
    )


async def test_explanation_applies_latest_saved_instructions_with_protected_rules(monkeypatch):
    from app.advisor import decision_explanation as service
    from app.advisor.ai_settings import AdvisorCredentials

    owner = uuid4()
    db = AsyncMock()
    history = AsyncMock(return_value=[SimpleNamespace(instructions="Używaj krótkich zdań.")])
    monkeypatch.setattr(service, "get_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service, "resolve_credentials", lambda *_: AdvisorCredentials("test", "synthetic")
    )
    monkeypatch.setattr(service, "prompt_history", history, raising=False)
    create = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            usage=None,
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(type="output_text", text='{"text":"Sprawdź termin."}')
                    ],
                )
            ],
        )
    )
    client = MagicMock()
    client.__aenter__.return_value = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(service, "create_openai_client", MagicMock(return_value=client))
    monkeypatch.setattr(service, "record_usage", AsyncMock())
    result = await service.explain_facts(db, owner, {"test": True})
    assert result.status == "ok" and result.text == "Sprawdź termin."
    history.assert_awaited_once_with(db, owner, limit=1)
    request = create.await_args.kwargs
    protected = request["input"][0]["content"]
    assert "nie gwarantuj płynności" in protected
    assert "Używaj krótkich zdań." in protected
    assert request["store"] is False and "tools" not in request
