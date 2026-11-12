import uuid

import pytest
from sqlalchemy import func, select

from app.finance.imports.commands import get_command_result
from app.finance.imports.commit import commit_import
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportBatch, ImportEvidence
from app.finance.models import FinanceCommandReceipt, FinancialTransaction, Posting
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import
from tests.test_finance.test_bank_imports.factories import ledger_snapshot
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration


async def test_replay_does_not_repost_and_lost_response_can_be_read(
    db_session, owner, tmp_path, monkeypatch
):
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    first = await commit_import(db_session, owner.id, case.batch_id, request, "same-intent")
    after = await ledger_snapshot(db_session)
    again = await commit_import(db_session, owner.id, case.batch_id, request, "same-intent")
    assert again == first and await ledger_snapshot(db_session) == after
    assert first.commit_state == "partial" and len(first.transaction_ids) == 1
    assert await get_command_result(
        db_session, owner.id, case.batch_id, "same-intent"
    ) == first.model_dump(mode="json")
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 1
    evidence = (await db_session.scalars(select(ImportEvidence))).one()
    assert evidence.row_id == case.rows[0].id and evidence.attributed_source_amount == -100
    assert evidence.component == "main" and evidence.receipt_id == first.receipt_id


async def test_reusing_key_for_another_payload_is_conflict_not_a_second_command(
    db_session, owner, tmp_path, monkeypatch
):
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    await commit_import(db_session, owner.id, case.batch_id, request, "same-key")
    after = await ledger_snapshot(db_session)
    with pytest.raises(ImportError) as error:
        await commit_import(
            db_session,
            owner.id,
            case.batch_id,
            request.model_copy(update={"request_hash": "0" * 64}),
            "same-key",
        )
    assert (
        error.value.code == "idempotency_key_reused" and await ledger_snapshot(db_session) == after
    )


async def test_fee_and_main_are_atomic_and_account_net_is_not_double_charged(
    db_session, owner, tmp_path, monkeypatch
):
    # Category is deliberately chosen only after the owned fixture exists.
    from app.documents import service as documents
    from app.finance.imports.decisions import save_decisions
    from app.finance.imports.preview import prepare_preview
    from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest
    from tests.test_finance.test_bank_imports.review_fixtures import review_case

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    case = await review_case(
        db_session,
        owner.id,
        tmp_path,
        parsed_statement(account_reference=None, rows=[statement_row(amount=-120, fee=20)]),
    )
    decision = case.decision.model_copy(update={"fee_category_id": case.category.id})
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
    before = await ledger_snapshot(db_session)
    from app.finance.imports import commit as commits

    real = commits.create_bank_transaction
    count = 0

    async def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise ValueError("synthetic fee failure")
        return await real(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(commits, "create_bank_transaction", fail_second)
        with pytest.raises(ValueError, match="synthetic fee failure"):
            await commit_import(db_session, owner.id, batch.id, request, "atomic-fee")
    assert await ledger_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ImportEvidence)) == 0
    result = await commit_import(db_session, owner.id, batch.id, request, "atomic-fee")
    assert result.commit_state == "committed" and len(result.transaction_ids) == 2
    postings = (
        await db_session.scalars(select(Posting).where(Posting.account_id == case.account.id))
    ).all()
    assert sorted(posting.source_amount for posting in postings) == [20, 100]
    assert all(posting.direction == "debit" for posting in postings)


@pytest.mark.parametrize("mutation", ["account", "source", "decision"])
async def test_changed_preview_rejects_all_financial_effects(
    db_session, owner, tmp_path, monkeypatch, mutation
):
    from app.finance.imports.models import ImportDecision, ImportSource

    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    if mutation == "account":
        case.account.name = "Changed"
    elif mutation == "source":
        source = await db_session.get(ImportSource, case.source_id)
        source.validation_state = "blocked"
    else:
        decision = await db_session.scalar(
            select(ImportDecision).where(ImportDecision.group_id == case.decision.group_id)
        )
        decision.data = dict(decision.data) | {"acknowledgements": ["changed"]}
    await db_session.flush()
    before = await ledger_snapshot(db_session)
    with pytest.raises(ImportError) as error:
        await commit_import(db_session, owner.id, case.batch_id, request, "stale")
    assert error.value.code == "preview_stale" and await ledger_snapshot(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


async def test_foreign_batch_preview_and_command_are_private(
    db_session, owner, other_owner, tmp_path, monkeypatch
):
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    for batch_id in [case.batch_id, uuid.uuid4()]:
        with pytest.raises(ImportError) as error:
            await commit_import(db_session, other_owner.id, batch_id, request, "foreign")
        assert error.value.http_status == 404
    with pytest.raises(ImportError) as error:
        await get_command_result(db_session, other_owner.id, case.batch_id, "foreign")
    assert error.value.http_status == 404
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0


@pytest.mark.parametrize(
    "change", [{"transaction_date": "2026-01-04"}, {"is_pending": True}, {"delete": True}]
)
async def test_source_evidence_protects_imported_payment_identity(
    db_session, owner, tmp_path, monkeypatch, change
):
    from app.finance.schemas import TransactionUpdate
    from app.finance.transactions import delete_transaction, update_transaction

    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    result = await commit_import(db_session, owner.id, case.batch_id, request, "protected")
    with pytest.raises(ValueError, match="[Ii]mport|źród|[Bb]ank"):
        if change.get("delete"):
            await delete_transaction(db_session, owner.id, result.transaction_ids[0])
        else:
            await update_transaction(
                db_session, owner.id, result.transaction_ids[0], TransactionUpdate(**change)
            )
    # Narrative overlays replace the old permission to rewrite bank evidence.
    with pytest.raises(ValueError, match="Oryginalny opis importu"):
        await update_transaction(
            db_session,
            owner.id,
            result.transaction_ids[0],
            TransactionUpdate(description="Reviewed description"),
        )
    from app.finance.annotation_schemas import AnnotationUpdate
    from app.finance.annotations import get_annotations, update_annotations

    context = await get_annotations(db_session, owner.id, result.transaction_ids[0])
    updated = await update_annotations(
        db_session,
        owner.id,
        result.transaction_ids[0],
        AnnotationUpdate(
            display_description="Reviewed description",
            note=None,
            tags=[],
            project_id=None,
            expected_version=context.version,
            expected_context_snapshot=context.context_snapshot,
        ),
        idempotency_key="descriptive-overlay",
    )
    assert updated.display_description == "Reviewed description"
    assert updated.original_description == context.original_description
    assert (await db_session.get(ImportBatch, case.batch_id)).version == 3
