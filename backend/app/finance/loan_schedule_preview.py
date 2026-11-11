"""Frozen plan-only previews. Private source integrity and target binding are server-owned."""

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.import_storage import ImportStorageError, read_import_original
from app.documents.models import Document
from app.finance.credit_card_models import CreditCard
from app.finance.dates import _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.contracts import ParsedSchedule
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBatch,
    ImportPreview,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.preview import canonical, digest, record, revision_record
from app.finance.loan_schedule_diff import (
    ScheduleDiff,
    ScheduleState,
    diff_schedule,
    load_schedule_state,
)
from app.finance.loan_schedule_models import LoanScheduleRevision
from app.finance.loan_schedule_schemas import (
    ScheduleActivateRequest,
    SchedulePreviewDTO,
    SchedulePreviewRequest,
)
from app.finance.models import LoanAgreement
from app.finance.queries import lock_accounts


@dataclass
class ScheduleContext:
    today: date
    batch: ImportBatch
    source: ImportSource
    revision: ImportRevision
    rows: list[ImportRow]
    parsed: ParsedSchedule
    state: ScheduleState
    diff: ScheduleDiff
    snapshot: dict[str, Any]


async def _context(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    data: SchedulePreviewRequest,
    *,
    today: date,
) -> ScheduleContext:
    await lock_document_mutations(db, owner)
    batch = await db.scalar(
        select(ImportBatch)
        .where(ImportBatch.id == batch_id, ImportBatch.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    if batch.kind != "loan_schedule":
        raise ImportError("import_kind_mismatch", "To nie jest import harmonogramu.", 422)
    if batch.archived_at is not None:
        raise ImportError("import_archived", "Import jest zarchiwizowany.")
    if batch.version != data.expected_version:
        raise ImportError(
            "import_version_conflict", "Import zmienił się; przygotuj podgląd ponownie."
        )
    source = await db.scalar(
        select(ImportSource)
        .where(
            ImportSource.id == data.source_id,
            ImportSource.batch_id == batch.id,
            ImportSource.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if source is None:
        raise ImportError("source_not_found", "Nie znaleziono źródła.", 404)
    if (
        source.kind != "loan_schedule"
        or source.processing_state != "ready"
        or source.current_revision_id is None
    ):
        raise ImportError("source_not_ready", "Źródło nie jest gotowym harmonogramem.", 422)
    revision = await db.scalar(
        select(ImportRevision)
        .where(
            ImportRevision.id == source.current_revision_id,
            ImportRevision.source_id == source.id,
            ImportRevision.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if revision is None or revision.result is None or revision.error_code is not None:
        raise ImportError("source_not_ready", "Brak poprawnej rewizji źródła.", 422)
    latest = await db.scalar(
        select(ImportRevision)
        .where(ImportRevision.source_id == source.id, ImportRevision.user_id == owner)
        .order_by(ImportRevision.number.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if latest is None or latest.id != revision.id:
        raise ImportError(
            "schedule_reparse_requires_comparison",
            "Nowa rewizja pozostaje kandydatem i wymaga osobnego porównania.",
        )
    try:
        parsed = ParsedSchedule.model_validate(revision.result)
    except ValidationError as error:
        raise ImportError("schedule_invalid", "Niepoprawne dane harmonogramu.", 422) from error
    if (
        source.bank != "velo"
        or parsed.bank != "velo"
        or source.currency != "PLN"
        or source.layout != parsed.layout
        or source.parser_version != parsed.parser_version
    ):
        raise ImportError(
            "schedule_source_mismatch", "Bank, waluta lub układ źródła są niezgodne.", 422
        )
    document = await db.scalar(
        select(Document)
        .where(Document.id == source.document_id, Document.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None or document.archived_at is not None:
        raise ImportError("source_unavailable", "Oryginał źródła jest niedostępny.")
    if revision.source_sha256 != document.sha256_hash:
        raise ImportError("source_integrity_failed", "Rewizja nie odpowiada oryginałowi.")
    try:
        await asyncio.to_thread(read_import_original, document)
    except ImportStorageError as error:
        raise ImportError(
            error.code, "Nie udało się zweryfikować oryginału.", error.http_status
        ) from error
    rows = list(
        (
            await db.scalars(
                select(ImportRow)
                .where(
                    ImportRow.revision_id == revision.id,
                    ImportRow.user_id == owner,
                    ImportRow.source_id == source.id,
                    ImportRow.batch_id == batch.id,
                )
                .order_by(ImportRow.ordinal)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(rows) != len(parsed.rows):
        raise ImportError("schedule_rows_changed", "Wiersze źródła nie odpowiadają rewizji.")
    for ordinal, (stored, value) in enumerate(zip(rows, parsed.rows, strict=True), 1):
        fields = value.model_dump(mode="json")
        hashed = hashlib.sha256(json.dumps(stored.fields, sort_keys=True).encode()).hexdigest()
        if (
            stored.ordinal != ordinal
            or stored.kind != "loan_schedule"
            or stored.source_key != str(value.bank_number)
            or stored.fields != fields
            or stored.row_hash != hashed
        ):
            raise ImportError("schedule_rows_changed", "Wiersze źródła nie odpowiadają rewizji.")
    loan = None
    if data.target.loan_id is not None:
        loan = await db.scalar(
            select(LoanAgreement)
            .where(LoanAgreement.id == data.target.loan_id, LoanAgreement.user_id == owner)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if loan is None:
            raise ImportError("loan_not_found", "Nie znaleziono kredytu.", 404)
        if not loan.is_active:
            raise ImportError("loan_inactive", "Kredyt jest nieaktywny.", 422)
        account_ids = {loan.account_id, loan.payment_account_id}
    else:
        assert data.target.new_loan is not None
        account_ids = {data.target.new_loan.account_id, data.target.new_loan.payment_account_id}
    if len(account_ids) != 2:
        raise ImportError("loan_accounts_invalid", "Kredyt wymaga dwóch różnych kont PLN.", 422)
    accounts = await lock_accounts(db, owner, account_ids, exclusive=True)
    if set(accounts) != account_ids:
        raise ImportError("account_not_found", "Nie znaleziono kont kredytu.", 404)
    if any(
        not a.is_active or a.currency != "PLN" or a.type == "credit_card" for a in accounts.values()
    ):
        raise ImportError(
            "loan_accounts_invalid", "Konta kredytu muszą być aktywne, PLN i nie być kartą.", 422
        )
    if await db.scalar(
        select(CreditCard.id).where(CreditCard.account_id.in_(account_ids)).limit(1)
    ):
        raise ImportError(
            "loan_accounts_invalid", "Konto z profilem karty nie może być kontem tego kredytu.", 422
        )
    if loan is None:
        assert data.target.new_loan is not None
        if await db.scalar(
            select(LoanAgreement.id)
            .where(LoanAgreement.account_id == data.target.new_loan.account_id)
            .limit(1)
        ):
            raise ImportError("loan_account_conflict", "Konto długu ma już umowę kredytu.")
        state = ScheduleState(
            uuid.UUID(int=0),
            None,
            (),
            (),
            digest({"new_loan": data.target.new_loan.model_dump(mode="json")}),
        )
    else:
        loaded = await load_schedule_state(db, owner, loan.id, lock=True)
        assert loaded is not None
        state = loaded
    # A source revision cannot silently create a second plan on a new intent.
    if await db.scalar(
        select(LoanScheduleRevision.id)
        .where(
            LoanScheduleRevision.source_revision_id == revision.id,
            LoanScheduleRevision.user_id == owner,
        )
        .limit(1)
    ):
        raise ImportError(
            "schedule_source_already_activated",
            "To źródło ma już zatwierdzoną wersję; zobacz historię.",
        )
    required = {f"schedule_target:{source.id}"}
    if required - set(data.acknowledgements):
        raise ImportError(
            "import_acknowledgement_required",
            "Wymagane potwierdzenia: " + ", ".join(sorted(required)),
        )
    diff = diff_schedule(state, parsed, today=today)
    snapshot = canonical(
        {
            "batch": record(batch),
            "source": record(source),
            "revision": revision_record(revision),
            "document": record(document),
            "rows": [record(r) for r in rows],
            "loan": record(loan) if loan else None,
            "accounts": [record(accounts[i]) for i in sorted(accounts, key=str)],
            "loan_fingerprint": state.fingerprint,
        }
    )
    return ScheduleContext(today, batch, source, revision, rows, parsed, state, diff, snapshot)


def _payload(
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    data: SchedulePreviewRequest,
    today: date,
    context: ScheduleContext,
) -> dict[str, Any]:
    return canonical(
        {
            "kind": "loan_schedule",
            "owner_id": str(owner),
            "batch_id": str(batch_id),
            "request": data.model_dump(mode="json"),
            "today": today.isoformat(),
            "snapshot": context.snapshot,
            "diff": TypeAdapter(ScheduleDiff).dump_python(context.diff, mode="json"),
            "ledger_effect": "none",
        }
    )


async def prepare_schedule_preview(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: SchedulePreviewRequest
) -> SchedulePreviewDTO:
    today = _local_today()
    context = await _context(db, owner, batch_id, data, today=today)
    payload = _payload(owner, batch_id, data, today, context)
    preview = ImportPreview(
        user_id=owner,
        batch_id=batch_id,
        version=context.batch.version,
        request_hash=digest(payload),
        payload=payload,
    )
    db.add(preview)
    await db.flush()
    await log_event(
        db,
        owner,
        "loan_schedule_preview",
        str(preview.id),
        "prepare_preview",
        new_state={"request_hash": preview.request_hash, "ledger_effect": "none"},
    )
    return SchedulePreviewDTO(
        id=preview.id,
        batch_id=batch_id,
        version=preview.version,
        request_hash=preview.request_hash,
        source_revision_id=context.revision.id,
        target=data.target,
        cutover_date=context.diff.cutover_date,
        loan_fingerprint=context.state.fingerprint,
        diff=context.diff,
    )


async def load_confirmed_schedule(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: ScheduleActivateRequest
) -> tuple[ScheduleContext, SchedulePreviewRequest]:
    preview = await db.scalar(
        select(ImportPreview)
        .where(
            ImportPreview.id == data.preview_id,
            ImportPreview.batch_id == batch_id,
            ImportPreview.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if preview is None:
        raise ImportError("preview_not_found", "Nie znaleziono podglądu tego importu.", 404)
    payload = canonical(preview.payload)
    if (
        data.request_hash != preview.request_hash
        or digest(payload) != preview.request_hash
        or payload.get("kind") != "loan_schedule"
        or payload.get("owner_id") != str(owner)
        or payload.get("batch_id") != str(batch_id)
    ):
        raise ImportError("preview_stale", "Podgląd jest niespójny.")
    today = _local_today()
    if payload.get("today") != today.isoformat():
        raise ImportError("preview_stale", "Zmienił się dzień aktywacji; przygotuj nowy podgląd.")
    try:
        request = SchedulePreviewRequest.model_validate(payload["request"])
        context = await _context(db, owner, batch_id, request, today=today)
    except (ImportError, ValidationError, KeyError) as error:
        raise ImportError(
            "preview_stale", "Źródło lub kredyt zmieniły się; przygotuj nowy podgląd."
        ) from error
    if (
        preview.version != context.batch.version
        or _payload(owner, batch_id, request, today, context) != payload
    ):
        raise ImportError(
            "preview_stale", "Dane podglądu zmieniły się; wymagane ponowne potwierdzenie."
        )
    if context.diff.conflicts:
        raise ImportError(
            "schedule_conflicts", "Harmonogram ma nierozwiązane konflikty; aktywacja zablokowana."
        )
    return context, request
