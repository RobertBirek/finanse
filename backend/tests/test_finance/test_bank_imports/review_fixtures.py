import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents import service as documents
from app.documents.models import Document
from app.finance.entities import create_account, create_category
from app.finance.imports.contracts import ParsedStatement
from app.finance.imports.models import ImportRevision, ImportRow, ImportSource
from app.finance.imports.schemas import ImportDecisionInput
from app.finance.models import Account, Category
from app.finance.schemas import AccountCreate, CategoryCreate
from tests.test_finance.test_bank_imports.factories import ready_statement, text_pdf_bytes
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement


@dataclass
class ReviewCase:
    batch_id: uuid.UUID
    source_id: uuid.UUID
    rows: list[ImportRow]
    account: Account
    category: Category
    decision: ImportDecisionInput


async def review_case(
    db: AsyncSession, owner: uuid.UUID, directory: Path, payload: ParsedStatement | None = None
) -> ReviewCase:
    payload = payload or parsed_statement(account_reference=None)
    batch_id = await ready_statement(db, owner, payload)
    source = await db.scalar(select(ImportSource).where(ImportSource.batch_id == batch_id))
    assert source is not None
    document = await db.get(Document, source.document_id)
    revision = await db.get(ImportRevision, source.current_revision_id)
    assert document is not None and revision is not None
    content = text_pdf_bytes("Synthetic already validated bank source")
    sha = hashlib.sha256(content).hexdigest()
    path = directory / documents._storage_path(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    document.sha256_hash = sha
    document.size_bytes = len(content)
    document.storage_path = documents._storage_path(sha)
    revision.source_sha256 = sha
    account = await create_account(
        db,
        owner,
        AccountCreate(name="Synthetic owned account", type="checking", currency=payload.currency),
    )
    category = await create_category(
        db, owner, CategoryCreate(name="Synthetic expense", type="expense")
    )
    rows = list(
        (
            await db.scalars(
                select(ImportRow).where(ImportRow.batch_id == batch_id).order_by(ImportRow.ordinal)
            )
        ).all()
    )
    decision = ImportDecisionInput(
        group_id=uuid.uuid4(),
        row_ids=[rows[0].id],
        action="create",
        kind="expense",
        account_id=account.id,
        category_id=category.id,
    )
    await db.flush()
    return ReviewCase(batch_id, source.id, rows, account, category, decision)


async def additional_source(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    directory: Path,
    payload: ParsedStatement,
) -> tuple[ImportSource, list[ImportRow]]:
    content = text_pdf_bytes("Synthetic additional " + uuid.uuid4().hex)
    sha = hashlib.sha256(content).hexdigest()
    path = directory / documents._storage_path(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    document = Document(
        user_id=owner,
        filename="synthetic.pdf",
        original_name="synthetic.pdf",
        mime_type="application/pdf",
        size_bytes=len(content),
        sha256_hash=sha,
        storage_path=documents._storage_path(sha),
        processing_method="bank_import",
        status="done",
    )
    db.add(document)
    await db.flush()
    source = ImportSource(
        user_id=owner,
        batch_id=batch_id,
        document_id=document.id,
        kind="statement",
        bank=payload.bank,
        currency=payload.currency,
        layout=payload.layout,
        parser_version=payload.parser_version,
        processing_state="ready",
        validation_state="passed",
    )
    db.add(source)
    await db.flush()
    revision = ImportRevision(
        user_id=owner,
        batch_id=batch_id,
        source_id=source.id,
        number=1,
        source_sha256=sha,
        parser_version=payload.parser_version,
        result=payload.model_dump(mode="json"),
        checks=[check.model_dump(mode="json") for check in payload.checks],
        warnings=payload.warnings,
    )
    db.add(revision)
    await db.flush()
    source.current_revision_id = revision.id
    rows = []
    for ordinal, row in enumerate(payload.rows, 1):
        fields = row.model_dump(mode="json")
        value = ImportRow(
            user_id=owner,
            batch_id=batch_id,
            source_id=source.id,
            revision_id=revision.id,
            kind="statement",
            ordinal=ordinal,
            source_key=row.key,
            row_hash=hashlib.sha256(str(fields).encode()).hexdigest(),
            fields=fields,
        )
        db.add(value)
        rows.append(value)
    await db.flush()
    return source, rows
