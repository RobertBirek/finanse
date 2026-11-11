import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.finance import loans
from app.finance.imports.errors import ImportError
from app.finance.loan_schedule_models import LoanScheduleMembership, LoanScheduleRevision
from app.finance.loan_schemas import LoanCreate, LoanInstallmentCreate
from app.finance.models import (
    Account,
    FinanceCommandReceipt,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
)
from tests.test_finance.test_loan_schedule_import.activation_fixtures import (
    confirmed_case,
    schedule_case,
)
from tests.test_finance.test_loan_schedule_import.factories import (
    financial_history_snapshot,
    payment_transfer,
)

pytestmark = pytest.mark.integration


async def test_activation_reuses_linked_uuid_without_mutating_ledger_or_old_values(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import (
        activate_schedule,
        get_schedule_revision,
        list_schedule_revisions,
    )
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    transfer = await payment_transfer(db_session, owner.id, case.loan)
    await loans.link_loan_payment(
        db_session, owner.id, case.loan.id, case.installment.id, transfer.id
    )
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    before = await financial_history_snapshot(db_session)
    result = await activate_schedule(
        db_session,
        owner.id,
        case.batch.id,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "activate-once",
    )
    assert not result.ledger_changed and result.loan_id == case.loan.id
    assert result.reused_ids == [case.installment.id] and len(result.new_ids) == 2
    assert await financial_history_snapshot(db_session) == before
    await db_session.refresh(case.installment)
    assert (
        case.installment.number,
        case.installment.principal_pln,
        case.installment.interest_pln,
    ) == (1, 100000, 2000)
    assert (
        await db_session.scalar(
            select(LoanPaymentLink.installment_id).where(
                LoanPaymentLink.transaction_id == transfer.id
            )
        )
        == case.installment.id
    )
    revisions = await list_schedule_revisions(db_session, owner.id, case.loan.id)
    assert len(revisions) == 2 and sum(r.state == "active" for r in revisions) == 1
    baseline = next(r for r in revisions if r.kind == "manual_baseline")
    original = await get_schedule_revision(db_session, owner.id, case.loan.id, baseline.id)
    assert len(original.installments) == 1 and original.installments[0].principal_pln == 100000
    latest = await get_schedule_revision(db_session, owner.id, case.loan.id, result.revision_id)
    assert [i.bank_number for i in latest.installments] == [1, 2, 3]


async def test_lost_response_replay_after_day_change_returns_same_receipt(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance import loan_schedule_preview as preview_module
    from app.finance.loan_schedule_commands import activate_schedule

    case, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    first = await activate_schedule(db_session, owner.id, case.batch.id, request, "lost-response")
    await db_session.commit()
    today = preview_module._local_today()
    monkeypatch.setattr(preview_module, "_local_today", lambda: today + timedelta(days=1))
    second = await activate_schedule(db_session, owner.id, case.batch.id, request, "lost-response")
    assert first == second
    with pytest.raises(ImportError):
        await activate_schedule(
            db_session, owner.id, case.batch.id, request, "new-intent-stale-day"
        )
    with pytest.raises(ImportError) as caught:
        await activate_schedule(
            db_session,
            owner.id,
            case.batch.id,
            request.model_copy(update={"request_hash": "b" * 64}),
            "lost-response",
        )
    assert caught.value.code == "idempotency_key_reused"


@pytest.mark.parametrize(
    "change", ["payment", "day", "archive", "file", "row", "preview", "loan", "account", "overflow"]
)
async def test_changed_snapshot_refuses_atomically_without_versions_or_receipt(
    db_session, owner, tmp_path, monkeypatch, change
):
    from app.finance import loan_schedule_preview as preview_module
    from app.finance.loan_schedule_commands import activate_schedule

    case, preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    if change == "payment":
        transfer = await payment_transfer(db_session, owner.id, case.loan)
        await loans.link_loan_payment(
            db_session, owner.id, case.loan.id, case.installment.id, transfer.id
        )
    elif change == "day":
        today = preview_module._local_today()
        monkeypatch.setattr(preview_module, "_local_today", lambda: today + timedelta(days=1))
    elif change == "archive":
        from datetime import UTC, datetime

        case.document.archived_at = datetime.now(UTC)
    elif change == "file":
        (tmp_path / case.document.storage_path).write_bytes(b"changed")
    elif change == "row":
        case.rows[0].fields = case.rows[0].fields | {"interest": 999}
    elif change == "preview":
        from app.finance.imports.models import ImportPreview

        saved = await db_session.get(ImportPreview, preview.id)
        saved.payload = saved.payload | {"owner_id": str(uuid.uuid4())}
    elif change == "loan":
        case.loan.is_active = False
    elif change == "account":
        (await db_session.get(Account, case.loan.account_id)).is_active = False
    else:
        case.installment.number = 2147483647
    await db_session.flush()
    before = await financial_history_snapshot(db_session)
    with pytest.raises(ImportError):
        await activate_schedule(db_session, owner.id, case.batch.id, request, "changed-snapshot")
    assert await financial_history_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinanceCommandReceipt)
            .where(FinanceCommandReceipt.key == "changed-snapshot")
        )
        == 0
    )


