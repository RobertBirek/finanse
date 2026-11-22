import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.documents import service as documents
from app.finance.imports.contracts import ParsedStatement
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportEvidence, ImportGroup, ImportSource
from app.finance.imports.queries import get_batch, list_rows
from app.finance.models import FinancialTransaction, Posting
from tests.test_finance.test_bank_imports.review_fixtures import ReviewCase, review_case
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement, statement_row

pytestmark = pytest.mark.integration

IBAN = "PL61109010140000071219812874"


def purchase(key: str, amount: int = -100, description: str = "Sklep testowy"):
    return statement_row(
        key=key,
        amount=amount,
        description=f"Płatność kartą\n{description}",
        raw={"description_lines": ["Płatność kartą", description]},
    )


async def case_with_rows(db, owner, path: Path, monkeypatch, **overrides: object) -> ReviewCase:
    monkeypatch.setattr(documents, "UPLOAD_DIR", path)
    values: dict[str, object] = {
        "account_reference": IBAN,
        "opening": 0,
        "closing": -70,
        "rows": [
            purchase("purchase"),
            statement_row(
                key="transfer", amount=30, raw={"description_lines": ["Przelew własny", "Test"]}
            ),
        ],
    }
    payload: ParsedStatement = parsed_statement(**(values | overrides))
    case = await review_case(db, owner, path, payload)
    case.account.iban = IBAN
    case.account.bank_name = "VeloBank"
    await db.flush()
    return case


async def configure(db, owner, case, *, enabled=False):
    from app.finance.imports.auto_post import set_auto_post_settings
    from app.finance.imports.schemas import AutoPostSettings

    await set_auto_post_settings(
        db, owner, AutoPostSettings(enabled=enabled, expense_category_id=case.category.id)
    )


async def queue(db, owner, case):
    from app.finance.imports.auto_post import queue_manual_auto_post
    from app.finance.imports.schemas import AutoPostRequest

    source = await db.get(ImportSource, case.source_id)
    return await queue_manual_auto_post(
        db,
        owner,
        case.batch_id,
        case.source_id,
        AutoPostRequest(revision_id=source.current_revision_id),
    )


async def test_one_existing_statement_books_only_unambiguous_rows_once(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.imports.auto_post import process_auto_post

    db = db_session
    case = await case_with_rows(db, owner.id, tmp_path, monkeypatch)
    await configure(db, owner.id, case)
    job = await queue(db, owner.id, case)
    await process_auto_post(db, job.id)
    await process_auto_post(db, job.id)
    batch = await get_batch(db, owner.id, case.batch_id)
    assert batch.commit_state == "partial" and batch.unresolved_count == 1
    assert batch.sources[0].auto_post.posted_count == 1
    rows = await list_rows(
        db, owner.id, case.batch_id, source_id=case.source_id, offset=0, limit=10
    )
    assert [row.auto_post_reason for row in rows.items] == [None, "movement_unclear"]
    evidence = (await db.scalars(select(ImportEvidence))).one()
    assert evidence.row_id == case.rows[0].id
    postings = (
        await db.scalars(select(Posting).where(Posting.transaction_id == evidence.transaction_id))
    ).all()
    assert len(postings) == 2
    assert (
        sum(p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln for p in postings)
        == 0
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"opening": 200}, "opening_gap"),
        ({"account_reference": "unmatched"}, "account_unresolved"),
        ({"layout": "velo_card_v1"}, "card_statement_review"),
        (
            {"checks": [{"code": "rollforward", "required": True, "result": "failed"}]},
            "source_validation_blocked",
        ),
    ],
)
async def test_source_exception_blocks_all_rows(
    db_session, owner, tmp_path, monkeypatch, overrides, reason
):
    from app.finance.imports.auto_post import process_auto_post

    db = db_session
    case = await case_with_rows(db, owner.id, tmp_path, monkeypatch, **overrides)
    await configure(db, owner.id, case)
    job = await queue(db, owner.id, case)
    await process_auto_post(db, job.id)
    batch = await get_batch(db, owner.id, case.batch_id)
    assert batch.sources[0].auto_post.reason == reason
    assert not batch.groups
    assert await db.scalar(select(func.count()).select_from(FinancialTransaction)) == 0


