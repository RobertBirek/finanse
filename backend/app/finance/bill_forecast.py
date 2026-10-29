"""Read-only projection of approved payable financial documents into cashflow."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import (
    Account,
    DocumentPaymentAllocation,
    FinancialDocument,
    RecurringOccurrenceCoverage,
    ScheduledFinanceItem,
)
from app.finance.schemas import CashflowSuggestion


@dataclass
class BillProjection:
    entries: list[CashflowSuggestion]
    day_changes_pln: dict[date, int]
    exclusions: list[str]
    covered_occurrences: set[tuple[uuid.UUID, date]]


async def project_bill_cashflows(
    db: AsyncSession, user_id: uuid.UUID, *, today: date, horizon_end: date
) -> BillProjection:
    bills = list(
        (
            await db.execute(
                select(FinancialDocument).where(
                    FinancialDocument.user_id == user_id, FinancialDocument.review == "approved"
                )
            )
        ).scalars()
    )
    coverage_rows = list(
        (
            await db.execute(
                select(RecurringOccurrenceCoverage).where(
                    RecurringOccurrenceCoverage.user_id == user_id
                )
            )
        ).scalars()
    )
    covered = {(row.scheduled_item_id, row.occurrence_date) for row in coverage_rows}
    covered_bill_ids = {row.financial_document_id for row in coverage_rows}
    entries: list[CashflowSuggestion] = []
    changes: dict[date, int] = {}
    exclusions: list[str] = []
    for bill in bills:
        paid = int(
            await db.scalar(
                select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                    DocumentPaymentAllocation.financial_document_id == bill.id
                )
            )
            or 0
        )
        remaining = max((bill.total_minor or 0) - paid, 0)
        if remaining <= 0:
            continue
        reasons: list[str] = []
        included = False
        effective_due = bill.due_date
        if bill.lifecycle != "active":
            reasons.append("inactive_lifecycle")
        if bill.declaration == "unknown":
            reasons.append("payment_declaration_unknown")
        elif bill.declaration != "payable":
            reasons.append("payment_not_payable")
        if bill.due_date is None:
            reasons.append("missing_due_date")
        elif bill.due_date < today:
            effective_due = today
        elif bill.due_date > horizon_end:
            reasons.append("outside_horizon")
        if bill.currency != "PLN":
            reasons.append("currency_without_pln_fx")
        if (
            bill.id not in covered_bill_ids
            and bill.recurring_decision is None
            and bill.due_date is not None
            and bill.payment_account_id is not None
            and bill.category_id is not None
            and await db.scalar(
                select(ScheduledFinanceItem.id)
                .where(
                    ScheduledFinanceItem.user_id == user_id,
                    ScheduledFinanceItem.is_active.is_(True),
                    ScheduledFinanceItem.type == "expense",
                    ScheduledFinanceItem.account_id == bill.payment_account_id,
                    ScheduledFinanceItem.category_id == bill.category_id,
                )
                .limit(1)
            )
            is not None
        ):
            reasons.append("coverage_unresolved")
        account = (
            await db.get(Account, bill.payment_account_id) if bill.payment_account_id else None
        )
        if account is None:
            reasons.append("missing_payment_account")
        elif (
            account.user_id != user_id
            or not account.is_active
            or not account.is_budget_account
            or account.currency != "PLN"
        ):
            reasons.append("payment_account_not_active_budget_pln")
        if not reasons and effective_due is not None:
            included = True
            changes[effective_due] = changes.get(effective_due, 0) - remaining
        else:
            exclusions.extend(reasons)
        entries.append(
            CashflowSuggestion(
                source="financial_document",
                source_key=f"financial_document:{bill.id}",
                financial_document_id=bill.id,
                name=bill.description or bill.supplier_name or "Financial document",
                type="expense",
                due_date=effective_due,
                amount_minor=remaining,
                currency=bill.currency or "PLN",
                amount_pln=remaining if bill.currency == "PLN" else None,
                status="due" if effective_due is not None and effective_due >= today else "overdue",
                included_in_forecast=included,
                exclusion_reasons=reasons,
            )
        )
    return BillProjection(
        entries=entries,
        day_changes_pln=changes,
        exclusions=sorted(set(exclusions)),
        covered_occurrences=covered,
    )
