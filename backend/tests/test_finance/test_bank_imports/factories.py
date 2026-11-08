import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.documents.models import Document
from app.finance.entities import create_account
from app.finance.imports.contracts import ParsedStatement
from app.finance.imports.models import ImportRevision, ImportRow, ImportSource
from app.finance.imports.service import create_batch
from app.finance.schemas import AccountCreate, PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction

HISTORY_TABLES = {
    "accounts",
    "financial_transactions",
    "postings",
    "actual_import_mappings",
    "loan_agreements",
    "loan_installments",
    "loan_payment_links",
    "credit_cards",
}


async def ledger_snapshot(db: AsyncSession) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in sorted(HISTORY_TABLES):
        table = Base.metadata.tables[name]
        rows = [
            json.dumps(dict(row), default=str, sort_keys=True)
            for row in (await db.execute(select(table))).mappings()
        ]
        result[name] = hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()
    return result


async def ready_statement(
    db: AsyncSession, owner: uuid.UUID, payload: ParsedStatement
) -> uuid.UUID:
    batch = await create_batch(db, owner, "statement")
    raw = b"synthetic-source-not-a-real-customer-statement"
    document = Document(
        user_id=owner,
        filename=uuid.uuid4().hex + ".pdf",
        original_name="synthetic.pdf",
        mime_type="application/pdf",
        sha256_hash=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        storage_path="/test-fixture/synthetic.pdf",
        status="done",
        processing_method="bank_import",
    )
    db.add(document)
    await db.flush()
    source = ImportSource(
        user_id=owner,
        batch_id=batch.id,
        document_id=document.id,
        kind="statement",
        processing_state="ready",
        validation_state="passed",
        bank=payload.bank,
        layout=payload.layout,
        parser_version=payload.parser_version,
    )
    db.add(source)
    await db.flush()
    revision = ImportRevision(
        user_id=owner,
        batch_id=batch.id,
        source_id=source.id,
        number=1,
        source_sha256=document.sha256_hash,
        parser_version=payload.parser_version,
        result=payload.model_dump(mode="json"),
        checks=[check.model_dump(mode="json") for check in payload.checks],
        warnings=payload.warnings,
    )
    db.add(revision)
    await db.flush()
    source.current_revision_id = revision.id
    for ordinal, row in enumerate(payload.rows, 1):
        fields = row.model_dump(mode="json")
        db.add(
            ImportRow(
                user_id=owner,
                batch_id=batch.id,
                source_id=source.id,
                revision_id=revision.id,
                kind="statement",
                ordinal=ordinal,
                source_key=row.key,
                row_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
                fields=fields,
            )
        )
    await db.flush()
    return batch.id


async def seed_legacy_transfer(db: AsyncSession, owner_id: uuid.UUID) -> None:
    source = await create_account(
        db, owner_id, AccountCreate(name="Synthetic source", type="checking")
    )
    destination = await create_account(
        db, owner_id, AccountCreate(name="Synthetic wallet", type="cash")
    )
    await create_transaction(
        db,
        owner_id,
        TransactionCreate(
            transaction_date="2026-01-03",
            description="Synthetic preexisting transfer",
            type="transfer",
            postings=[
                PostingCreate(
                    account_id=source.id, source_amount=100, base_amount_pln=100, direction="debit"
                ),
                PostingCreate(
                    account_id=destination.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit",
                ),
            ],
        ),
    )
