"""Durable, owner-authorized subset of the ordinary statement confirmation flow."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.documents.models import Document
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.auto_policy import classify
from app.finance.imports.commit import commit_import
from app.finance.imports.contracts import ParsedStatement, StatementRow
from app.finance.imports.decisions import load_batch, normalized_reference, save_decisions
from app.finance.imports.errors import ImportError
from app.finance.imports.matching import candidate_postings
from app.finance.imports.models import (
    ImportAutoPostJob,
    ImportAutoPostSettings,
    ImportEvidence,
    ImportGroupRow,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.preview import prepare_preview, statement_opening_gap
from app.finance.imports.schemas import (
    AutoPostRequest,
    AutoPostSettings,
    CommitRequest,
    DecisionUpdate,
    ImportDecisionInput,
    PreviewRequest,
)
from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.queries import lock_accounts

_INFORMATIONAL_WARNINGS = frozenset(
    {
        "timestamps_without_timezone",
        "order_from_balances",
        "opening_derived",
        "no_posted_movements",
        "source_has_no_row_balances",
    }
)


async def _policy(db: AsyncSession, owner: uuid.UUID) -> ImportAutoPostSettings | None:
    return await db.scalar(
        select(ImportAutoPostSettings)
        .where(ImportAutoPostSettings.user_id == owner)
        .execution_options(populate_existing=True)
    )


async def get_auto_post_settings(db: AsyncSession, owner: uuid.UUID) -> AutoPostSettings:
    policy = await _policy(db, owner)
    return AutoPostSettings.model_validate(policy) if policy else AutoPostSettings()


async def set_auto_post_settings(
    db: AsyncSession, owner: uuid.UUID, data: AutoPostSettings
) -> AutoPostSettings:
    await lock_document_mutations(db, owner)
    for kind, category_id in (
        ("expense", data.expense_category_id),
        ("income", data.income_category_id),
    ):
        if category_id is not None and not await _valid_category(db, owner, category_id, kind):
            raise ImportError("category_unavailable", "Wybierz aktywną kategorię danego typu.", 422)
    policy = await _policy(db, owner)
    if policy is not None and AutoPostSettings.model_validate(policy) == data:
        return data
    if policy is None:
        policy = ImportAutoPostSettings(user_id=owner, epoch=1)
        db.add(policy)
    else:
        policy.epoch += 1
    policy.enabled = data.enabled
    policy.expense_category_id = data.expense_category_id
    policy.income_category_id = data.income_category_id
    await db.flush()
    await log_event(
        db,
        owner,
        "bank_import_auto_post_settings",
        str(policy.id),
        "change_auto_post_settings",
        new_state=data.model_dump(mode="json") | {"epoch": policy.epoch},
    )
    return data


async def _valid_category(
    db: AsyncSession, owner: uuid.UUID, category_id: uuid.UUID, kind: str
) -> bool:
    return (
        await db.scalar(
            select(Category.id)
            .where(
                Category.id == category_id,
                Category.user_id == owner,
                Category.is_active.is_(True),
                Category.type == kind,
            )
            .with_for_update()
        )
    ) is not None


async def capture_auto_post_epoch(db: AsyncSession, owner: uuid.UUID, source: ImportSource) -> None:
    if source.kind == "statement":
        policy = await _policy(db, owner)
        source.auto_post_epoch = policy.epoch if policy and policy.enabled else None


async def enroll_auto_post(db: AsyncSession, owner: uuid.UUID, source: ImportSource) -> None:
    if source.kind != "statement" or source.auto_post_epoch is None:
        return
    assert source.current_revision_id is not None
    db.add(
        ImportAutoPostJob(
            user_id=owner,
            source_id=source.id,
            revision_id=source.current_revision_id,
            policy_epoch=source.auto_post_epoch,
        )
    )


async def queue_manual_auto_post(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    source_id: uuid.UUID,
    request: AutoPostRequest,
) -> ImportAutoPostJob:
    await lock_document_mutations(db, owner)
    await load_batch(db, owner, batch_id, locked=True)
    source = await db.scalar(
        select(ImportSource)
        .where(
            ImportSource.id == source_id,
            ImportSource.user_id == owner,
            ImportSource.batch_id == batch_id,
        )
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise ImportError("source_not_found", "Nie znaleziono źródła.", 404)
    if source.current_revision_id != request.revision_id or source.processing_state != "ready":
        raise ImportError(
            "source_revision_conflict", "Odczyt źródła zmienił się lub nie jest gotowy."
        )
    if request.account_id is not None and not await db.scalar(
        select(Account.id).where(
            Account.user_id == owner,
            Account.id == request.account_id,
            Account.is_active.is_(True),
        )
    ):
        raise ImportError("account_not_found", "Nie znaleziono aktywnego rachunku.", 404)
    job = await db.scalar(
        select(ImportAutoPostJob)
        .where(
            ImportAutoPostJob.user_id == owner,
            ImportAutoPostJob.revision_id == request.revision_id,
        )
        .execution_options(populate_existing=True)
    )
    if job is not None and job.manual:
        if job.account_id != request.account_id:
            raise ImportError(
                "auto_post_already_requested", "Dla tego odczytu zlecono już księgowanie."
            )
        return job
    if job is None:
        job = ImportAutoPostJob(
            user_id=owner,
            source_id=source_id,
            revision_id=request.revision_id,
        )
        db.add(job)
    policy = await _policy(db, owner)
    job.manual = True
    job.policy_epoch = policy.epoch if policy else None
    job.account_id = request.account_id
    job.state = "queued"
    job.attempts = 0
    job.next_attempt_at = None
    job.reason = None
    job.row_reasons = {}
    await db.flush()
    await log_event(
        db,
        owner,
        "bank_import_source",
        str(source_id),
        "request_auto_post",
        new_state={"job_id": str(job.id), "revision_id": str(request.revision_id)},
    )
    return job


async def list_due_auto_posts(db: AsyncSession) -> list[uuid.UUID]:
    return list(
        (
            await db.scalars(
                select(ImportAutoPostJob.id)
                .where(
                    ImportAutoPostJob.state == "queued",
                    or_(
                        ImportAutoPostJob.next_attempt_at.is_(None),
                        ImportAutoPostJob.next_attempt_at <= datetime.now(UTC),
                    ),
                )
                .order_by(ImportAutoPostJob.created_at, ImportAutoPostJob.id)
                .limit(settings.FINANCE_IMPORT_DISPATCH_BATCH)
            )
        ).all()
    )


async def _job_for_update(db: AsyncSession, job_id: uuid.UUID) -> ImportAutoPostJob | None:
    owner = await db.scalar(select(ImportAutoPostJob.user_id).where(ImportAutoPostJob.id == job_id))
    if owner is None:
        return None
    await lock_document_mutations(db, owner)
    return await db.scalar(
        select(ImportAutoPostJob)
        .where(
            ImportAutoPostJob.id == job_id,
            ImportAutoPostJob.user_id == owner,
            ImportAutoPostJob.state == "queued",
            or_(
                ImportAutoPostJob.next_attempt_at.is_(None),
                ImportAutoPostJob.next_attempt_at <= datetime.now(UTC),
            ),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _finish(
    db: AsyncSession,
    job: ImportAutoPostJob,
    *,
    reason: str | None = None,
    posted: int = 0,
    row_reasons: dict[str, str] | None = None,
) -> None:
    job.state = "done"
    job.next_attempt_at = None
    job.reason = reason
    job.posted_count += posted
    job.row_reasons = row_reasons or {}
    await log_event(
        db,
        job.user_id,
        "bank_import_source",
        str(job.source_id),
        "finish_auto_post",
        performed_by="system",
        new_state={
            "job_id": str(job.id),
            "trigger": "manual" if job.manual else "opt_in",
            "reason": reason,
            "posted_count": posted,
            "review_count": len(job.row_reasons),
        },
    )


async def record_auto_post_failure(db: AsyncSession, job_id: uuid.UUID) -> None:
    job = await _job_for_update(db, job_id)
    if job is None:
        return
    job.attempts += 1
    if job.attempts >= settings.FINANCE_IMPORT_MAX_ATTEMPTS:
        await _finish(db, job, reason="processing_failed")
    else:
        job.next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=settings.FINANCE_IMPORT_RETRY_SECONDS * 2 ** (job.attempts - 1)
        )


async def _source_account(
    db: AsyncSession, job: ImportAutoPostJob, statement: ParsedStatement
) -> Account | None:
    accounts = (
        await db.scalars(
            select(Account)
            .where(
                Account.user_id == job.user_id,
                Account.is_active.is_(True),
                Account.type.in_(["checking", "savings"]),
                Account.currency == statement.currency,
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    reference = normalized_reference(statement.account_reference or "")
    matches = [
        account
        for account in accounts
        if (job.account_id is None or account.id == job.account_id)
        and statement.bank
        in "".join(ch for ch in (account.bank_name or "").lower() if "a" <= ch <= "z")
        and (
            (reference and normalized_reference(account.iban or "") == reference)
            or (not reference and job.manual and account.id == job.account_id)
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _source_duplicate(row: StatementRow, other: StatementRow) -> bool:
    if row.bank_reference and row.bank_reference == other.bank_reference:
        return True
    return (
        row.booking_date is not None
        and other.booking_date is not None
        and abs((row.booking_date - other.booking_date).days) <= 3
        and (
            row.amount == other.amount
            or " ".join(row.description.casefold().split())
            == " ".join(other.description.casefold().split())
        )
    )


async def _pending_duplicate(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, row: StatementRow
) -> bool:
    assert row.booking_date is not None
    return (
        await db.scalar(
            select(Posting.id)
            .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
            .where(
                FinancialTransaction.user_id == owner,
                FinancialTransaction.is_pending.is_(True),
                FinancialTransaction.date.between(
                    row.booking_date - timedelta(days=3), row.booking_date + timedelta(days=3)
                ),
                Posting.account_id == account_id,
                Posting.source_amount == abs(row.amount),
                Posting.source_currency == row.currency,
            )
            .limit(1)
        )
    ) is not None


async def process_auto_post(db: AsyncSession, job_id: uuid.UUID) -> None:
    job = await _job_for_update(db, job_id)
    if job is None:
        return
    policy = await _policy(db, job.user_id)
    if (policy.epoch if policy else None) != job.policy_epoch or (
        not job.manual and (policy is None or not policy.enabled)
    ):
        await _finish(db, job, reason="settings_changed")
        return
    source = await db.get(ImportSource, job.source_id, populate_existing=True)
    revision = await db.get(ImportRevision, job.revision_id, populate_existing=True)
    assert source is not None and revision is not None
    document = await db.get(Document, source.document_id, populate_existing=True)
    if (
        source.kind != "statement"
        or source.current_revision_id != job.revision_id
        or source.processing_state != "ready"
        or source.validation_state == "blocked"
        or document is None
        or document.archived_at is not None
        or document.sha256_hash != revision.source_sha256
        or not revision.result
        or set(revision.warnings) - _INFORMATIONAL_WARNINGS
        or await db.scalar(
            select(ImportRevision.id)
            .where(
                ImportRevision.source_id == source.id,
                ImportRevision.user_id == job.user_id,
                ImportRevision.number > revision.number,
            )
            .limit(1)
        )
    ):
        await _finish(db, job, reason="source_validation_blocked")
        return
    try:
        batch = await load_batch(db, job.user_id, source.batch_id, locked=True)
    except ImportError as error:
        await _finish(db, job, reason=error.code)
        return
    statement = ParsedStatement.model_validate(revision.result)
    if statement.layout == "velo_card_v1" or statement.card_header is not None:
        await _finish(db, job, reason="card_statement_review")
        return
    if any(check.required and check.result != "passed" for check in statement.checks):
        await _finish(db, job, reason="source_validation_blocked")
        return
    if len(statement.rows) > settings.FINANCE_IMPORT_AUTO_POST_MAX_ROWS:
        await _finish(db, job, reason="too_many_rows")
        return
    account = await _source_account(db, job, statement)
    if account is None:
        await _finish(db, job, reason="account_unresolved")
        return
    await lock_accounts(db, job.user_id, {account.id}, exclusive=True)
    mapped = await _source_account(db, job, statement)
    if mapped is None or mapped.id != account.id:
        await _finish(db, job, reason="account_unresolved")
        return
    if statement.opening is None or await statement_opening_gap(
        db, job.user_id, account.id, statement.period_start, statement.opening
    ):
        await _finish(db, job, reason="opening_gap")
        return
    rows = (
        await db.execute(
            select(ImportRow, ImportGroupRow.id, ImportEvidence.id)
            .outerjoin(ImportGroupRow, ImportGroupRow.row_id == ImportRow.id)
            .outerjoin(ImportEvidence, ImportEvidence.row_id == ImportRow.id)
            .where(ImportRow.user_id == job.user_id, ImportRow.revision_id == job.revision_id)
            .order_by(ImportRow.ordinal)
        )
    ).all()
    items = [
        (row, group_id, evidence_id, StatementRow.model_validate(row.fields))
        for row, group_id, evidence_id in rows
    ]
    source_rows = {row.id: value for row, _, _, value in items if value.state == "posted"}
    category_ids = {}
    if policy:
        for category_kind, category_id in (
            ("expense", policy.expense_category_id),
            ("income", policy.income_category_id),
        ):
            if category_id and await _valid_category(db, job.user_id, category_id, category_kind):
                category_ids[category_kind] = category_id
    row_reasons: dict[str, str] = {}
    decisions: list[ImportDecisionInput] = []
    for row, group_id, evidence_id, value in items:
        if evidence_id is not None:
            continue
        kind, reason = classify(statement.bank, value)
        if group_id and reason != "not_postable":
            reason = "manual_decision"
        elif kind:
            if (
                any(
                    other_id != row.id and _source_duplicate(value, other)
                    for other_id, other in source_rows.items()
                )
                or await candidate_postings(db, job.user_id, row.id, account.id)
                or await _pending_duplicate(db, job.user_id, account.id, value)
            ):
                reason = "possible_duplicate"
            elif kind not in category_ids:
                reason = "category_unavailable"
            elif value.currency != "PLN":
                # Keep external quote I/O out of the owner's ledger lock.
                reason = "fx_review"
            elif not value.description.strip() or (
                value.booking_date is None
                or not statement.period_start <= value.booking_date <= statement.period_end
            ):
                reason = "movement_unclear"
            else:
                decisions.append(
                    ImportDecisionInput(
                        group_id=uuid.uuid4(),
                        row_ids=[row.id],
                        action="create",
                        kind=kind,
                        account_id=account.id,
                        category_id=category_ids[kind],
                    )
                )
        if reason:
            row_reasons[str(row.id)] = reason
    if not decisions:
        await _finish(db, job, row_reasons=row_reasons)
        return
    try:
        async with db.begin_nested():
            reviewed = await save_decisions(
                db,
                job.user_id,
                batch.id,
                DecisionUpdate(
                    expected_version=batch.version,
                    decisions=decisions,
                ),
            )
            preview = await prepare_preview(
                db,
                job.user_id,
                batch.id,
                PreviewRequest(
                    expected_version=reviewed.version,
                    group_ids=[item.group_id for item in decisions],
                ),
            )
            result = await commit_import(
                db,
                job.user_id,
                batch.id,
                CommitRequest(preview_id=preview.id, request_hash=preview.request_hash),
                f"auto-post:{job.id}:{reviewed.version}",
            )
    except ImportError as error:
        await _finish(db, job, reason=error.code, row_reasons=row_reasons)
        return
    await _finish(db, job, posted=len(result.transaction_ids), row_reasons=row_reasons)
