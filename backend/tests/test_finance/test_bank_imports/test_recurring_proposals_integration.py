"""PostgreSQL coverage for read-only recurring-import suggestions."""

import hashlib
import json
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.models import Document
from app.finance.entities import create_account, create_category
from app.finance.imports.contracts import StatementRow
from app.finance.imports.models import (
    ImportBankIdentity,
    ImportBatch,
    ImportEvidence,
    ImportGroup,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.recurring_proposals import propose_recurring_expense
from app.finance.models import (
    FinanceCommandReceipt,
    FinancialTransaction,
    Posting,
    ScheduledFinanceItem,
)
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _counts(db: AsyncSession) -> tuple[int, int, int, int]:
    """The proposal read must not create ledger, evidence, or schedule records."""
    return tuple(
        (await db.scalar(select(func.count()).select_from(model))) or 0
        for model in (FinancialTransaction, Posting, ImportEvidence, ScheduledFinanceItem)
    )


async def _statement_source(
    db: AsyncSession,
    owner: uuid.UUID,
    batch: ImportBatch,
    *,
    bank: str = "velo",
    account_reference: str = "PL61109010140000071219812874",
    booking_date: date,
    reference: str,
    ordinal: int,
) -> tuple[ImportSource, ImportRow]:
    """Persist a complete, current synthetic statement source and its posted expense row."""
    raw = f"synthetic-recurring-{reference}".encode()
    document = Document(
        user_id=owner,
        filename=f"{reference}.pdf",
        original_name=f"{reference}.pdf",
        mime_type="application/pdf",
        sha256_hash=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        storage_path=f"/test-fixture/{reference}.pdf",
        status="done",
        processing_method="bank_import",
    )
    db.add(document)
    await db.flush()
    row_value = StatementRow.model_validate(
        {
            "key": f"page-1-line-{ordinal}",
            "position": {"page": 1, "line": ordinal, "section": None},
            "booking_date": booking_date.isoformat(),
            "operation_date": None,
            "started_at": None,
            "completed_at": None,
            "description": "Synthetic streaming subscription",
            "amount": -4900,
            "fee": 0,
            "currency": "PLN",
            "state": "posted",
            "balance_after": None,
            "bank_reference": reference,
            "raw": {"synthetic": "only"},
        }
    )
    source = ImportSource(
        user_id=owner,
        batch_id=batch.id,
        document_id=document.id,
        kind="statement",
        bank=bank,
        account_reference=account_reference,
        currency="PLN",
        layout="velo_account_v1",
        parser_version="synthetic-v1",
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
        source_sha256=document.sha256_hash,
        parser_version="synthetic-v1",
        result={"account_reference": account_reference},
        checks=[],
        warnings=[],
    )
    db.add(revision)
    await db.flush()
    source.current_revision_id = revision.id
    fields = row_value.model_dump(mode="json")
    row = ImportRow(
        user_id=owner,
        batch_id=batch.id,
        source_id=source.id,
        revision_id=revision.id,
        kind="statement",
        ordinal=1,
        source_key=row_value.key,
        row_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
        fields=fields,
    )
    db.add(row)
    await db.flush()
    return source, row


async def _recurring_case(
    db: AsyncSession, owner: uuid.UUID, *, history_reference: str = "stream-2026-02"
) -> tuple[ImportBatch, uuid.UUID, ImportRow]:
    """Seed three complete monthly observations, with two committed history rows."""
    account = await create_account(
        db, owner, AccountCreate(name="Synthetic Velo", type="checking", currency="PLN")
    )
    account.bank_name = "Velo Bank"
    account.iban = "PL61109010140000071219812874"
    category = await create_category(
        db, owner, CategoryCreate(name="Synthetic subscriptions", type="expense")
    )
    batch = ImportBatch(user_id=owner, kind="statement", version=1, commit_state="committed")
    db.add(batch)
    await db.flush()
    for ordinal, (observed_on, reference) in enumerate(
        ((date(2026, 1, 5), "stream-2026-01"), (date(2026, 2, 5), history_reference)), 1
    ):
        _, row = await _statement_source(
            db,
            owner,
            batch,
            booking_date=observed_on,
            reference=reference,
            ordinal=ordinal,
        )
        transaction = await create_transaction(
            db,
            owner,
            TransactionCreate(
                transaction_date=observed_on,
                description="Synthetic streaming subscription",
                type="expense",
                source="bank_import",
                postings=[
                    PostingCreate(
                        account_id=account.id,
                        source_amount=4900,
                        base_amount_pln=4900,
                        direction="debit",
                    ),
                    PostingCreate(
                        category_id=category.id,
                        source_amount=4900,
                        base_amount_pln=4900,
                        direction="credit",
                    ),
                ],
            ),
        )
        group = ImportGroup(user_id=owner, batch_id=batch.id, state="committed", version=1)
        receipt = FinanceCommandReceipt(
            user_id=owner,
            action="synthetic.recurring.history",
            key=reference,
            request_hash="a" * 64,
            response_json={},
        )
        db.add_all([group, receipt])
        await db.flush()
        posting = next(item for item in transaction.postings if item.account_id == account.id)
        db.add_all(
            [
                ImportBankIdentity(
                    user_id=owner,
                    batch_id=batch.id,
                    group_id=group.id,
                    bank="velo",
                    account_id=account.id,
                    currency="PLN",
                    strong_reference=reference,
                ),
                ImportEvidence(
                    user_id=owner,
                    batch_id=batch.id,
                    group_id=group.id,
                    row_id=row.id,
                    transaction_id=transaction.id,
                    posting_id=posting.id,
                    receipt_id=receipt.id,
                    component="whole",
                    attributed_source_amount=-4900,
                ),
            ]
        )
    _, current = await _statement_source(
        db,
        owner,
        batch,
        booking_date=date(2026, 3, 5),
        reference="stream-2026-03",
        ordinal=3,
    )
    await db.flush()
    return batch, account.id, current


async def test_recurring_suggestion_returns_candidate_without_mutating_persisted_state(
    db_session: AsyncSession, owner
) -> None:
    """Fails if a valid advisory candidate writes a schedule, transaction, or evidence."""
    batch, account_id, current = await _recurring_case(db_session, owner.id)
    before = await _counts(db_session)

    response = await propose_recurring_expense(
        db_session, owner.id, batch.id, current.id, account_id
    )

    assert response.status == "proposed"
    assert response.proposal is not None
    assert response.proposal.merchant == "synthetic streaming subscription"
    assert response.proposal.frequency == "monthly"
    assert response.proposal.amount_kind == "stable"
    assert response.proposal.amount_minor == -4900
    assert len(response.evidence) == 3
    assert await _counts(db_session) == before


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("iban", "current_source_account_uncertain"),
        ("bank", "current_source_account_uncertain"),
    ],
)
async def test_recurring_suggestion_rejects_unbound_current_source_without_mutation(
    db_session: AsyncSession, owner, change: str, reason: str
) -> None:
    """Fails if an IBAN or bank-provenance mismatch becomes an advisory candidate."""
    batch, account_id, current = await _recurring_case(db_session, owner.id)
    source = await db_session.get(ImportSource, current.source_id)
    assert source is not None
    if change == "iban":
        source.account_reference = "PL02114020040000300201355387"
    else:
        source.bank = "ing"
    await db_session.flush()
    before = await _counts(db_session)

    response = await propose_recurring_expense(
        db_session, owner.id, batch.id, current.id, account_id
    )

    assert response.status == "uncertain"
    assert response.reason == reason
    assert response.proposal is None
    assert await _counts(db_session) == before


