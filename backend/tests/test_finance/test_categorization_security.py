import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import settings
from app.database import get_db
from app.finance.models import FinanceCommandReceipt, TransactionCategorizationState
from app.identity.service import create_session
from app.main import app
from tests.test_finance.test_categorization import path, setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_categorization_requires_session_and_production_csrf(db_session, monkeypatch):
    owner, txn, _, food, _ = await setup(db_session)
    token, csrf, _ = await create_session(db_session, owner)
    await db_session.commit()

    async def database():
        yield db_session

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = database
    body = {
        "expected_version": 0,
        "expected_preview_snapshot": "0" * 64,
        "parts": [{"category_id": str(food.id), "amount_minor": 10000}],
        "confirmed": True,
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(path(txn))).status_code == 401
            client.cookies.set("advisor_session", token)
            monkeypatch.setattr(settings, "ENVIRONMENT", "production")
            headers = {"Idempotency-Key": uuid.uuid4().hex, "Origin": settings.trusted_origins[0]}
            assert (
                await client.post(path(txn) + "/apply", json=body, headers=headers)
            ).status_code == 403
            client.cookies.set("advisor_csrf", csrf)
            headers["X-CSRF-Token"] = csrf
            # A valid proof reaches the stale-preview guard, not a CSRF/auth error.
            assert (
                await client.post(path(txn) + "/apply", json=body, headers=headers)
            ).status_code == 409
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(TransactionCategorizationState))
        == 0
    )
