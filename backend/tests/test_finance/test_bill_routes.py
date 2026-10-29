import uuid

import pytest

from app.documents.models import Document
from app.identity.models import User
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_prepare_route_is_explicit_and_replays(db_session) -> None:
    user = User(email=f"{uuid.uuid4()}@example.test", password_hash="x", display_name="Owner")
    db_session.add(user)
    await db_session.flush()
    document = Document(
        user_id=user.id,
        filename="route.pdf",
        original_name="route.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="test/route.pdf",
    )
    db_session.add(document)
    await db_session.flush()
    async with client_for(db_session, user.id) as client:
        created = await client.post(
            f"/api/finance/bills/prepare/{document.id}", headers={"Idempotency-Key": "prepare"}
        )
        replay = await client.post(
            f"/api/finance/bills/prepare/{document.id}", headers={"Idempotency-Key": "prepare"}
        )
    assert created.status_code == 201
    assert replay.json() == created.json()
