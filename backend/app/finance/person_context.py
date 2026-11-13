"""Read-only evidence for a gift attribution; never normalizes existing postings."""

import uuid
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.categorization_context import columns, digest
from app.finance.imports.models import ImportEvidence
from app.finance.ledger_validation import _validate_posting_sum, _validate_transaction_postings
from app.finance.models import (
    ActualImportMapping,
    DocumentPaymentAllocation,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
)
from app.finance.person_models import FinancePerson, PersonTransactionLink
from app.finance.person_schemas import PersonLinkContext, PersonResponse


class PersonError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 409) -> None:
        self.code, self.status = code, status
        super().__init__(detail)


async def get_person_link_context(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
) -> PersonLinkContext:
    txn = await db.scalar(
        select(FinancialTransaction)
        .where(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == owner,
        )
        .options(selectinload(FinancialTransaction.postings))
        .execution_options(populate_existing=True)
    )
    if txn is None:
        raise LookupError("Transaction not found")
    mappings = list(
        (
            await db.scalars(
                select(ActualImportMapping)
                .where(
                    ActualImportMapping.entity_type == "transaction",
                    ActualImportMapping.entity_id == txn.id,
                )
                .order_by(ActualImportMapping.id)
            )
        ).all()
    )
    evidence = list(
        (
            await db.scalars(
                select(ImportEvidence)
                .where(
                    ImportEvidence.transaction_id == txn.id,
                )
                .order_by(ImportEvidence.id)
            )
        ).all()
    )
    loans = list(
        (
            await db.scalars(
                select(LoanPaymentLink.id)
                .where(LoanPaymentLink.transaction_id == txn.id)
                .order_by(LoanPaymentLink.id)
            )
        ).all()
    )
    allocations = list(
        (
            await db.scalars(
                select(DocumentPaymentAllocation.id)
                .join(
                    Posting,
                    Posting.id == DocumentPaymentAllocation.posting_id,
                )
                .where(Posting.transaction_id == txn.id)
                .order_by(DocumentPaymentAllocation.id)
            )
        ).all()
    )
    link = await db.scalar(
        select(PersonTransactionLink)
        .where(
            PersonTransactionLink.user_id == owner,
            PersonTransactionLink.transaction_id == txn.id,
        )
        .execution_options(populate_existing=True)
    )
    person = (
        await db.scalar(
            select(FinancePerson)
            .where(
                FinancePerson.id == link.person_id,
                FinancePerson.user_id == owner,
            )
            .execution_options(populate_existing=True)
        )
        if link
        else None
    )
    snapshot = digest(
        {
            "schema": "person-gift-v1",
            "transaction": columns(txn),
            "postings": [columns(p) for p in sorted(txn.postings, key=lambda p: str(p.id))],
            "dates": columns(txn.date_metadata) if txn.date_metadata else None,
            "mappings": [columns(m) for m in mappings],
            "evidence": [columns(e) for e in evidence],
            "loans": loans,
            "allocations": allocations,
            "link": columns(link) if link else None,
        }
    )
    reason: str | None = None
    if loans or allocations:
        reason = "Protected loan or document payment; not a gift."
    elif any(r.user_id != owner for r in mappings) or any(r.user_id != owner for r in evidence):
        reason = "Foreign source evidence protects this payment."
    elif txn.type != "income" or txn.is_pending or len(txn.postings) != 2:
        reason = "Wybierz zaksięgowany przychód z jednym rachunkiem i kategorią."
    else:
        # The shared validator normalizes is_budget_impact. Use detached values,
        # not ORM postings: assigning a person must never modify the ledger.
        ps = [
            SimpleNamespace(
                **{
                    key: getattr(p, key)
                    for key in (
                        "account_id",
                        "category_id",
                        "source_amount",
                        "source_currency",
                        "base_amount_pln",
                        "fx_rate",
                        "direction",
                        "is_budget_impact",
                    )
                }
            )
            for p in txn.postings
        ]
        try:
            _validate_posting_sum(ps, "income")
            if len({p.source_currency for p in ps}) != 1:
                raise ValueError("Mixed currency income")
            await _validate_transaction_postings(
                db, owner, ps, "income", allow_inactive_accounts=True
            )
        except ValueError:
            reason = "Przychód ma nieprawidłowy zapis lub kategorię. Wymaga osobnej korekty, bez automatycznej zmiany."
    return PersonLinkContext(
        transaction_id=txn.id,
        snapshot=snapshot,
        person=PersonResponse.model_validate(person) if person else None,
        eligible=reason is None,
        reason=reason,
    )
