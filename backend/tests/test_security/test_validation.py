"""PATCH omission/null semantics and bounded legacy pagination regressions."""

import uuid
from datetime import date
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.finance.schemas import AccountCreate, AccountUpdate
from app.identity.router import get_current_user
from app.inbox.schemas import InboxItemCreate, InboxItemUpdate
from app.main import app

NULL_CASES = [
    (AccountUpdate, "/api/finance/accounts/", field)
    for field in ("name", "type", "is_active", "is_budget_account")
] + [
    (InboxItemUpdate, "/api/inbox/items/", field)
    for field in ("content", "is_processed")
]
LIST_CASES = [
    ("/api/finance/transactions", "app.finance.router", "get_transactions", 200, 50),
    ("/api/inbox/items", "app.inbox.router", "get_inbox_items", 500, 100),
    ("/api/work/tasks", "app.work.router", "get_tasks", 500, 100),
    ("/api/work/time-blocks", "app.work.router", "get_time_blocks", 500, 100),
]


@pytest.mark.parametrize("schema,path,field", NULL_CASES)
def test_required_patch_fields_reject_explicit_null(schema, path, field):
    with pytest.raises(ValidationError, match="cannot be null"):
        schema.model_validate({field: None})


@pytest.mark.parametrize("schema", [AccountUpdate, InboxItemUpdate])
def test_omitted_patch_fields_are_not_updates(schema):
    assert schema().model_dump(exclude_unset=True) == {}


def test_nullable_fields_and_false_values_remain_explicit_updates():
    assert AccountUpdate(closed_at=None, is_active=False).model_dump(exclude_unset=True) == {
        "closed_at": None, "is_active": False,
    }
    assert InboxItemUpdate(target_id=None, target_type=None, is_processed=False).model_dump(
        exclude_unset=True
    ) == {"target_id": None, "target_type": None, "is_processed": False}


@pytest.fixture
async def validation_client(monkeypatch):
    db = AsyncMock(spec=AsyncSession)

    async def override_db():
        yield db

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(app, "dependency_overrides", {
        get_db: override_db,
        get_current_user: lambda: SimpleNamespace(id=uuid.uuid4()),
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, db


@pytest.mark.parametrize("schema,path,field", NULL_CASES)
async def test_invalid_patch_returns_422_without_database_access(validation_client, schema, path, field):
    client, db = validation_client
    response = await client.patch(f"{path}{uuid.uuid4()}", json={field: None})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    db.execute.assert_not_awaited()
    db.flush.assert_not_awaited()


@pytest.mark.parametrize("path,module,name,maximum,default", LIST_CASES)
@pytest.mark.parametrize("limit", [-1, 0, "over_maximum", "not-an-integer"])
async def test_invalid_list_limits_return_422_before_query(
    validation_client, path, module, name, maximum, default, limit
):
    client, db = validation_client
    response = await client.get(path, params={"limit": maximum + 1 if limit == "over_maximum" else limit})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "limit"]
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("path,module,name,maximum,default", LIST_CASES)
async def test_negative_offsets_return_422_before_query(
    validation_client, path, module, name, maximum, default
):
    client, db = validation_client
    response = await client.get(path, params={"offset": -1})
    assert response.status_code == 422
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("path,module,name,maximum,default", LIST_CASES)
@pytest.mark.parametrize("boundary", ["minimum", "maximum", "default"])
async def test_valid_pagination_preserves_limits_and_zero_offset(
    validation_client, monkeypatch, path, module, name, maximum, default, boundary
):
    client, _db = validation_client
    read = AsyncMock(return_value=[])
    monkeypatch.setattr(import_module(module), name, read)
    limit = {"minimum": 1, "maximum": maximum, "default": default}[boundary]
    response = await client.get(path, params={} if boundary == "default" else {"limit": limit})
    assert response.status_code == 200
    assert response.json() == []
    assert read.await_args.kwargs["limit"] == limit
    assert read.await_args.kwargs["offset"] == 0


@pytest.mark.integration
async def test_account_patch_rejects_null_atomically_and_allows_clear(db_session, async_client, monkeypatch):
    from app.finance.service import create_account, get_account

    user_id = uuid.uuid4()
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=user_id))
    account = await create_account(db_session, user_id, AccountCreate(name="Original", type="checking"))
    account.closed_at = date(2026, 1, 1)
    await db_session.flush()
    response = await async_client.patch(
        f"/api/finance/accounts/{account.id}", json={"name": "Changed", "is_active": None}
    )
    assert response.status_code == 422
    await db_session.refresh(account)
    assert account.name == "Original" and account.is_active is True
    response = await async_client.patch(
        f"/api/finance/accounts/{account.id}", json={"is_active": False, "closed_at": None}
    )
    assert response.status_code == 200
    persisted = await get_account(db_session, user_id, account.id)
    assert persisted.name == "Original" and persisted.type == "checking"
    assert persisted.is_active is False and persisted.is_budget_account is True
    assert persisted.closed_at is None


@pytest.mark.integration
async def test_inbox_patch_rejects_null_atomically_and_allows_clear(db_session, async_client, monkeypatch):
    from app.inbox.service import create_inbox_item, get_inbox_item

    user_id = uuid.uuid4()
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=user_id))
    item = await create_inbox_item(db_session, user_id, InboxItemCreate(content="Original"))
    item.target_type, item.target_id, item.is_processed = "task", uuid.uuid4(), True
    await db_session.flush()
    response = await async_client.patch(
        f"/api/inbox/items/{item.id}", json={"content": "Changed", "is_processed": None}
    )
    assert response.status_code == 422
    await db_session.refresh(item)
    assert item.content == "Original" and item.is_processed is True
    response = await async_client.patch(
        f"/api/inbox/items/{item.id}",
        json={"is_processed": False, "target_id": None, "target_type": None},
    )
    assert response.status_code == 200
    persisted = await get_inbox_item(db_session, user_id, item.id)
    assert persisted.content == "Original" and persisted.is_processed is False
    assert persisted.target_id is None and persisted.target_type is None