async def test_explicit_new_target_creates_one_contract_only_at_activation(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.entities import create_account
    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest, ScheduleTarget
    from app.finance.schemas import AccountCreate

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    debt = await create_account(
        db_session, owner.id, AccountCreate(name="New synthetic debt", type="credit")
    )
    payer = await create_account(
        db_session, owner.id, AccountCreate(name="New synthetic payer", type="checking")
    )
    request = case.request.model_copy(
        update={
            "target": ScheduleTarget(
                new_loan=LoanCreate(
                    name="New contract", account_id=debt.id, payment_account_id=payer.id
                )
            )
        }
    )
    before = await financial_history_snapshot(db_session)
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, request)
    assert await db_session.scalar(select(func.count()).select_from(LoanAgreement)) == 1
    result = await activate_schedule(
        db_session,
        owner.id,
        case.batch.id,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "new-contract",
    )
    assert result.loan_id != case.loan.id and len(result.new_ids) == 3
    assert await db_session.scalar(select(func.count()).select_from(LoanAgreement)) == 2
    assert await financial_history_snapshot(db_session) == before


async def test_shorter_full_tail_archives_old_last_row_without_deleting_history(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    last = await loans.create_loan_installment(
        db_session,
        owner.id,
        case.loan.id,
        LoanInstallmentCreate(
            number=99, due_date="2030-01-01", principal_pln=500, interest_pln=0, fees_pln=0
        ),
    )
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    result = await activate_schedule(
        db_session,
        owner.id,
        case.batch.id,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "shorter-plan",
    )
    assert result.superseded_ids == [last.id]
    await db_session.refresh(last)
    assert last.superseded_by_revision_id == result.revision_id
    detail = await loans.get_loan(db_session, owner.id, case.loan.id)
    assert last.id not in {i.id for i in detail.installments} and len(detail.installments) == 3
    assert await db_session.get(LoanInstallment, last.id) is not None
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleMembership)) == 5


async def test_identical_59_row_import_with_one_payment_reuses_all_ids_and_original_fields(
    db_session, owner, tmp_path, monkeypatch
):
    from datetime import date

    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest
    from tests.test_finance.test_loan_schedule_import.test_parser import HEADER

    table = "".join(
        f"{n} {date(2026, 12, 1) + timedelta(days=30 * (n - 1))} 100,00 10,00 110,00 {(59 - n) * 100},00\n"
        for n in range(1, 60)
    )
    case = await schedule_case(
        db_session, owner.id, tmp_path, monkeypatch, pdf_text=HEADER + table + "Strona 1 z 1"
    )
    case.installment.number = 501
    for row in case.parsed.rows[1:]:
        await loans.create_loan_installment(
            db_session,
            owner.id,
            case.loan.id,
            LoanInstallmentCreate(
                number=500 + row.bank_number,
                due_date=row.due_date,
                principal_pln=row.principal,
                interest_pln=row.interest,
                fees_pln=row.fees,
            ),
        )
    transfer = await payment_transfer(db_session, owner.id, case.loan)
    await loans.link_loan_payment(
        db_session, owner.id, case.loan.id, case.installment.id, transfer.id
    )
    before_rows = (
        await db_session.execute(
            select(LoanInstallment.__table__)
            .where(LoanInstallment.loan_id == case.loan.id)
            .order_by(LoanInstallment.number)
        )
    ).all()
    before = await financial_history_snapshot(db_session)
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    result = await activate_schedule(
        db_session,
        owner.id,
        case.batch.id,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "identical-59",
    )
    assert len(result.reused_ids) == 59 and not result.new_ids and not result.superseded_ids
    assert (
        await db_session.execute(
            select(LoanInstallment.__table__)
            .where(LoanInstallment.loan_id == case.loan.id)
            .order_by(LoanInstallment.number)
        )
    ).all() == before_rows
    assert await financial_history_snapshot(db_session) == before


async def test_max_internal_number_blocks_new_ids_before_any_version_is_written(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    case.installment.number = 2147483647
    await db_session.flush()
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    with pytest.raises(ImportError):
        await activate_schedule(
            db_session,
            owner.id,
            case.batch.id,
            ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
            "number-overflow",
        )
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0


async def test_future_link_omitted_from_new_plan_blocks_the_whole_activation(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import activate_schedule
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    future = await loans.create_loan_installment(
        db_session,
        owner.id,
        case.loan.id,
        LoanInstallmentCreate(
            number=2, due_date="2030-01-01", principal_pln=500, interest_pln=0, fees_pln=0
        ),
    )
    transfer = await payment_transfer(db_session, owner.id, case.loan)
    await loans.link_loan_payment(db_session, owner.id, case.loan.id, future.id, transfer.id)
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    assert preview.diff.conflicts
    before = await financial_history_snapshot(db_session)
    with pytest.raises(ImportError):
        await activate_schedule(
            db_session,
            owner.id,
            case.batch.id,
            ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
            "missing-linked-future",
        )
    assert await financial_history_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0
