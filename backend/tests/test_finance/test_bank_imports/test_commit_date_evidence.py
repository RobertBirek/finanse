from datetime import date

import pytest

from app.documents import service as documents
from app.finance.imports.commit import commit_import
from app.finance.imports.decisions import save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.preview import prepare_preview
from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest
from app.finance.schemas import PostingCreate, TransactionCreate, TransactionDatesUpdate
from app.finance.transaction_dates import set_transaction_dates
from app.finance.transactions import create_transaction
from tests.test_finance.test_bank_imports.review_fixtures import review_case
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration


async def test_link_date_evidence_change_after_preview_invalidates_confirmation(
    db_session, owner, tmp_path, monkeypatch
):
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(account_reference=None, rows=[statement_row()]),
    )
    old = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            booking_date="2026-01-03",
            purchase_date="2026-01-02",
            description="Manual before bank review",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=case.account.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit",
                ),
            ],
        ),
    )
    decision = case.decision.model_copy(
        update={"action": "link", "existing_transaction_id": old.id}
    )
    batch = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[decision]),
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        batch.id,
        PreviewRequest(
            expected_version=batch.version,
            group_ids=[decision.group_id],
            acknowledgements=[f"opening_gap:{case.source_id}"],
        ),
    )
    await set_transaction_dates(
        db_session,
        owner.id,
        old.id,
        TransactionDatesUpdate(
            purchase_date=date(2026, 1, 1),
            booking_date=date(2026, 1, 3),
            expected_version=1,
            expected_updated_at=old.updated_at,
        ),
    )
    with pytest.raises(ImportError) as error:
        await commit_import(
            db_session,
            owner.id,
            batch.id,
            CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
            "old-date-changed",
        )
    assert error.value.code == "preview_stale"
