import uuid

import pytest
from sqlalchemy import func, select

from app.documents import service as documents
from app.finance.imports.decisions import save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportDecision, ImportGroupRow
from app.finance.imports.schemas import DecisionUpdate
from tests.test_finance.test_bank_imports.factories import ledger_snapshot
from tests.test_finance.test_bank_imports.review_fixtures import review_case

pytestmark = pytest.mark.integration


async def test_decisions_are_versioned_persistent_and_do_not_post(
    db_session, owner, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(db_session, owner.id, tmp_path)
    before = await ledger_snapshot(db_session)
    result = await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(expected_version=1, decisions=[case.decision]),
    )
    assert result.version == 2
    assert len(result.groups) == 1 and result.groups[0].id == case.decision.group_id
    assert result.groups[0].row_ids == [case.rows[0].id]
    assert result.groups[0].decision["action"] == "create"
    from app.finance.imports.service import list_rows

    page = await list_rows(db_session, owner.id, case.batch_id, source_id=None, offset=0, limit=10)
    assert page.items[0].decision["group_id"] == str(case.decision.group_id)
    assert page.items[1].decision is None
    assert await db_session.scalar(select(func.count()).select_from(ImportGroupRow)) == 1
    change = case.decision.model_copy(update={"action": "defer"})
    await save_decisions(
        db_session, owner.id, case.batch_id, DecisionUpdate(expected_version=2, decisions=[change])
    )
    assert await db_session.scalar(select(func.count()).select_from(ImportDecision)) == 2
    assert await ledger_snapshot(db_session) == before


@pytest.mark.parametrize("field", ["account_id", "category_id"])
async def test_foreign_or_unknown_mapping_is_not_silently_accepted(
    db_session, owner, tmp_path, field
) -> None:
    case = await review_case(db_session, owner.id, tmp_path)
    decision = case.decision.model_copy(update={field: uuid.uuid4()})
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[decision]),
        )
    assert error.value.http_status == 404


async def test_wrong_iban_is_not_overridden_by_a_valid_currency(
    db_session, owner, tmp_path
) -> None:
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement

    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(account_reference="00111111111111111111111111"),
    )
    case.account.iban = "PL00222222222222222222222222"
    await db_session.flush()
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[case.decision]),
        )
    assert error.value.code == "account_reference_mismatch"


async def test_stale_version_cannot_overwrite_another_review(db_session, owner, tmp_path) -> None:
    case = await review_case(db_session, owner.id, tmp_path)
    data = DecisionUpdate(expected_version=1, decisions=[case.decision])
    await save_decisions(db_session, owner.id, case.batch_id, data)
    with pytest.raises(ImportError) as error:
        await save_decisions(db_session, owner.id, case.batch_id, data)
    assert error.value.code == "import_version_conflict"


async def test_fx_without_actual_second_leg_is_not_a_transfer_estimate(
    db_session, owner, tmp_path
) -> None:
    from app.finance.entities import create_account
    from app.finance.schemas import AccountCreate

    case = await review_case(db_session, owner.id, tmp_path)
    other = await create_account(
        db_session, owner.id, AccountCreate(name="Synthetic EUR", type="checking", currency="EUR")
    )
    decision = case.decision.model_copy(
        update={"kind": "exchange", "other_account_id": other.id, "category_id": None}
    )
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[decision]),
        )
    assert error.value.code == "exchange_leg_missing"


async def test_cash_withdrawal_cannot_be_disguised_as_external_expense(
    db_session, owner, tmp_path
) -> None:
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    payload = parsed_statement(
        account_reference=None, rows=[statement_row(raw={"Rodzaj": "Cash withdrawal"})]
    )
    case = await review_case(db_session, owner.id, tmp_path, payload)
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[case.decision]),
        )
    assert error.value.code == "cash_account_required"


async def test_pending_row_can_be_deferred_but_never_created(db_session, owner, tmp_path) -> None:
    from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(
            account_reference=None, rows=[statement_row(state="pending", booking_date=None)]
        ),
    )
    with pytest.raises(ImportError) as error:
        await save_decisions(
            db_session,
            owner.id,
            case.batch_id,
            DecisionUpdate(expected_version=1, decisions=[case.decision]),
        )
    assert error.value.code == "row_not_postable"
    await save_decisions(
        db_session,
        owner.id,
        case.batch_id,
        DecisionUpdate(
            expected_version=1,
            decisions=[
                case.decision.model_copy(
                    update={
                        "action": "defer",
                        "kind": None,
                        "account_id": None,
                        "category_id": None,
                    }
                )
            ],
        ),
    )
