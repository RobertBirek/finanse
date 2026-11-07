"""Owned card operations; transaction boundaries belong to the caller.

All writes share the finance mutation mutex then an account lock. A plan is a
classification of existing principal, never a second liability or expense.
"""

import itertools
import uuid
from datetime import date
from typing import Any, TypeVar

from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit.models import AuditEvent
from app.audit.service import log_event
from app.finance.credit_card_math import card_position, estimate_schedule
from app.finance.credit_card_models import (
    CardAllocation,
    CardCharge,
    CardInstallment,
    CardPlan,
    CardRecord,
    CardStatement,
    CreditCard,
)
from app.finance.credit_card_schemas import (
    AllocationCreate,
    BankSchedule,
    CardConfig,
    CardInput,
    ChargeCreate,
    PlanCreate,
    StatementCreate,
)
from app.finance.dates import _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.models import Category, FinancialTransaction, LoanAgreement, Posting
from app.finance.queries import lock_accounts
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_card_refund_transaction, create_transaction

Record = TypeVar("Record", bound=CardRecord)


class CardConflict(ValueError):
    pass


async def _card(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, *, lock: bool = False
) -> CreditCard:
    if lock:
        await lock_document_mutations(db, owner)
        accounts = await lock_accounts(db, owner, {account_id}, exclusive=True)
        if account_id not in accounts:
            raise LookupError("Card account not found")
        if not accounts[account_id].is_active:
            raise ValueError("Card account is inactive")
    item = await db.scalar(
        select(CreditCard)
        .where(CreditCard.user_id == owner, CreditCard.account_id == account_id)
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise LookupError("Card not configured")
    return item


async def configure(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, data: CardConfig
) -> dict:
    await lock_document_mutations(db, owner)
    accounts = await lock_accounts(db, owner, {account_id}, exclusive=True)
    account = accounts.get(account_id)
    if account is None:
        raise LookupError("Account not found")
    if account.currency != "PLN" or not account.is_active:
        raise ValueError("An active PLN account is required")
    if await db.scalar(
        select(LoanAgreement.id)
        .where(
            LoanAgreement.user_id == owner,
            (LoanAgreement.account_id == account_id)
            | (LoanAgreement.payment_account_id == account_id),
        )
        .limit(1)
    ):
        raise ValueError("Account is linked to a loan; use a separate card account")
    item = await db.scalar(
        select(CreditCard).where(CreditCard.account_id == account_id, CreditCard.user_id == owner)
    )
    if data.expected_version != (item.version if item else 0):
        raise CardConflict("Card settings changed; refresh before saving")
    before = jsonable_encoder(_fields(item)) if item else None
    if item is None:
        item = CreditCard(account_id=account_id, user_id=owner, version=1)
        db.add(item)
    else:
        item.version += 1
    for name, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(item, name, value)
    # Keep the same account/ledger; classification is not a balance migration.
    account.type = "credit"
    await db.flush()
    await log_event(
        db,
        owner,
        "credit_card",
        str(item.id),
        "configure",
        old_state=before,
        new_state=_audit_data(data),
    )
    return await detail(db, owner, account_id)


def _audit_data(data: CardInput) -> dict[str, Any]:
    return data.model_dump(mode="json")


def _fields(item: Any) -> dict[str, Any]:
    result = {
        column.key: getattr(item, column.key)
        for column in item.__table__.columns
        if column.key
        not in {"request_payload", "user_id", "created_at", "updated_at", "request_id"}
    }
    if "apr" in result:
        result["apr"] = format(result["apr"], ".4f")
    return result


async def _retry[Record: CardRecord](
    db: AsyncSession, card: CreditCard, cls: type[Record], data: Any
) -> Record | None:
    item = await db.scalar(
        select(cls).where(cls.card_id == card.id, cls.request_id == data.request_id)
    )
    if item is None:
        # Metadata can be deliberately unlinked without deleting its ledger row.
        # Keep the creation audit as a durable tombstone so a delayed old retry
        # cannot book that cost for a second time after the metadata was removed.
        removed = await db.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.user_id == card.user_id,
                AuditEvent.entity_type == "credit_card",
                AuditEvent.entity_id == str(card.id),
                AuditEvent.action == f"create_{cls.__tablename__}",
                AuditEvent.new_state["request_id"].as_string() == str(data.request_id),
            )
            .limit(1)
        )
        if removed is not None:
            raise CardConflict(
                "Request belongs to removed card metadata; check the ledger and do not repeat the booking"
            )
    if item is not None and item.request_payload != _audit_data(data):
        raise CardConflict("Request key already used with different data")
    return item


