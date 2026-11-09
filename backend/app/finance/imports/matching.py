"""Suggestions only: a similar Actual transaction never becomes an automatic link."""

import uuid
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.contracts import StatementRow
from app.finance.imports.decisions import signed_posting
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBankIdentity,
    ImportDecision,
    ImportEvidence,
    ImportGroupRow,
    ImportRow,
    ImportSource,
)
from app.finance.imports.schemas import ExistingCandidate, ImportDecisionInput
from app.finance.models import Account, FinancialTransaction, Posting


async def candidate_postings(
    db: AsyncSession, owner: uuid.UUID, row_id: uuid.UUID, account_id: uuid.UUID | None = None
) -> list[tuple[ExistingCandidate, FinancialTransaction, Posting]]:
    record = (
        await db.execute(
            select(ImportRow, ImportSource)
            .join(ImportSource, ImportSource.id == ImportRow.source_id)
            .where(
                ImportRow.id == row_id, ImportRow.user_id == owner, ImportSource.user_id == owner
            )
        )
    ).one_or_none()
    if record is None:
        raise ImportError("row_not_found", "Nie znaleziono wiersza źródłowego.", 404)
    row, source = record
    value = StatementRow.model_validate(row.fields)
    if value.booking_date is None or value.state != "posted":
        return []
    if account_id is None:
        group_id = await db.scalar(
            select(ImportGroupRow.group_id).where(
                ImportGroupRow.row_id == row_id, ImportGroupRow.user_id == owner
            )
        )
        if group_id is not None:
            saved = await db.scalar(
                select(ImportDecision)
                .where(ImportDecision.group_id == group_id, ImportDecision.user_id == owner)
                .order_by(ImportDecision.version.desc())
                .limit(1)
            )
            if saved is not None:
                decision = ImportDecisionInput.model_validate(saved.data)
                account_id = (
                    decision.other_account_id
                    if decision.kind in {"transfer", "exchange"}
                    and len(decision.row_ids) == 2
                    and value.amount + value.fee > 0
                    else decision.account_id
                )
    strong_ids: set[uuid.UUID] = set()
    if value.bank_reference and account_id is not None:
        strong_ids = set(
            (
                await db.scalars(
                    select(ImportEvidence.posting_id)
                    .join(
                        ImportBankIdentity, ImportBankIdentity.group_id == ImportEvidence.group_id
                    )
                    .where(
                        ImportBankIdentity.user_id == owner,
                        ImportEvidence.user_id == owner,
                        ImportBankIdentity.bank == source.bank,
                        ImportBankIdentity.account_id == account_id,
                        ImportBankIdentity.currency == value.currency,
                        ImportBankIdentity.strong_reference == value.bank_reference,
                    )
                )
            ).all()
        )
    statement = (
        select(FinancialTransaction, Posting)
        .join(Posting, Posting.transaction_id == FinancialTransaction.id)
        .join(Account, Account.id == Posting.account_id)
        .where(
            FinancialTransaction.user_id == owner,
            Account.user_id == owner,
            Posting.source_currency == value.currency,
            FinancialTransaction.is_pending.is_(False),
            or_(
                Posting.id.in_(strong_ids),
                FinancialTransaction.date.between(
                    value.booking_date - timedelta(days=3), value.booking_date + timedelta(days=3)
                ),
            ),
        )
    )
    if account_id is not None:
        statement = statement.where(Account.id == account_id)
    records = (
        await db.execute(
            statement.order_by(FinancialTransaction.date, FinancialTransaction.id, Posting.id)
        )
    ).all()
    candidates = []
    for transaction, posting in records:
        strong = posting.id in strong_ids
        exact_amount = signed_posting(posting) == value.amount
        same_description = " ".join(transaction.description.casefold().split()) == " ".join(
            value.description.casefold().split()
        )
        if not strong and not exact_amount and not same_description:
            continue
        reasons = [
            *(["bank_reference"] if strong else []),
            *(["same_signed_amount"] if exact_amount else []),
            *(["same_description"] if same_description else []),
        ]
        conflicts = [
            *(["amount_mismatch"] if not exact_amount else []),
            *(["booking_date_difference"] if transaction.date != value.booking_date else []),
        ]
        candidates.append(
            (
                ExistingCandidate(
                    transaction_id=transaction.id,
                    account_posting_id=posting.id,
                    strength="strong" if strong else "possible",
                    reasons=reasons,
                    conflicts=conflicts,
                ),
                transaction,
                posting,
            )
        )
    return candidates


async def get_candidates(
    db: AsyncSession, owner: uuid.UUID, row_id: uuid.UUID
) -> list[ExistingCandidate]:
    return [
        candidate
        for candidate, _transaction, _posting in await candidate_postings(db, owner, row_id)
    ]
