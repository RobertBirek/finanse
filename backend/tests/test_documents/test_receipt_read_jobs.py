import pytest
from sqlalchemy import select

from app.documents.receipt_read_models import ReceiptReadJob
from tests.test_finance.receipt_read_helpers import read_path, read_ready, start
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_allocation_version_noise_does_not_require_new_export_consent(
    db_session, monkeypatch
):
    from sqlalchemy import update

    from app.finance.models import FinancialDocument
    from tests.test_finance.receipt_read_helpers import export

    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        p = await export(client, r)
        await db_session.execute(
            update(FinancialDocument).where(FinancialDocument.id == r.bill_id).values(version=2)
        )
        await db_session.commit()
        response = await start(client, r, preview=p)
        assert response.status_code == 200, response.text


async def test_cancel_after_marker_conflicts_and_preserves_dispatch(db_session, monkeypatch):
    import uuid
    from datetime import UTC, datetime

    from sqlalchemy import update

    r = await read_ready(db_session, monkeypatch)
    async with client_for(db_session, r.owner) as client:
        response = await start(client, r)
        assert response.status_code == 200, response.text
        job_id = uuid.UUID(response.json()["id"])
        token = uuid.uuid4()
        await db_session.execute(
            update(ReceiptReadJob)
            .where(ReceiptReadJob.id == job_id)
            .values(
                state="dispatched", dispatch_token=token, dispatched_at=datetime.now(UTC), version=2
            )
        )
        await db_session.commit()
        response = await client.post(
            read_path(r, f"reads/{job_id}/cancel"),
            json={"expected_version": 2},
            headers={"Idempotency-Key": "late-cancel"},
        )
        assert response.status_code == 409, response.text
    assert (
        await db_session.scalar(
            select(ReceiptReadJob.dispatch_token).where(ReceiptReadJob.id == job_id)
        )
        == token
    )
