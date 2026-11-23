from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service as documents
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportEvidence, ImportGroup, ImportPreview
from app.finance.imports.service import create_batch
from app.finance.imports.settlement import confirm_settlement, settlement_preview
from app.finance.imports.settlement_schemas import SettlementConfirm, SettlementSelection
from app.finance.models import FinancialTransaction
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from app.identity.models import User
from tests.test_finance.test_bank_imports.review_fixtures import (
    ReviewCase,
    additional_source,
    review_case,
)
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration


async def _case(db: AsyncSession, owner: User, directory: Path) -> ReviewCase:
    return await review_case(
        db,
        owner.id,
        directory,
        parsed_statement(
            account_reference=None,
            opening=0,
            closing=-1100,
            rows=[
                statement_row(
                    key="existing",
                    description="Known card purchase",
                    amount=-100,
                    raw={"description_lines": ["Płatność kartą", "Known card purchase"]},
                ),
                statement_row(
                    key="new",
                    description="New card purchase",
                    amount=-1000,
                    raw={"description_lines": ["Płatność kartą", "New card purchase"]},
                ),
            ],
        ),
    )


async def _existing(
    db: AsyncSession, owner: User, case: ReviewCase, day: str = "2026-01-03"
) -> FinancialTransaction:
    return await create_transaction(
        db,
        owner.id,
        TransactionCreate(
            transaction_date=day,
            description="Known card purchase",
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


async def test_read_only_then_link_and_create_atomically_with_replay(
    db_session: AsyncSession,
    owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await _case(db_session, owner, tmp_path)
    existing = await _existing(db_session, owner, case)
    view = await settlement_preview(db_session, owner.id, case.batch_id, case.account.id)
    assert [row.status for row in view.rows] == ["link", "create"]
    assert view.rows[0].target and view.rows[0].target.id == existing.id
    assert await db_session.scalar(select(ImportGroup.id)) is None
    assert await db_session.scalar(select(ImportPreview.id)) is None
    assert await db_session.scalar(select(ImportEvidence.id)) is None
    intent = SettlementConfirm(
        account_id=case.account.id,
        fingerprint=view.fingerprint,
        confirmed=True,
        selection=[
            SettlementSelection(row_id=case.rows[0].id),
            SettlementSelection(row_id=case.rows[1].id, category_id=case.category.id),
        ],
    )
    outcome = await confirm_settlement(db_session, owner.id, case.batch_id, intent, "settle-same")
    assert outcome.linked_row_ids == [case.rows[0].id]
    assert len(outcome.transaction_ids) == 1
    assert (
        await confirm_settlement(db_session, owner.id, case.batch_id, intent, "settle-same")
        == outcome
    )
    again = await settlement_preview(db_session, owner.id, case.batch_id, case.account.id)
    assert [row.status for row in again.rows] == ["settled", "settled"]
    assert len((await db_session.scalars(select(FinancialTransaction))).all()) == 2


async def test_same_bank_reference_cannot_reuse_a_transaction_in_another_import(
    db_session: AsyncSession,
    owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    payload = parsed_statement(
        account_reference=None,
        opening=0,
        closing=-100,
        rows=[
            statement_row(
                description="Known card purchase",
                bank_reference="synthetic-shared-bank-reference",
                raw={"description_lines": ["Płatność kartą", "Known card purchase"]},
            )
        ],
    )
    case = await review_case(db_session, owner.id, tmp_path, payload)
    existing = await _existing(db_session, owner, case)
    unrelated = await create_batch(db_session, owner.id, "statement")
    _, [duplicate] = await additional_source(db_session, owner.id, unrelated.id, tmp_path, payload)
    before = await settlement_preview(db_session, owner.id, unrelated.id, case.account.id)
    assert before.rows[0].status == "link"

    first = await settlement_preview(db_session, owner.id, case.batch_id, case.account.id)
    await confirm_settlement(
        db_session,
        owner.id,
        case.batch_id,
        SettlementConfirm(
            account_id=case.account.id,
            fingerprint=first.fingerprint,
            confirmed=True,
            selection=[SettlementSelection(row_id=case.rows[0].id)],
        ),
        "settle-first-reference",
    )
    after = await settlement_preview(db_session, owner.id, unrelated.id, case.account.id)
    assert after.rows[0].id == duplicate.id
    assert after.rows[0].status == "review"
    assert after.rows[0].reason == "possible_duplicate"
    assert after.rows[0].target is None
    assert before.fingerprint != after.fingerprint
    [evidence] = (await db_session.scalars(select(ImportEvidence))).all()
    assert evidence.transaction_id == existing.id
    assert evidence.row_id == case.rows[0].id


async def test_rejects_foreign_access_and_changed_ledger_without_saving_decisions(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await _case(db_session, owner, tmp_path)
    with pytest.raises(ImportError) as denied:
        await settlement_preview(db_session, other_owner.id, case.batch_id, case.account.id)
    assert denied.value.http_status == 404
    view = await settlement_preview(db_session, owner.id, case.batch_id, case.account.id)
    await _existing(db_session, owner, case, "2026-01-29")
    request = SettlementConfirm(
        account_id=case.account.id,
        fingerprint=view.fingerprint,
        confirmed=True,
        selection=[SettlementSelection(row_id=case.rows[1].id, category_id=case.category.id)],
    )
    with pytest.raises(ImportError) as stale:
        await confirm_settlement(db_session, owner.id, case.batch_id, request, "changed")
    assert stale.value.code == "settlement_stale"
    assert await db_session.scalar(select(ImportGroup.id)) is None


async def test_a_rejected_final_commit_rolls_back_the_saved_groups_and_preview(
    db_session: AsyncSession,
    owner: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.finance.imports import commit

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await _case(db_session, owner, tmp_path)
    view = await settlement_preview(db_session, owner.id, case.batch_id, case.account.id)

    async def fail_final_check(*_args: object) -> object:
        raise ImportError("preview_stale", "Synthetic failure after creating preview.")

    monkeypatch.setattr(commit, "_locked_payload", fail_final_check)
    intent = SettlementConfirm(
        account_id=case.account.id,
        fingerprint=view.fingerprint,
        confirmed=True,
        selection=[SettlementSelection(row_id=case.rows[1].id, category_id=case.category.id)],
    )
    with pytest.raises(ImportError) as failure:
        await confirm_settlement(db_session, owner.id, case.batch_id, intent, "fail-final")
    assert failure.value.code == "preview_stale"
    for model in (ImportGroup, ImportPreview, ImportEvidence, FinancialTransaction):
        assert await db_session.scalar(select(model.id)) is None
