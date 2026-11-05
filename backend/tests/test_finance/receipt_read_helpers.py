"""Synthetic owner/source fixtures. No provider, private file or production policy."""

import uuid
from dataclasses import dataclass

from app.documents.models import Document
from app.finance.models import FinancialDocumentSource
from tests.test_documents.test_receipt_read_policy import config_settings
from tests.test_finance.receipt_helpers import ROOT, ready


@dataclass(frozen=True)
class ReadFixture:
    owner: uuid.UUID
    bill_id: uuid.UUID
    document_id: uuid.UUID
    transaction_id: uuid.UUID
    food_id: uuid.UUID
    home_id: uuid.UUID


async def read_ready(db, monkeypatch, *, enable=True):
    from app.config import settings
    from app.documents.receipt_read_config import get_receipt_read_config
    from app.documents.receipt_read_policy import get_receipt_read_policy, set_receipt_read_policy

    s = config_settings(DOCUMENT_RECEIPT_ITEMS_ENABLED=enable)
    for name in type(s).model_fields:
        if name.startswith("DOCUMENT_RECEIPT_ITEMS_"):
            monkeypatch.setattr(settings, name, getattr(s, name))
    owner, bill, txn, _, _, food, home = await ready(db)
    doc = Document(
        user_id=owner,
        filename="synthetic.png",
        original_name="Paragon testowy.png",
        mime_type="image/png",
        size_bytes=10,
        storage_path=f"synthetic-{uuid.uuid4()}.png",
        sha256_hash="a" * 64,
        status="done",
    )
    db.add(doc)
    await db.flush()
    db.add(
        FinancialDocumentSource(user_id=owner, financial_document_id=bill.id, document_id=doc.id)
    )
    if enable:
        await set_receipt_read_policy(
            db,
            enabled=True,
            expected_epoch=(await get_receipt_read_policy(db)).epoch,
            config=get_receipt_read_config(settings),
            performed_by="synthetic-test",
        )
    await db.commit()
    return ReadFixture(owner, bill.id, doc.id, txn.id, food.id, home.id)


def read_path(r, suffix):
    return f"{ROOT}/bills/{r.bill_id}/items/{suffix}"


async def export(client, r, reread=None):
    response = await client.post(
        read_path(r, "read-export-preview"),
        json={"document_id": str(r.document_id), "reread_of_job_id": reread},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def start(client, r, *, preview=None, key=None, reread=None):
    p = preview or await export(client, r, reread)
    return await client.post(
        read_path(r, "read-start"),
        json={
            "document_id": p["document_id"],
            "reread_of_job_id": p["reread_of_job_id"],
            "expected_export_snapshot": p["export_snapshot"],
            "confirmed": True,
        },
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
    )