async def _save[Record: CardRecord](
    db: AsyncSession, card: CreditCard, item: Record, data: Any
) -> Record:
    item.user_id, item.card_id = card.user_id, card.id
    item.request_id, item.request_payload = data.request_id, _audit_data(data)
    db.add(item)
    await db.flush()
    await log_event(
        db,
        card.user_id,
        "credit_card",
        str(card.id),
        f"create_{item.__tablename__}",
        new_state={"record_id": str(item.id), **_audit_data(data)},
    )
    return item


async def _balance(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, as_of: date
) -> tuple[int, int]:
    balance, holds = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                FinancialTransaction.is_pending.is_(False),
                                case(
                                    (Posting.direction == "credit", Posting.source_amount),
                                    else_=-Posting.source_amount,
                                ),
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                FinancialTransaction.is_pending.is_(True)
                                & (Posting.direction == "debit"),
                                Posting.source_amount,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
            .where(
                FinancialTransaction.user_id == owner,
                Posting.account_id == account_id,
                FinancialTransaction.date <= as_of,
            )
        )
    ).one()
    return int(balance), int(holds)


async def _transaction(
    db: AsyncSession, owner: uuid.UUID, txn_id: uuid.UUID
) -> FinancialTransaction:
    item = await db.scalar(
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == owner, FinancialTransaction.id == txn_id)
        .options(selectinload(FinancialTransaction.postings))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None or item.is_pending or item.date > _local_today():
        raise ValueError("An owned, booked transaction is required")
    return item


def _card_leg(txn: FinancialTransaction, card: CreditCard, direction: str) -> int:
    legs = [p for p in txn.postings if p.account_id == card.account_id]
    if len(legs) != 1 or legs[0].direction != direction or legs[0].source_currency != "PLN":
        raise ValueError("Transaction does not match card and direction")
    return int(legs[0].source_amount)


async def create_statement(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, data: StatementCreate
) -> dict:
    card = await _card(db, owner, account_id, lock=True)
    item = await _retry(db, card, CardStatement, data)
    if item is None:
        if data.period_end > _local_today():
            raise ValueError("A bank statement cannot close in the future")
        overlaps = await db.scalar(
            select(CardStatement.id).where(
                CardStatement.card_id == card.id,
                CardStatement.period_start <= data.period_end,
                CardStatement.period_end >= data.period_start,
            )
        )
        if overlaps:
            raise CardConflict("Statement overlaps an existing statement")
        item = await _save(db, card, CardStatement(**data.model_dump(exclude={"request_id"})), data)
    return await _statement_view(db, card, item)


async def create_plan(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, data: PlanCreate
) -> dict:
    card = await _card(db, owner, account_id, lock=True)
    item = await _retry(db, card, CardPlan, data)
    if item is None:
        txn = await _transaction(db, owner, data.source_transaction_id)
        if await db.scalar(select(CardCharge.id).where(CardCharge.transaction_id == txn.id)):
            raise CardConflict("A booked card cost cannot finance a new plan")
        if txn.type not in {"expense", "transfer"} or data.first_due < txn.date:
            raise ValueError("Plan requires a purchase/payout before its first installment")
        amount = _card_leg(txn, card, "debit")
        used = int(
            await db.scalar(
                select(func.coalesce(func.sum(CardPlan.principal_pln), 0)).where(
                    CardPlan.source_transaction_id == txn.id
                )
            )
            or 0
        )
        if used + data.principal_pln > amount:
            raise CardConflict("Plan principal exceeds unassigned source principal")
        rows = estimate_schedule(
            data.principal_pln, data.apr, data.count, data.first_due, data.fees_pln
        )
        item = await _save(
            db,
            card,
            CardPlan(**data.model_dump(exclude={"request_id", "count", "first_due"})),
            data,
        )
        for row in rows:
            db.add(CardInstallment(plan_id=item.id, **row))
        await db.flush()
    return await _plan_view(db, item)


async def _owned_plan(db: AsyncSession, card: CreditCard, plan_id: uuid.UUID) -> CardPlan:
    item = await db.scalar(
        select(CardPlan).where(CardPlan.id == plan_id, CardPlan.card_id == card.id)
    )
    if item is None:
        raise LookupError("Card plan not found")
    return item


