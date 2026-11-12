import pytest
from sqlalchemy import select

from app.finance import service
from app.finance.imports.commit import commit_import
from app.finance.imports.models import ImportEvidence
from app.finance.models import FinanceCommandReceipt, Posting
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_annotations import context, edit, save
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_categorization import columns
from tests.test_finance.test_imported_categorization import rows

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_bank_annotation_does_not_change_evidence_receipts_or_replay(
    db_session, tmp_path, monkeypatch
):
    db = db_session
    owner = await create_owner(db)
    case, request = await confirmed_import(db, owner, tmp_path, monkeypatch)
    committed = await commit_import(db, owner, case.batch_id, request, "bank-original")
    txn = await service.get_transaction(db, owner, committed.transaction_ids[0])
    await db.commit()
    before_txn = columns(txn)
    before_posts = await rows(db, Posting)
    before_evidence = await rows(db, ImportEvidence)
    original_receipt = await db.scalar(
        select(FinanceCommandReceipt).where(FinanceCommandReceipt.action == "bank_import.commit")
    )
    before_receipt = columns(original_receipt)
    async with client_for(db, owner) as client:
        result = await save(
            client,
            txn,
            edit(
                await context(client, txn),
                display_description="My bank expense",
                note="Only narrative",
                tags=["Import"],
            ),
        )
        assert result.status_code == 200, result.text
    again = await commit_import(db, owner, case.batch_id, request, "bank-original")
    assert again == committed
    assert await rows(db, Posting) == before_posts
    assert await rows(db, ImportEvidence) == before_evidence
    await db.refresh(txn)
    await db.refresh(original_receipt)
    assert columns(txn) == before_txn
    assert columns(original_receipt) == before_receipt
