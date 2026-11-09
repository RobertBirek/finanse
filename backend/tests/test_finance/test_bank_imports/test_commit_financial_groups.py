from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.documents import service as documents
from app.finance.imports.commit import commit_import
from app.finance.imports.decisions import save_decisions
from app.finance.imports.models import ImportEvidence
from app.finance.imports.preview import prepare_preview
from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest
from app.finance.models import FinancialTransaction, Posting
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import
from tests.test_finance.test_bank_imports.review_fixtures import additional_source, review_case
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration


async def test_refund_commit_remains_expense_not_income(db_session, owner, tmp_path, monkeypatch):
    case, request = await confirmed_import(
        db_session,
        owner.id,
        tmp_path,
        monkeypatch,
        parsed_statement(account_reference=None, rows=[statement_row(amount=100)]),
        kind="expense_refund",
    )
    result = await commit_import(db_session, owner.id, case.batch_id, request, "refund")
    transaction = await db_session.get(FinancialTransaction, result.transaction_ids[0])
    posting = await db_session.scalar(select(Posting).where(Posting.account_id == case.account.id))
    assert transaction.type == "expense" and posting.direction == "credit"
    assert posting.source_amount == 100 and transaction.source == "bank_import"


async def test_fx_commit_keeps_both_actual_legs_without_provider_calls(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.entities import create_account
    from app.finance.nbp_rates import NbpRateProvider
    from app.finance.schemas import AccountCreate

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(
            account_reference=None,
            currency="EUR",
            opening=0,
            rows=[statement_row(amount=-100, currency="EUR")],
        ),
    )
    _source, rows = await additional_source(
        db_session,
        owner.id,
        case.batch_id,
        tmp_path,
        parsed_statement(
            account_reference=None,
            currency="USD",
            opening=0,
            rows=[statement_row(amount=125, currency="USD")],
        ),
    )
    other = await create_account(
        db_session, owner.id, AccountCreate(name="USD", type="checking", currency="USD")
    )
    decision = case.decision.model_copy(
        update={
            "kind": "exchange",
            "other_account_id": other.id,
            "category_id": None,
            "row_ids": [case.rows[0].id, rows[0].id],
            "manual_rate": Decimal("4.0"),
        }
    )
    # model_validate gives the same Decimal conversion as the HTTP boundary.
    decision = type(decision).model_validate(decision.model_dump())
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

    async def forbidden(*args, **kwargs):
        raise AssertionError("Commit may not fetch rates")

    monkeypatch.setattr(NbpRateProvider, "get_rate", forbidden)
    result = await commit_import(
        db_session,
        owner.id,
        batch.id,
        CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "fx",
    )
    assert len(result.transaction_ids) == 1 and result.commit_state == "committed"
    postings = (
        await db_session.scalars(
            select(Posting)
            .where(Posting.transaction_id == result.transaction_ids[0])
            .order_by(Posting.direction)
        )
    ).all()
    assert {posting.source_currency: posting.source_amount for posting in postings} == {
        "EUR": 100,
        "USD": 125,
    }
    assert {posting.base_amount_pln for posting in postings} == {400}
    assert sorted(
        (await db_session.scalars(select(ImportEvidence.attributed_source_amount))).all()
    ) == [-100, 125]


async def test_card_statement_uses_card_service_and_retry_does_not_duplicate_metadata(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.credit_card_models import CardStatement
    from app.finance.credit_card_schemas import CardConfig
    from app.finance.credit_cards import configure
    from tests.test_finance.test_bank_imports.test_card_headers import confirmed
    from tests.test_finance.test_bank_imports.test_velo_card import card_statement

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path, card_statement())
    await configure(
        db_session,
        owner.id,
        case.account.id,
        CardConfig(
            limit_pln=3360000,
            apr="14.50",
            cycle_close_day=17,
            due_day=12,
            grace_days=57,
            expected_version=0,
        ),
    )
    decision = case.decision.model_copy(
        update={"row_ids": [case.rows[1].id], "card_header": confirmed(account_id=case.account.id)}
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
    request = CommitRequest(preview_id=preview.id, request_hash=preview.request_hash)
    result = await commit_import(db_session, owner.id, batch.id, request, "card")
    assert await commit_import(db_session, owner.id, batch.id, request, "card") == result
    assert await db_session.scalar(select(func.count()).select_from(CardStatement)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