async def replace_schedule(
    db: AsyncSession,
    owner: uuid.UUID,
    account_id: uuid.UUID,
    plan_id: uuid.UUID,
    data: BankSchedule,
) -> dict:
    card = await _card(db, owner, account_id, lock=True)
    item = await _owned_plan(db, card, plan_id)
    paid = await db.scalar(
        select(CardAllocation.id).where(CardAllocation.plan_id == item.id).limit(1)
    )
    if item.version != data.expected_version or paid:
        raise CardConflict("Plan changed or has payments; cannot replace schedule")
    rows = data.installments
    if (
        sum(r.principal_pln for r in rows) != item.principal_pln
        or [r.number for r in rows] != list(range(1, len(rows) + 1))
        or any(a.due_date >= b.due_date for a, b in itertools.pairwise(rows))
    ):
        raise ValueError("Schedule must preserve principal, ordered dates and consecutive numbers")
    source = await _transaction(db, owner, item.source_transaction_id)
    if rows[0].due_date < source.date:
        raise ValueError("Schedule starts before financing")
    existing = (
        await db.scalars(select(CardInstallment).where(CardInstallment.plan_id == item.id))
    ).all()
    for row in existing:
        await db.delete(row)
    await db.flush()
    for input_row in rows:
        db.add(CardInstallment(plan_id=item.id, **input_row.model_dump()))
    item.schedule_kind, item.version = "bank", item.version + 1
    await log_event(
        db,
        owner,
        "credit_card",
        str(card.id),
        "replace_schedule",
        new_state={"plan_id": str(item.id), **_audit_data(data)},
    )
    await db.flush()
    return await _plan_view(db, item)


async def allocate(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, data: AllocationCreate
) -> dict:
    card = await _card(db, owner, account_id, lock=True)
    item = await _retry(db, card, CardAllocation, data)
    if item is not None:
        return _fields(item)
    txn = await _transaction(db, owner, data.transaction_id)
    if txn.type != "transfer" or len(txn.postings) != 2 or any(p.category_id for p in txn.postings):
        raise ValueError("Repayment must be an existing two-account PLN transfer")
    amount = _card_leg(txn, card, "credit")
    outgoing = next((p for p in txn.postings if p.account_id != card.account_id), None)
    if (
        outgoing is None
        or outgoing.direction != "debit"
        or outgoing.source_currency != "PLN"
        or outgoing.source_amount != amount
    ):
        raise ValueError("Repayment requires an equal PLN source account debit")
    # Statements and plans describe the same payment on two different axes.
    # Cap each axis, not their sum; neither creates another ledger entry.
    axis = (
        CardAllocation.plan_id.is_not(None)
        if data.plan_id
        else CardAllocation.statement_id.is_not(None)
    )
    used = (
        await db.scalar(
            select(func.coalesce(func.sum(CardAllocation.amount_pln), 0)).where(
                CardAllocation.transaction_id == txn.id, axis
            )
        )
        or 0
    )
    if used + data.amount_pln > amount:
        raise CardConflict("Allocation exceeds remaining transfer amount")
    if data.plan_id:
        plan = await _owned_plan(db, card, data.plan_id)
        source = await _transaction(db, owner, plan.source_transaction_id)
        if txn.date < source.date:
            raise ValueError("Payment predates plan financing")
        used_principal = (
            await db.scalar(
                select(func.coalesce(func.sum(CardAllocation.principal_pln), 0)).where(
                    CardAllocation.plan_id == plan.id
                )
            )
            or 0
        )
        if used_principal + data.principal_pln > plan.principal_pln:
            raise CardConflict("Principal exceeds plan remaining amount")
    else:
        statement = await db.scalar(
            select(CardStatement).where(
                CardStatement.id == data.statement_id, CardStatement.card_id == card.id
            )
        )
        if statement is None:
            raise LookupError("Card statement not found")
        if txn.date <= statement.period_end:
            raise ValueError("Payment must be after statement close")
        used_total = (
            await db.scalar(
                select(func.coalesce(func.sum(CardAllocation.amount_pln), 0)).where(
                    CardAllocation.statement_id == statement.id
                )
            )
            or 0
        )
        if used_total + data.amount_pln > statement.debt_pln:
            raise CardConflict("Payment exceeds statement remaining amount")
    return _fields(
        await _save(db, card, CardAllocation(**data.model_dump(exclude={"request_id"})), data)
    )


async def remove_allocation(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, allocation_id: uuid.UUID
) -> None:
    card = await _card(db, owner, account_id, lock=True)
    item = await db.scalar(
        select(CardAllocation).where(
            CardAllocation.id == allocation_id, CardAllocation.card_id == card.id
        )
    )
    if item is None:
        raise LookupError("Card allocation not found")
    await log_event(
        db,
        owner,
        "credit_card",
        str(card.id),
        "unlink_payment",
        old_state={"allocation_id": str(item.id), "transaction_id": str(item.transaction_id)},
    )
    await db.delete(item)
    await db.flush()


