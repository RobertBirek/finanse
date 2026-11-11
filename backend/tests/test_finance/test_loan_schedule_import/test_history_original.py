import pytest

from tests.test_finance.test_loan_schedule_import.activation_fixtures import confirmed_case

pytestmark = pytest.mark.integration


async def test_history_binds_each_bank_version_to_its_owned_original_without_live_installment_values(
    db_session, owner, other_owner, tmp_path, monkeypatch
):
    from app.finance.loan_schedule_commands import (
        activate_schedule,
        get_schedule_revision,
        list_schedule_revisions,
    )

    case, preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    assert preview.bank_effective_date == case.parsed.effective_date
    result = await activate_schedule(db_session, owner.id, case.batch.id, request, "history-source")
    versions = await list_schedule_revisions(db_session, owner.id, case.loan.id)
    bank = next(v for v in versions if v.kind == "bank_import")
    assert bank.document_id == case.document.id and bank.batch_id == case.batch.id
    assert bank.original_name == "synthetic-schedule.pdf"
    baseline = next(v for v in versions if v.kind == "manual_baseline")
    assert baseline.document_id is None and baseline.batch_id is None
    case.installment.interest_pln = 999
    await db_session.flush()
    history = await get_schedule_revision(db_session, owner.id, case.loan.id, result.revision_id)
    assert history.installments[0].interest_pln == 2000
    assert (
        await get_schedule_revision(db_session, other_owner.id, case.loan.id, result.revision_id)
        is None
    )
