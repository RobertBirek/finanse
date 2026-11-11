import pytest

from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_loan_schedule_import.activation_fixtures import schedule_case

pytestmark = pytest.mark.integration


async def test_owner_preview_activate_history_and_shared_receipt_recovery(
    db_session, owner, other_owner, tmp_path, monkeypatch
):
    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    root = f"/api/finance/imports/{case.batch.id}"
    async with client_for(db_session, owner.id) as client:
        response = await client.post(
            root + "/schedule-preview",
            json=case.request.model_dump(mode="json"),
            headers={"Idempotency-Key": "preview-http"},
        )
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["ledger_effect"] == "none"
        body = {"preview_id": preview["id"], "request_hash": preview["request_hash"]}
        rejected = await client.post(
            root + "/activate-schedule",
            json=body | {"postings": []},
            headers={"Idempotency-Key": "no-postings"},
        )
        assert rejected.status_code == 422
        result = await client.post(
            root + "/activate-schedule", json=body, headers={"Idempotency-Key": "activate-http"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["ledger_changed"] is False
        recovered = await client.get(root + "/commands/activate-http")
        assert recovered.json() == result.json()
        revisions = await client.get(f"/api/finance/loans/{case.loan.id}/schedule-revisions")
        assert revisions.status_code == 200 and len(revisions.json()) == 2
        revision_id = result.json()["revision_id"]
        detail = await client.get(
            f"/api/finance/loans/{case.loan.id}/schedule-revisions/{revision_id}"
        )
        assert detail.status_code == 200 and len(detail.json()["installments"]) == 3
    async with client_for(db_session, other_owner.id) as client:
        assert (await client.get(root + "/commands/activate-http")).status_code == 404
        assert (
            await client.get(f"/api/finance/loans/{case.loan.id}/schedule-revisions")
        ).status_code == 404
        assert (
            await client.get(f"/api/finance/loans/{case.loan.id}/schedule-revisions/{revision_id}")
        ).status_code == 404
        assert (
            await client.post(
                root + "/activate-schedule", json=body, headers={"Idempotency-Key": "activate-http"}
            )
        ).status_code == 404


async def test_preview_id_from_another_batch_cannot_be_used(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.imports.models import ImportBatch
    from app.finance.loan_schedule_preview import prepare_schedule_preview

    case = await schedule_case(db_session, owner.id, tmp_path, monkeypatch)
    preview = await prepare_schedule_preview(db_session, owner.id, case.batch.id, case.request)
    other = ImportBatch(user_id=owner.id, kind="loan_schedule")
    db_session.add(other)
    await db_session.flush()
    async with client_for(db_session, owner.id) as client:
        response = await client.post(
            f"/api/finance/imports/{other.id}/activate-schedule",
            json={"preview_id": str(preview.id), "request_hash": preview.request_hash},
            headers={"Idempotency-Key": "wrong-batch"},
        )
        assert response.status_code == 404