async def charge(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, data: ChargeCreate
) -> dict:
    card = await _card(db, owner, account_id, lock=True)
    item = await _retry(db, card, CardCharge, data)
    if item is not None:
        return _fields(item)
    if data.plan_id:
        await _owned_plan(db, card, data.plan_id)
    if data.booking_date > _local_today():
        raise ValueError("Future costs are estimates, not booked charges")
    category = await db.scalar(
        select(Category).where(
            Category.id == data.category_id,
            Category.user_id == owner,
            Category.is_active.is_(True),
            Category.type == "expense",
        )
    )
    if category is None:
        raise ValueError("An owned active expense category is required")
    refund = data.kind.endswith("_refund")
    direction = "credit" if refund else "debit"
    if data.existing_transaction_id:
        txn = await _transaction(db, owner, data.existing_transaction_id)
        already = await db.scalar(select(CardCharge.id).where(CardCharge.transaction_id == txn.id))
        if already:
            raise CardConflict("Transaction already classified as a card charge")
        if (
            _card_leg(txn, card, direction) != data.amount_pln
            or txn.date != data.booking_date
            or txn.type != "expense"
        ):
            raise ValueError("Existing charge date/amount/type mismatch")
        categories = [
            p for p in txn.postings if p.category_id == category.id and p.direction != direction
        ]
        if (
            len(txn.postings) != 2
            or len(categories) != 1
            or categories[0].source_amount != data.amount_pln
        ):
            raise ValueError("Existing charge category mismatch")
    else:
        create = create_card_refund_transaction if refund else create_transaction
        txn = await create(
            db,
            owner,
            TransactionCreate(
                type="expense",
                source="credit_card",
                description=data.description,
                transaction_date=data.booking_date,
                postings=[
                    PostingCreate(
                        account_id=account_id,
                        source_amount=data.amount_pln,
                        base_amount_pln=data.amount_pln,
                        direction=direction,
                    ),
                    PostingCreate(
                        category_id=category.id,
                        source_amount=data.amount_pln,
                        base_amount_pln=data.amount_pln,
                        direction="debit" if refund else "credit",
                    ),
                ],
            ),
        )
    item = CardCharge(
        **data.model_dump(exclude={"request_id", "category_id", "existing_transaction_id"}),
        transaction_id=txn.id,
    )
    return _fields(await _save(db, card, item, data))


async def _plan_view(db: AsyncSession, plan: CardPlan) -> dict:
    rows = (
        await db.scalars(
            select(CardInstallment)
            .where(CardInstallment.plan_id == plan.id)
            .order_by(CardInstallment.number)
        )
    ).all()
    paid = int(
        await db.scalar(
            select(func.coalesce(func.sum(CardAllocation.principal_pln), 0)).where(
                CardAllocation.plan_id == plan.id
            )
        )
        or 0
    )
    return {
        **_fields(plan),
        "remaining_principal_pln": plan.principal_pln - paid,
        "status": "closed" if paid == plan.principal_pln else "active",
        "installments": [
            {
                key: getattr(row, key)
                for key in ("number", "due_date", "principal_pln", "interest_pln", "fees_pln")
            }
            for row in rows
        ],
    }


async def _statement_view(db: AsyncSession, card: CreditCard, item: CardStatement) -> dict:
    paid = int(
        await db.scalar(
            select(func.coalesce(func.sum(CardAllocation.amount_pln), 0)).where(
                CardAllocation.statement_id == item.id
            )
        )
        or 0
    )
    timely = int(
        await db.scalar(
            select(func.coalesce(func.sum(CardAllocation.amount_pln), 0))
            .join(FinancialTransaction, FinancialTransaction.id == CardAllocation.transaction_id)
            .where(
                CardAllocation.statement_id == item.id, FinancialTransaction.date <= item.due_date
            )
        )
        or 0
    )
    balance, _ = await _balance(db, card.user_id, card.account_id, item.period_end)
    return {
        **_fields(item),
        "remaining_pln": max(0, item.debt_pln - paid),
        "minimum_remaining_pln": max(0, item.minimum_pln - paid),
        "paid_by_due_pln": timely,
        "reconciliation_difference_pln": max(0, -balance) - item.debt_pln,
    }