async def test_manual_decision_is_not_changed_and_possible_duplicates_are_not_posted(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.imports.auto_post import process_auto_post
    from app.finance.imports.decisions import save_decisions
    from app.finance.imports.schemas import DecisionUpdate

    db = db_session
    case = await case_with_rows(
        db,
        owner.id,
        tmp_path,
        monkeypatch,
        closing=-900,
        rows=[purchase("manual"), purchase("dup1", -400), purchase("dup2", -400)],
    )
    await save_decisions(
        db, owner.id, case.batch_id, DecisionUpdate(expected_version=1, decisions=[case.decision])
    )
    await configure(db, owner.id, case)
    job = await queue(db, owner.id, case)
    await process_auto_post(db, job.id)
    rows = await list_rows(
        db, owner.id, case.batch_id, source_id=case.source_id, offset=0, limit=10
    )
    assert [row.auto_post_reason for row in rows.items] == [
        "manual_decision",
        "possible_duplicate",
        "possible_duplicate",
    ]
    group = (await db.scalars(select(ImportGroup))).one()
    assert group.id == case.decision.group_id and group.state == "ready"
    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 0


async def test_opt_in_does_not_scan_old_imports_and_disabling_cancels_queued_work(
    db_session, owner, tmp_path, monkeypatch
):
    from app.finance.imports.auto_post import (
        capture_auto_post_epoch,
        enroll_auto_post,
        list_due_auto_posts,
        process_auto_post,
    )

    db = db_session
    case = await case_with_rows(db, owner.id, tmp_path, monkeypatch)
    await configure(db, owner.id, case, enabled=True)
    assert await list_due_auto_posts(db) == []
    source = await db.get(ImportSource, case.source_id)
    await capture_auto_post_epoch(db, owner.id, source)
    await enroll_auto_post(db, owner.id, source)
    await db.flush()
    [job] = await list_due_auto_posts(db)
    await configure(db, owner.id, case, enabled=False)
    await process_auto_post(db, job)
    batch = await get_batch(db, owner.id, case.batch_id)
    assert batch.sources[0].auto_post.reason == "settings_changed"
    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 0


async def test_other_owner_cannot_queue_a_statement(db_session, owner, tmp_path, monkeypatch):
    case = await case_with_rows(db_session, owner.id, tmp_path, monkeypatch)
    with pytest.raises(ImportError) as error:
        await queue(db_session, uuid.uuid4(), case)
    assert error.value.code == "import_not_found"


async def test_pending_row_is_not_booked_and_has_a_reason(db_session, owner, tmp_path, monkeypatch):
    from app.finance.imports.auto_post import process_auto_post

    db = db_session
    case = await case_with_rows(
        db,
        owner.id,
        tmp_path,
        monkeypatch,
        rows=[purchase("pending").model_copy(update={"state": "pending"})],
    )
    await configure(db, owner.id, case)
    await process_auto_post(db, (await queue(db, owner.id, case)).id)
    rows = await list_rows(
        db, owner.id, case.batch_id, source_id=case.source_id, offset=0, limit=10
    )
    assert rows.items[0].auto_post_reason == "not_postable"
    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 0


async def test_first_publication_enrolls_new_source_but_not_a_reparse(
    db_session,
    owner,
    tmp_path,
    monkeypatch,
):
    from app.documents.import_storage import store_import_document
    from app.finance.imports.auto_post import list_due_auto_posts
    from app.finance.imports.jobs import claim_import_job, finish_import_job, request_prepare
    from app.finance.imports.models import ImportAutoPostJob
    from app.finance.imports.service import create_batch
    from app.finance.imports.storage import attach_source
    from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

    db = db_session
    old = await case_with_rows(db, owner.id, tmp_path, monkeypatch)
    await configure(db, owner.id, old, enabled=True)
    batch = await create_batch(db, owner.id, "statement")
    document, _ = await store_import_document(
        db,
        owner.id,
        content=text_pdf_bytes("Synthetic new source"),
        filename="new.pdf",
    )
    new = await attach_source(db, owner.id, batch.id, document.id)
    for index in range(2):
        job = await request_prepare(db, owner.id, new.source.id, f"prepare-{index}")
        claim = await claim_import_job(db, job.id, datetime.now(UTC))
        assert await finish_import_job(db, claim, parsed_statement(account_reference=IBAN))
    assert len(await list_due_auto_posts(db)) == 1
    enrolled = (await db.scalars(select(ImportAutoPostJob))).one()
    assert enrolled.source_id == new.source.id
    assert enrolled.revision_id != claim.revision_id


async def test_concurrent_delivery_and_manual_confirmation_preserve_one_posting_per_row(
    db_session,
    test_database,
    owner,
    tmp_path,
    monkeypatch,
):
    from app.finance.imports.auto_post import process_auto_post
    from app.finance.imports.commit import commit_import
    from app.finance.imports.decisions import save_decisions
    from app.finance.imports.preview import prepare_preview
    from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest

    db = db_session
    case = await case_with_rows(
        db,
        owner.id,
        tmp_path,
        monkeypatch,
        closing=-300,
        rows=[purchase("manual", -100, "Pierwszy sklep"), purchase("auto", -200, "Drugi sklep")],
    )
    await configure(db, owner.id, case)
    reviewed = await save_decisions(
        db, owner.id, case.batch_id, DecisionUpdate(expected_version=1, decisions=[case.decision])
    )
    preview = await prepare_preview(
        db,
        owner.id,
        case.batch_id,
        PreviewRequest(expected_version=reviewed.version, group_ids=[case.decision.group_id]),
    )
    request = CommitRequest(preview_id=preview.id, request_hash=preview.request_hash)
    job_id = (await queue(db, owner.id, case)).id
    owner_id, batch_id = owner.id, case.batch_id
    await db.commit()
    session = async_sessionmaker(test_database, expire_on_commit=False)

    async def automatic():
        async with session() as other:
            await process_auto_post(other, job_id)
            await other.commit()

    async def manual():
        async with session() as other:
            try:
                await commit_import(other, owner_id, batch_id, request, "race-manual")
                await other.commit()
            except ImportError as error:
                assert error.code == "preview_stale"

    await asyncio.wait_for(asyncio.gather(automatic(), automatic(), manual()), 30)
    evidence = (await db.scalars(select(ImportEvidence))).all()
    covered = [item.row_id for item in evidence]
    assert covered.count(case.rows[1].id) == 1
    assert covered.count(case.rows[0].id) <= 1


async def test_rollback_after_posting_leaves_queue_recoverable(
    db_session,
    test_database,
    owner,
    tmp_path,
    monkeypatch,
):
    from app.finance.imports.auto_post import list_due_auto_posts, process_auto_post

    db = db_session
    case = await case_with_rows(db, owner.id, tmp_path, monkeypatch)
    await configure(db, owner.id, case)
    job_id = (await queue(db, owner.id, case)).id
    await db.commit()
    session = async_sessionmaker(test_database)
    async with session() as attempt:
        await process_auto_post(attempt, job_id)
        await attempt.rollback()
    assert await list_due_auto_posts(db) == [job_id]
    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 0
    await process_auto_post(db, job_id)
    assert await db.scalar(select(func.count()).select_from(ImportEvidence)) == 1
