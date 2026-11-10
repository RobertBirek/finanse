"""Read-only, immutable inputs and explicit plan differences. Never mutates ledger rows."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.document_guards import lock_document_mutations
from app.finance.imports.contracts import ParsedSchedule, ScheduleRow
from app.finance.models import (
    FinancialTransaction,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
    Posting,
)


@dataclass(frozen=True)
class ScheduleInstallment:
    id: uuid.UUID
    number: int
    due_date: date
    principal_pln: int
    interest_pln: int
    fees_pln: int
    superseded_by_revision_id: uuid.UUID | None


@dataclass(frozen=True)
class SchedulePayment:
    id: uuid.UUID
    installment_id: uuid.UUID
    transaction_id: uuid.UUID
    amount_pln: int
    transaction_date: date


@dataclass(frozen=True)
class ScheduleState:
    loan_id: uuid.UUID
    active_revision_id: uuid.UUID | None
    installments: tuple[ScheduleInstallment, ...]
    payment_links: tuple[SchedulePayment, ...]
    fingerprint: str


@dataclass(frozen=True)
class ScheduleConflict:
    code: str
    row_key: str | None
    installment_ids: list[uuid.UUID]


@dataclass(frozen=True)
class ScheduleDiff:
    cutover_date: date
    reused_ids: list[uuid.UUID]
    new_rows: list[ScheduleRow]
    superseded_ids: list[uuid.UUID]
    retained_history_ids: list[uuid.UUID]
    conflicts: list[ScheduleConflict]
    warnings: list[str]
    fingerprint: str


async def load_schedule_state(
    db: AsyncSession, owner: uuid.UUID, loan_id: uuid.UUID, *, lock: bool
) -> ScheduleState | None:
    if lock:
        await lock_document_mutations(db, owner)
    query = select(LoanAgreement).where(LoanAgreement.user_id == owner, LoanAgreement.id == loan_id)
    if lock:
        query = query.with_for_update()
    loan = await db.scalar(query.execution_options(populate_existing=True))
    if loan is None:
        return None
    item_query = (
        select(LoanInstallment)
        .where(LoanInstallment.user_id == owner, LoanInstallment.loan_id == loan_id)
        .order_by(LoanInstallment.id)
    )
    if lock:
        item_query = item_query.with_for_update()
    items = (await db.scalars(item_query.execution_options(populate_existing=True))).all()
    snapshots = tuple(
        ScheduleInstallment(
            i.id,
            i.number,
            i.due_date,
            i.principal_pln,
            i.interest_pln,
            i.fees_pln,
            i.superseded_by_revision_id,
        )
        for i in items
    )
    link_query = (
        select(LoanPaymentLink)
        .where(LoanPaymentLink.installment_id.in_([i.id for i in items]))
        .order_by(LoanPaymentLink.id)
    )
    if lock:
        link_query = link_query.with_for_update()
    links = (await db.scalars(link_query.execution_options(populate_existing=True))).all()
    payments: list[SchedulePayment] = []
    financial_inputs: list[dict[str, object]] = []
    for link in links:
        tx_query = select(FinancialTransaction).where(
            FinancialTransaction.id == link.transaction_id
        )
        if lock:
            tx_query = tx_query.with_for_update()
        transaction = await db.scalar(tx_query.execution_options(populate_existing=True))
        if transaction is None or transaction.user_id != owner or link.user_id != owner:
            raise ValueError("Loan payment ownership is inconsistent")
        postings = (
            await db.scalars(
                select(Posting)
                .where(Posting.transaction_id == transaction.id)
                .order_by(Posting.id)
                .execution_options(populate_existing=True)
            )
        ).all()
        amount = sum(
            p.base_amount_pln
            for p in postings
            if p.account_id == loan.payment_account_id and p.direction == "debit"
        )
        payments.append(
            SchedulePayment(link.id, link.installment_id, transaction.id, amount, transaction.date)
        )
        financial_inputs.append(
            {
                "id": transaction.id,
                "date": transaction.date,
                "type": transaction.type,
                "pending": transaction.is_pending,
                "postings": [
                    {
                        "id": p.id,
                        "account": p.account_id,
                        "category": p.category_id,
                        "amount": p.source_amount,
                        "currency": p.source_currency,
                        "base": p.base_amount_pln,
                        "fx": str(p.fx_rate),
                        "direction": p.direction,
                    }
                    for p in postings
                ],
            }
        )
    content = {
        "loan": {
            "id": loan.id,
            "owner": owner,
            "active_revision": loan.active_schedule_revision_id,
            "name": loan.name,
            "active": loan.is_active,
            "account": loan.account_id,
            "payment_account": loan.payment_account_id,
        },
        "installments": [asdict(i) for i in snapshots],
        "payments": [asdict(p) for p in payments],
        "financial_inputs": financial_inputs,
    }
    fingerprint = hashlib.sha256(
        json.dumps(content, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return ScheduleState(
        loan.id, loan.active_schedule_revision_id, snapshots, tuple(payments), fingerprint
    )


def diff_schedule(state: ScheduleState, parsed: ParsedSchedule, *, today: date) -> ScheduleDiff:
    cutover = max(today, parsed.effective_date) if parsed.effective_date is not None else today
    conflicts: list[ScheduleConflict] = []
    reused: list[uuid.UUID] = []
    new: list[ScheduleRow] = []
    superseded: list[uuid.UUID] = []
    retained: list[uuid.UUID] = []
    active = [i for i in state.installments if i.superseded_by_revision_id is None]
    linked = {p.installment_id for p in state.payment_links}
    if (
        parsed.bank != "velo"
        or not parsed.complete_tail
        or parsed.effective_date is None
        or not parsed.rows
        or any(c.required and c.result != "passed" for c in parsed.checks)
    ):
        return ScheduleDiff(
            cutover,
            [],
            [],
            [],
            [],
            [ScheduleConflict("source_incomplete", None, [])],
            [],
            state.fingerprint,
        )
    if len({r.due_date for r in parsed.rows}) != len(parsed.rows):
        return ScheduleDiff(
            cutover,
            [],
            [],
            [],
            [],
            [ScheduleConflict("source_dates_ambiguous", None, [])],
            [],
            state.fingerprint,
        )
    for row in parsed.rows:
        matches = [
            i
            for i in active
            if (i.due_date, i.principal_pln, i.interest_pln, i.fees_pln)
            == (row.due_date, row.principal, row.interest, row.fees)
        ]
        key = str(row.bank_number)
        if len(matches) > 1:
            conflicts.append(
                ScheduleConflict("installment_ambiguous", key, [i.id for i in matches])
            )
        elif matches:
            reused.append(matches[0].id)
        elif row.due_date < cutover and state.installments:
            same_date = [i.id for i in active if i.due_date == row.due_date]
            conflicts.append(
                ScheduleConflict("historical_row_changed_or_unmatched", key, same_date)
            )
        else:
            new.append(row)
    for item in active:
        if item.due_date < cutover:
            retained.append(item.id)
            if item.id not in reused and item.id not in linked:
                conflicts.append(ScheduleConflict("historical_unpaid_missing", None, [item.id]))
        elif item.id not in reused:
            if item.id in linked:
                conflicts.append(
                    ScheduleConflict("linked_future_missing_or_changed", None, [item.id])
                )
            else:
                superseded.append(item.id)
    warnings = ["retained_history"] if retained else []
    return ScheduleDiff(
        cutover, reused, new, superseded, retained, conflicts, warnings, state.fingerprint
    )
