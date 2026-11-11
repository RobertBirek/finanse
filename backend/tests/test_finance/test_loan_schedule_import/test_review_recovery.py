"""Review regressions: durable reopen discovery and explicit reparse revision choice."""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.finance.imports.contracts import ParsedSchedule
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportRevision, ImportRow
from app.finance.loan_schedule_commands import activate_schedule
from app.finance.loan_schedule_models import LoanScheduleRevision
from app.finance.loan_schedule_preview import prepare_schedule_preview
from app.finance.loan_schedule_schemas import ScheduleActivateRequest, SchedulePreviewRequest
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_loan_schedule_import.activation_fixtures import confirmed_case
from tests.test_finance.test_loan_schedule_import.factories import financial_history_snapshot

pytestmark = pytest.mark.integration


async def candidate(db, owner_id, case, *, changed=False, number=2, invalid=False):
    value = case.parsed.model_dump(mode="json")
    value["parser_version"] = f"synthetic-review-v{number}"
    if changed:
        value["rows"][1]["interest"] += 1
        value["rows"][1]["total"] += 1
    if invalid:
        value["checks"][0]["result"] = "failed"
    parsed = ParsedSchedule.model_validate(value)
    revision = ImportRevision(
        user_id=owner_id,
        batch_id=case.batch.id,
        source_id=case.source.id,
        number=number,
        source_sha256=case.document.sha256_hash,
        parser_version=parsed.parser_version,
        result=parsed.model_dump(mode="json"),
        checks=[c.model_dump(mode="json") for c in parsed.checks],
        warnings=["reparse_requires_comparison"],
    )
    db.add(revision)
    await db.flush()
    for ordinal, row in enumerate(parsed.rows, 1):
        fields = row.model_dump(mode="json")
        db.add(
            ImportRow(
                user_id=owner_id,
                batch_id=case.batch.id,
                source_id=case.source.id,
                revision_id=revision.id,
                kind="loan_schedule",
                ordinal=ordinal,
                source_key=str(row.bank_number),
                row_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
                fields=fields,
            )
        )
    case.batch.version += 1
    await db.flush()
    return revision


def request_for(case, revision, *, ack=True):
    return SchedulePreviewRequest.model_validate(
        {
            "expected_version": case.batch.version,
            "source_id": case.source.id,
            "source_revision_id": revision.id,
            "target": {"loan_id": case.loan.id},
            "acknowledgements": [
                f"schedule_target:{case.source.id}",
                *([f"reparse_comparison:{case.source.id}:{revision.id}"] if ack else []),
            ],
        }
    )


async def test_reopen_without_command_key_discovers_original_activation_and_no_foreign_result(
    db_session, owner, other_owner, tmp_path, monkeypatch
):
    case, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    result = await activate_schedule(
        db_session, owner.id, case.batch.id, request, "original-result"
    )
    await db_session.commit()
    async with client_for(db_session, owner.id) as client:
        response = await client.get(f"/api/finance/imports/{case.batch.id}")
        assert response.status_code == 200
        activation = response.json()["sources"][0]["schedule_activations"][0]
        assert activation["source_revision_id"] == str(case.revision.id)
        assert activation["result"] == result.model_dump(mode="json")
    async with client_for(db_session, other_owner.id) as client:
        assert (await client.get(f"/api/finance/imports/{case.batch.id}")).status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 2


async def test_equivalent_new_parser_preview_identifies_same_receipt_without_new_version(
    db_session, owner, tmp_path, monkeypatch
):
    case, _preview, request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    original = await activate_schedule(
        db_session, owner.id, case.batch.id, request, "before-reparse"
    )
    revision = await candidate(db_session, owner.id, case)
    before = await financial_history_snapshot(db_session)
    compared = await prepare_schedule_preview(
        db_session, owner.id, case.batch.id, request_for(case, revision)
    )
    assert compared.source_revision_id == revision.id and compared.existing_activation == original
    assert await financial_history_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 2
    assert case.source.current_revision_id == case.revision.id


@pytest.mark.parametrize("problem", ["no_ack", "foreign_revision", "old_choice", "bad_checks"])
async def test_candidate_requires_owned_latest_choice_valid_controls_and_exact_ack(
    db_session, owner, tmp_path, monkeypatch, problem
):
    case, _preview, _request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    revision = await candidate(db_session, owner.id, case, invalid=problem == "bad_checks")
    data = request_for(case, revision, ack=problem != "no_ack")
    if problem == "foreign_revision":
        data = data.model_copy(update={"source_revision_id": uuid.uuid4()})
    if problem == "old_choice":
        await candidate(db_session, owner.id, case, number=3)
        data = data.model_copy(update={"expected_version": case.batch.version})
    with pytest.raises(ImportError):
        await prepare_schedule_preview(db_session, owner.id, case.batch.id, data)
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0


async def test_reviewed_changed_candidate_uses_diff_and_preserves_old_source_history(
    db_session, owner, tmp_path, monkeypatch
):
    case, _preview, _request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    revision = await candidate(db_session, owner.id, case, changed=True)
    preview = await prepare_schedule_preview(
        db_session, owner.id, case.batch.id, request_for(case, revision)
    )
    assert preview.existing_activation is None and preview.source_revision_id == revision.id
    assert len(preview.diff.new_rows) == 2 and not preview.diff.conflicts
    before = await financial_history_snapshot(db_session)
    result = await activate_schedule(
        db_session,
        owner.id,
        case.batch.id,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
        "changed-reparse",
    )
    saved = await db_session.get(LoanScheduleRevision, result.revision_id)
    assert saved.source_revision_id == revision.id
    assert case.source.current_revision_id == case.revision.id
    assert await financial_history_snapshot(db_session) == before
    from app.finance.imports.queries import get_batch

    loaded = await get_batch(db_session, owner.id, case.batch.id)
    assert loaded.commit_state == "committed" and loaded.unresolved_count == 0


async def test_new_candidate_after_review_invalidates_frozen_preview(
    db_session, owner, tmp_path, monkeypatch
):
    case, _preview, _request = await confirmed_case(db_session, owner.id, tmp_path, monkeypatch)
    revision = await candidate(db_session, owner.id, case, changed=True)
    preview = await prepare_schedule_preview(
        db_session, owner.id, case.batch.id, request_for(case, revision)
    )
    await candidate(db_session, owner.id, case, number=3)
    with pytest.raises(ImportError):
        await activate_schedule(
            db_session,
            owner.id,
            case.batch.id,
            ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
            "changed-after-comparison",
        )
    assert await db_session.scalar(select(func.count()).select_from(LoanScheduleRevision)) == 0
