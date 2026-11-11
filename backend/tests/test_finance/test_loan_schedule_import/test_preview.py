import copy
import uuid

import pytest
from sqlalchemy import func, select

from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportPreview
from app.finance.models import LoanAgreement
from tests.test_finance.test_loan_schedule_import.activation_fixtures import schedule_case
from tests.test_finance.test_loan_schedule_import.factories import financial_history_snapshot

pytestmark = pytest.mark.integration


async def test_preview_freezes_source_target_diff_and_day_without_financial_writes(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_preview import prepare_schedule_preview

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    before = await financial_history_snapshot(db_session)
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    assert preview.ledger_effect == "none" and preview.source_revision_id == case.revision.id
    assert preview.target.loan_id == case.loan.id and preview.diff.reused_ids == [
        case.installment.id
    ]
    assert len(preview.diff.new_rows) == 2 and not preview.diff.conflicts
    saved = await db_session.get(ImportPreview, preview.id)
    payload = copy.deepcopy(saved.payload)
    case.installment.interest_pln += 1
    await db_session.flush()
    await db_session.refresh(saved)
    assert saved.payload == payload and saved.request_hash == preview.request_hash
    assert await financial_history_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(LoanAgreement)) == 1


async def test_mapping_needs_explicit_ack_and_stale_batch_is_not_silently_rebased(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_preview import prepare_schedule_preview

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    with pytest.raises(ImportError) as caught:
        await prepare_schedule_preview(
            db_session,
            owner.id,
            case.batch.id,
            case.request.model_copy(update={"acknowledgements": []}),
        )
    assert caught.value.code == "import_acknowledgement_required"
    with pytest.raises(ImportError) as caught:
        await prepare_schedule_preview(
            db_session,
            owner.id,
            case.batch.id,
            case.request.model_copy(update={"expected_version": 999}),
        )
    assert caught.value.http_status == 409


@pytest.mark.parametrize(
    "target", ["foreign_loan", "foreign_account", "foreign_source", "currency", "card"]
)
async def test_preview_owner_currency_and_card_target_guards(
    db_session, owner, other_owner, tmp_path, monkeypatch, target
):
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleTarget
    from app.finance.models import Account

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    request = case.request
    if target == "foreign_loan":
        request = request.model_copy(update={"target": ScheduleTarget(loan_id=uuid.uuid4())})
    elif target == "foreign_source":
        request = request.model_copy(update={"source_id": uuid.uuid4()})
    else:
        account = await db_session.get(Account, case.loan.account_id)
        if target == "currency":
            account.currency = "EUR"
        elif target == "card":
            account.type = "credit_card"
        else:
            account.user_id = other_owner.id
        await db_session.flush()
    with pytest.raises(ImportError) as caught:
        await prepare_schedule_preview(db_session, owner.id, case.batch.id, request)
    assert caught.value.http_status in {404, 422}
