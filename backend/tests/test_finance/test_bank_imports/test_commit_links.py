import uuid

import pytest
from sqlalchemy import select

from app.documents import service as documents
from app.finance.imports.commit import commit_import
from app.finance.imports.decisions import save_decisions
from app.finance.imports.models import ImportEvidence
from app.finance.imports.preview import prepare_preview
from app.finance.imports.schemas import (
    CommitRequest,
    DecisionUpdate,
    ImportDecisionInput,
    PreviewRequest,
)
from app.finance.models import ActualImportMapping, FinancialTransaction, Posting
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from tests.test_finance.test_bank_imports.factories import ledger_snapshot
from tests.test_finance.test_bank_imports.review_fixtures import additional_source, review_case
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration


async def test_link_unsplit_actual_preserves_ledger_and_existing_actual_mapping(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.nbp_rates import NbpRateProvider

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    payload = parsed_statement(account_reference=None, rows=[statement_row(amount=-120, fee=20)])
    case = await review_case(db_session, owner.id, tmp_path, payload)
    old = await create_transaction(
        db_session,
        owner.id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Old Actual",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=case.account.id,
                    source_amount=120,
                    base_amount_pln=120,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=case.category.id,
                    source_amount=120,
                    base_amount_pln=120,
                    direction="credit",
                ),
            ],
        ),
    )
    db_session.add(
        ActualImportMapping(
            user_id=owner.id,
            entity_type="transaction",
            entity_id=old.id,
            actual_id="old-actual-payment",
        )
    )
    await db_session.flush()
    decision = case.decision.model_copy(
        update={"action": "link", "existing_transaction_id": old.id, "category_id": None}
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
    before = await ledger_snapshot(db_session)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Commit must never fetch rates")

    monkeypatch.setattr(NbpRateProvider, "get_rate", forbidden)
    result = await commit_import(
        db_session,
        owner.id,
        batch.id,
        CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "link-old",
    )
    assert not result.transaction_ids and result.linked_row_ids == [case.rows[0].id]
    assert await ledger_snapshot(db_session) == before
    evidence = (await db_session.scalars(select(ImportEvidence))).one()
    assert evidence.component == "whole" and evidence.attributed_source_amount == -120


async def test_second_statement_can_evidence_the_other_leg_of_same_transfer(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.entities import create_account
    from app.finance.imports.service import create_batch
    from app.finance.schemas import AccountCreate

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(
            account_reference=None,
            opening=0,
            rows=[statement_row(amount=-100, bank_reference="outgoing-ref")],
        ),
    )
    other = await create_account(
        db_session, owner.id, AccountCreate(name="Other owned account", type="checking")
    )
    decision = case.decision.model_copy(
        update={"kind": "transfer", "other_account_id": other.id, "category_id": None}
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
        PreviewRequest(expected_version=batch.version, group_ids=[decision.group_id]),
    )
    first = await commit_import(
        db_session,
        owner.id,
        batch.id,
        CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "transfer",
    )
    second = await create_batch(db_session, owner.id, "statement")
    _source, rows = await additional_source(
        db_session,
        owner.id,
        second.id,
        tmp_path,
        parsed_statement(
            account_reference=None,
            opening=0,
            rows=[statement_row(amount=100, bank_reference="incoming-ref")],
        ),
    )
    linked = ImportDecisionInput(
        group_id=uuid.uuid4(),
        row_ids=[rows[0].id],
        action="link",
        kind="transfer",
        account_id=other.id,
        existing_transaction_id=first.transaction_ids[0],
    )
    second = await save_decisions(
        db_session, owner.id, second.id, DecisionUpdate(expected_version=1, decisions=[linked])
    )
    preview = await prepare_preview(
        db_session,
        owner.id,
        second.id,
        PreviewRequest(expected_version=second.version, group_ids=[linked.group_id]),
    )
    before = await ledger_snapshot(db_session)
    result = await commit_import(
        db_session,
        owner.id,
        second.id,
        CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "second-evidence",
    )
    assert not result.transaction_ids and result.linked_row_ids == [rows[0].id]
    assert await ledger_snapshot(db_session) == before
    evidence = (
        await db_session.scalars(
            select(ImportEvidence).order_by(ImportEvidence.attributed_source_amount)
        )
    ).all()
    assert [item.attributed_source_amount for item in evidence] == [-100, 100]
    assert evidence[0].transaction_id == evidence[1].transaction_id == first.transaction_ids[0]
    txn = await db_session.get(FinancialTransaction, first.transaction_ids[0])
    assert (
        txn.type == "transfer"
        and len(
            (
                await db_session.scalars(select(Posting).where(Posting.transaction_id == txn.id))
            ).all()
        )
        == 2
    )