async def detail(db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID) -> dict:
    card = await _card(db, owner, account_id)
    balance, holds = await _balance(db, owner, account_id, _local_today())
    plans = (
        await db.scalars(
            select(CardPlan)
            .where(CardPlan.card_id == card.id)
            .order_by(CardPlan.created_at, CardPlan.id)
        )
    ).all()
    statements = (
        await db.scalars(
            select(CardStatement)
            .where(CardStatement.card_id == card.id)
            .order_by(CardStatement.period_end.desc())
        )
    ).all()
    allocations = (
        await db.scalars(
            select(CardAllocation)
            .where(CardAllocation.card_id == card.id)
            .order_by(CardAllocation.created_at, CardAllocation.id)
        )
    ).all()
    charges = (
        await db.scalars(
            select(CardCharge)
            .where(CardCharge.card_id == card.id)
            .order_by(CardCharge.booking_date.desc(), CardCharge.id)
        )
    ).all()
    return {
        **_fields(card),
        **card_position(card.limit_pln, balance, holds),
        "as_of": _local_today(),
        "plans": [await _plan_view(db, row) for row in plans],
        "statements": [await _statement_view(db, card, row) for row in statements],
        "allocations": [_fields(row) for row in allocations],
        "charges": [_fields(row) for row in charges],
    }


async def candidates(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, kind: str, limit: int, offset: int
) -> dict:
    await _card(db, owner, account_id)
    direction = "credit" if kind == "payment" else "debit"
    query = (
        select(FinancialTransaction, Posting.source_amount)
        .join(Posting, Posting.transaction_id == FinancialTransaction.id)
        .where(
            FinancialTransaction.user_id == owner,
            Posting.account_id == account_id,
            FinancialTransaction.is_pending.is_(False),
            FinancialTransaction.date <= _local_today(),
            Posting.source_currency == "PLN",
        )
    )
    if kind != "charge":
        query = query.where(
            Posting.direction == direction,
            FinancialTransaction.type.in_(
                ["transfer"] if kind == "payment" else ["expense", "transfer"]
            ),
        )
    else:
        query = query.where(FinancialTransaction.type.in_(["expense", "income"]))
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db.execute(
            query.order_by(FinancialTransaction.date.desc(), FinancialTransaction.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {"id": txn.id, "description": txn.description, "date": txn.date, "amount_pln": amount}
            for txn, amount in rows
        ],
    }


async def guard_transaction(db: AsyncSession, owner: uuid.UUID, txn_id: uuid.UUID) -> None:
    """Called after the shared mutation mutex, before any date/delete/pending edit."""
    for cls, column in [
        (CardPlan, CardPlan.source_transaction_id),
        (CardAllocation, CardAllocation.transaction_id),
        (CardCharge, CardCharge.transaction_id),
    ]:
        if await db.scalar(select(cls.id).where(cls.user_id == owner, column == txn_id).limit(1)):
            raise CardConflict(
                "Transaction is linked to a credit card record; unlink/reconcile first"
            )


async def remove_record(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID, kind: str, record_id: uuid.UUID
) -> None:
    """Correct an unallocated metadata mistake, never remove a ledger transaction."""
    card = await _card(db, owner, account_id, lock=True)
    item: CardRecord | None
    if kind == "plans":
        item = await _owned_plan(db, card, record_id)
        used = await db.scalar(
            select(CardAllocation.id).where(CardAllocation.plan_id == record_id).limit(1)
        )
        charged = await db.scalar(
            select(CardCharge.id).where(CardCharge.plan_id == record_id).limit(1)
        )
        if used or charged:
            raise CardConflict("Plan has payments or linked costs; history must be preserved")
        for row in (
            await db.scalars(select(CardInstallment).where(CardInstallment.plan_id == record_id))
        ).all():
            await db.delete(row)
    elif kind == "statements":
        item = await db.scalar(
            select(CardStatement).where(
                CardStatement.id == record_id, CardStatement.card_id == card.id
            )
        )
        if item is None:
            raise LookupError("Card record not found")
        if await db.scalar(
            select(CardAllocation.id).where(CardAllocation.statement_id == record_id).limit(1)
        ):
            raise CardConflict("Statement has linked payments; unlink first")
    else:
        item = await db.scalar(
            select(CardCharge).where(CardCharge.id == record_id, CardCharge.card_id == card.id)
        )
    if item is None:
        raise LookupError("Card record not found")
    await log_event(
        db,
        owner,
        "credit_card",
        str(card.id),
        "remove_metadata",
        old_state={"kind": kind, "record_id": str(record_id)},
    )
    await db.delete(item)
    await db.flush()