async def test_recurring_suggestion_does_not_disclose_another_owners_current_row(
    db_session: AsyncSession, owner, other_owner
) -> None:
    """Fails if a caller can use another owner's import row to obtain a candidate."""
    batch, account_id, current = await _recurring_case(db_session, owner.id)
    before = await _counts(db_session)

    response = await propose_recurring_expense(
        db_session, other_owner.id, batch.id, current.id, account_id
    )

    assert response.status == "uncertain"
    assert response.reason == "current_row_not_found_or_not_current"
    assert response.proposal is None
    assert response.evidence == ()
    assert await _counts(db_session) == before


async def test_recurring_suggestion_rejects_history_with_a_different_canonical_reference(
    db_session: AsyncSession, owner
) -> None:
    """Fails if group identity is allowed to validate a different historical statement row."""
    batch, account_id, current = await _recurring_case(
        db_session, owner.id, history_reference="statement-reference"
    )
    identity = await db_session.scalar(
        select(ImportBankIdentity).where(
            ImportBankIdentity.strong_reference == "statement-reference"
        )
    )
    assert identity is not None
    identity.strong_reference = "other-group-reference"
    await db_session.flush()
    before = await _counts(db_session)

    response = await propose_recurring_expense(
        db_session, owner.id, batch.id, current.id, account_id
    )

    assert response.status == "uncertain"
    assert response.reason == "historical_identity_uncertain"
    assert response.proposal is None
    assert await _counts(db_session) == before
