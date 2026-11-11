"""Real synthetic PDF, source rows and an existing loan; never customer data."""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service as documents
from app.documents.models import Document
from app.finance.imports.contracts import ParsedSchedule
from app.finance.imports.models import ImportBatch, ImportRevision, ImportRow, ImportSource
from app.finance.loan_schedule_schemas import SchedulePreviewRequest, ScheduleTarget
from app.finance.models import LoanAgreement, LoanInstallment
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes
from tests.test_finance.test_loan_schedule_import.factories import legacy_loan
from tests.test_finance.test_loan_schedule_import.test_parser import HEADER, ROW1, ROW2, ROW3, parse


@dataclass
class ScheduleCase:
    batch: ImportBatch
    source: ImportSource
    revision: ImportRevision
    rows: list[ImportRow]
    document: Document
    loan: LoanAgreement
    installment: LoanInstallment
    parsed: ParsedSchedule
    request: SchedulePreviewRequest


async def schedule_case(
    db: AsyncSession, owner, tmp_path, monkeypatch, *, pdf_text: str | None = None
) -> ScheduleCase:
    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    text = pdf_text if pdf_text is not None else HEADER + ROW1 + ROW2 + ROW3 + "Strona 1 z 1"
    content = text_pdf_bytes(text)
    parsed = parse(text, pdf=True)
    sha = hashlib.sha256(content).hexdigest()
    relative = documents._storage_path(sha)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    document = Document(
        user_id=owner,
        filename="synthetic-schedule.pdf",
        original_name="synthetic-schedule.pdf",
        mime_type="application/pdf",
        sha256_hash=sha,
        size_bytes=len(content),
        storage_path=relative,
        status="done",
        processing_method="bank_import",
    )
    batch = ImportBatch(user_id=owner, kind="loan_schedule")
    db.add_all([document, batch])
    await db.flush()
    source = ImportSource(
        user_id=owner,
        batch_id=batch.id,
        document_id=document.id,
        kind="loan_schedule",
        bank="velo",
        layout=parsed.layout,
        parser_version=parsed.parser_version,
        currency="PLN",
        account_reference=parsed.loan_reference,
        processing_state="ready",
        validation_state="passed",
    )
    db.add(source)
    await db.flush()
    revision = ImportRevision(
        user_id=owner,
        batch_id=batch.id,
        source_id=source.id,
        number=1,
        source_sha256=sha,
        parser_version=parsed.parser_version,
        result=parsed.model_dump(mode="json"),
        checks=[c.model_dump(mode="json") for c in parsed.checks],
    )
    db.add(revision)
    await db.flush()
    source.current_revision_id = revision.id
    rows = []
    for ordinal, row in enumerate(parsed.rows, 1):
        fields = row.model_dump(mode="json")
        record = ImportRow(
            user_id=owner,
            batch_id=batch.id,
            source_id=source.id,
            revision_id=revision.id,
            kind="loan_schedule",
            ordinal=ordinal,
            source_key=str(row.bank_number),
            row_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
            fields=fields,
        )
        db.add(record)
        rows.append(record)
    loan, item, _receipt = await legacy_loan(db, owner)
    first = parsed.rows[0]
    item.due_date = first.due_date
    item.principal_pln = first.principal
    item.interest_pln = first.interest
    await db.flush()
    request = SchedulePreviewRequest(
        expected_version=batch.version,
        source_id=source.id,
        target=ScheduleTarget(loan_id=loan.id),
        acknowledgements=[f"schedule_target:{source.id}"],
    )
    return ScheduleCase(batch, source, revision, rows, document, loan, item, parsed, request)


async def confirmed_case(db, owner, tmp_path, monkeypatch):
    from app.finance.loan_schedule_preview import prepare_schedule_preview
    from app.finance.loan_schedule_schemas import ScheduleActivateRequest

    case = await schedule_case(db, owner, tmp_path, monkeypatch)
    preview = await prepare_schedule_preview(db, owner, case.batch.id, case.request)
    return (
        case,
        preview,
        ScheduleActivateRequest(preview_id=preview.id, request_hash=preview.request_hash),
    )
