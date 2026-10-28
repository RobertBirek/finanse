"""Loan schedule plans and explicit links to immutable existing transfers."""

import uuid

from sqlalchemy import case, false, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.dates import _local_today
from app.finance.loan_schemas import (
    LoanCreate,
    LoanDetailResponse,
    LoanInstallmentCreate,
    LoanInstallmentResponse,
    LoanInstallmentUpdate,
    LoanPaymentCandidate,
    LoanPaymentCandidatesResponse,
    LoanPaymentResponse,
    LoanResponse,
    LoanUpdate,
)
from app.finance.models import (
    FinancialTransaction,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
    Posting,
)
from app.finance.queries import lock_accounts


def _total(row: LoanInstallment) -> int:
    return row.principal_pln + row.interest_pln + row.fees_pln


async def _owned_loan(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID, *, lock: bool = False
) -> LoanAgreement | None:
    statement = select(LoanAgreement).where(
        LoanAgreement.id == loan_id, LoanAgreement.user_id == user_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(statement)).scalar_one_or_none()


async def create_loan(db: AsyncSession, user_id: uuid.UUID, data: LoanCreate) -> LoanAgreement:
    if data.account_id == data.payment_account_id:
        raise ValueError("Loan accounts must be different")
    accounts = await lock_accounts(db, user_id, {data.account_id, data.payment_account_id})
    debt = accounts.get(data.account_id)
    payer = accounts.get(data.payment_account_id)
    if debt is None or payer is None:
        raise LookupError("Loan account not found")
    if (
        not debt.is_active
        or not payer.is_active
        or debt.currency != "PLN"
        or payer.currency != "PLN"
    ):
        raise ValueError("Loan accounts must be active PLN accounts")
    loan = LoanAgreement(user_id=user_id, **data.model_dump())
    db.add(loan)
    await db.flush()
    return loan


async def update_loan(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID, data: LoanUpdate
) -> LoanAgreement | None:
    loan = await _owned_loan(db, user_id, loan_id)
    if loan is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            raise ValueError("Loan fields cannot be null")
        setattr(loan, key, value)
    await db.flush()
    return loan


async def create_loan_installment(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID, data: LoanInstallmentCreate
) -> LoanInstallment:
    loan = await _owned_loan(db, user_id, loan_id, lock=True)
    if loan is None:
        raise LookupError("Loan not found")
    installment = LoanInstallment(user_id=user_id, loan_id=loan.id, **data.model_dump())
    db.add(installment)
    await db.flush()
    return installment


async def update_loan_installment(
    db: AsyncSession,
    user_id: uuid.UUID,
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    data: LoanInstallmentUpdate,
) -> LoanInstallment | None:
    installment = (
        await db.execute(
            select(LoanInstallment)
            .where(
                LoanInstallment.id == installment_id,
                LoanInstallment.loan_id == loan_id,
                LoanInstallment.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if installment is None:
        return None
    linked = await db.scalar(
        select(LoanPaymentLink.id).where(LoanPaymentLink.installment_id == installment.id).limit(1)
    )
    if linked is not None:
        raise ValueError("Cannot change a linked installment")
    updates = data.model_dump(exclude_unset=True)
    if any(value is None for value in updates.values()):
        raise ValueError("Installment fields cannot be null")
    values = {
        key: updates.get(key, getattr(installment, key))
        for key in ("principal_pln", "interest_pln", "fees_pln")
    }
    total = sum(values.values())
    if total == 0 or total > 9_007_199_254_740_991:
        raise ValueError("Installment total must be between 1 and the API amount limit")
    for key, value in updates.items():
        setattr(installment, key, value)
    await db.flush()
    return installment


async def delete_loan_installment(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID, installment_id: uuid.UUID
) -> bool:
    installment = (
        await db.execute(
            select(LoanInstallment)
            .where(
                LoanInstallment.id == installment_id,
                LoanInstallment.loan_id == loan_id,
                LoanInstallment.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if installment is None:
        return False
    if (
        await db.scalar(
            select(LoanPaymentLink.id)
            .where(LoanPaymentLink.installment_id == installment.id)
            .limit(1)
        )
        is not None
    ):
        raise ValueError("Cannot delete a linked installment")
    await db.delete(installment)
    await db.flush()
    return True


def _valid_transfer_amount(transaction: FinancialTransaction, loan: LoanAgreement) -> int:
    postings = transaction.postings
    if (
        transaction.user_id != loan.user_id
        or transaction.type != "transfer"
        or transaction.is_pending
        or transaction.date > _local_today()
        or len(postings) != 2
    ):
        raise ValueError("Transaction is not an eligible loan payment transfer")
    debit = next(
        (
            p
            for p in postings
            if p.account_id == loan.payment_account_id
            and p.direction == "debit"
            and p.category_id is None
        ),
        None,
    )
    credit = next(
        (
            p
            for p in postings
            if p.account_id == loan.account_id and p.direction == "credit" and p.category_id is None
        ),
        None,
    )
    if debit is None or credit is None or debit is credit:
        raise ValueError("Transaction is not an eligible loan payment transfer")
    if any(
        p.source_currency != "PLN" or p.fx_rate != 1 or p.source_amount != p.base_amount_pln
        for p in postings
    ):
        raise ValueError("Transaction is not an eligible PLN loan payment transfer")
    if debit.base_amount_pln <= 0 or debit.base_amount_pln != credit.base_amount_pln:
        raise ValueError("Transaction is not an eligible loan payment transfer")
    return debit.base_amount_pln


async def link_loan_payment(
    db: AsyncSession,
    user_id: uuid.UUID,
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    transaction_id: uuid.UUID,
) -> LoanDetailResponse | None:
    loan = await _owned_loan(db, user_id, loan_id, lock=True)
    if loan is None:
        return None
    installment = (
        await db.execute(
            select(LoanInstallment)
            .where(
                LoanInstallment.id == installment_id,
                LoanInstallment.loan_id == loan.id,
                LoanInstallment.user_id == user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if installment is None:
        return None
    transaction = (
        await db.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == user_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if transaction is None:
        raise LookupError("Transaction not found")
    await db.refresh(transaction, attribute_names=["postings"])
    existing = await db.scalar(
        select(LoanPaymentLink)
        .where(LoanPaymentLink.transaction_id == transaction_id)
        .with_for_update()
    )
    if existing is not None:
        if existing.installment_id == installment.id:
            return await get_loan(db, user_id, loan.id)
        raise ValueError("Transaction is already linked to another installment")
    amount = _valid_transfer_amount(transaction, loan)
    paid = await _installment_paid(db, installment.id)
    if paid + amount > _total(installment):
        raise ValueError("Payment exceeds installment remaining amount")
    db.add(
        LoanPaymentLink(
            user_id=user_id, installment_id=installment.id, transaction_id=transaction.id
        )
    )
    await db.flush()
    return await get_loan(db, user_id, loan.id)


async def unlink_loan_payment(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID, link_id: uuid.UUID
) -> bool:
    # Always take the agreement before installment/link locks, just as linking
    # does. This prevents opposite lock orders on an idempotent link vs unlink.
    if await _owned_loan(db, user_id, loan_id, lock=True) is None:
        return False
    link = (
        await db.execute(
            select(LoanPaymentLink)
            .join(LoanInstallment)
            .where(
                LoanPaymentLink.id == link_id,
                LoanPaymentLink.user_id == user_id,
                LoanInstallment.loan_id == loan_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if link is None:
        return False
    await db.delete(link)
    await db.flush()
    return True


async def _installment_paid(db: AsyncSession, installment_id: uuid.UUID) -> int:
    value = await db.scalar(
        select(func.coalesce(func.sum(Posting.base_amount_pln), 0))
        .select_from(LoanPaymentLink)
        .join(FinancialTransaction, FinancialTransaction.id == LoanPaymentLink.transaction_id)
        .join(Posting, Posting.transaction_id == FinancialTransaction.id)
        .join(LoanInstallment, LoanInstallment.id == LoanPaymentLink.installment_id)
        .join(LoanAgreement, LoanAgreement.id == LoanInstallment.loan_id)
        .where(
            LoanPaymentLink.installment_id == installment_id,
            Posting.account_id == LoanAgreement.payment_account_id,
            Posting.direction == "debit",
        )
    )
    return int(value or 0)


async def _detail(db: AsyncSession, loan: LoanAgreement) -> LoanDetailResponse:
    installments = list(
        (
            await db.execute(
                select(LoanInstallment)
                .where(LoanInstallment.loan_id == loan.id)
                .order_by(LoanInstallment.due_date, LoanInstallment.number, LoanInstallment.id)
            )
        ).scalars()
    )
    links = (
        await db.execute(
            select(LoanPaymentLink, FinancialTransaction, Posting)
            .join(FinancialTransaction, FinancialTransaction.id == LoanPaymentLink.transaction_id)
            .join(Posting, Posting.transaction_id == FinancialTransaction.id)
            .where(
                LoanPaymentLink.installment_id.in_([i.id for i in installments])
                if installments
                else false(),
                Posting.account_id == loan.payment_account_id,
                Posting.direction == "debit",
            )
            .order_by(FinancialTransaction.date, FinancialTransaction.id)
        )
    ).all()
    payment_rows: dict[uuid.UUID, list[LoanPaymentResponse]] = {
        item.id: [] for item in installments
    }
    for link, transaction, posting in links:
        payment_rows[link.installment_id].append(
            LoanPaymentResponse(
                id=link.id,
                transaction_id=transaction.id,
                transaction_date=transaction.date,
                amount_pln=posting.base_amount_pln,
            )
        )
    responses = []
    for item in installments:
        total = _total(item)
        paid = sum(row.amount_pln for row in payment_rows[item.id])
        remaining = total - paid
        responses.append(
            LoanInstallmentResponse(
                id=item.id,
                number=item.number,
                due_date=item.due_date,
                principal_pln=item.principal_pln,
                interest_pln=item.interest_pln,
                fees_pln=item.fees_pln,
                total_pln=total,
                paid_pln=paid,
                remaining_pln=remaining,
                payment_status="paid" if remaining == 0 else "partial" if paid else "unpaid",
                payments=payment_rows[item.id],
            )
        )
    ledger_balance = await db.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (Posting.direction == "credit", Posting.base_amount_pln),
                        else_=-Posting.base_amount_pln,
                    )
                ),
                0,
            )
        ).where(Posting.account_id == loan.account_id)
    )
    principal = sum(item.principal_pln for item in installments)
    interest = sum(item.interest_pln for item in installments)
    fees = sum(item.fees_pln for item in installments)
    paid = sum(item.paid_pln for item in responses)
    total = principal + interest + fees
    return LoanDetailResponse(
        id=loan.id,
        name=loan.name,
        account_id=loan.account_id,
        payment_account_id=loan.payment_account_id,
        is_active=loan.is_active,
        ledger_balance_pln=int(ledger_balance or 0),
        planned_principal_pln=principal,
        planned_interest_pln=interest,
        planned_fees_pln=fees,
        total_planned_pln=total,
        paid_pln=paid,
        remaining_pln=total - paid,
        installments=responses,
    )


async def get_loan(
    db: AsyncSession, user_id: uuid.UUID, loan_id: uuid.UUID
) -> LoanDetailResponse | None:
    loan = await _owned_loan(db, user_id, loan_id)
    return None if loan is None else await _detail(db, loan)


async def get_loans(db: AsyncSession, user_id: uuid.UUID) -> list[LoanResponse]:
    loans = list(
        (
            await db.execute(
                select(LoanAgreement)
                .where(LoanAgreement.user_id == user_id)
                .order_by(LoanAgreement.created_at.desc(), LoanAgreement.id.desc())
            )
        ).scalars()
    )
    details = [await _detail(db, loan) for loan in loans]
    return [LoanResponse(**detail.model_dump(exclude={"installments"})) for detail in details]


async def get_loan_payment_candidates(
    db: AsyncSession,
    user_id: uuid.UUID,
    loan_id: uuid.UUID,
    installment_id: uuid.UUID,
    limit: int,
    offset: int,
) -> LoanPaymentCandidatesResponse | None:
    loan = await _owned_loan(db, user_id, loan_id)
    installment = (
        await db.execute(
            select(LoanInstallment).where(
                LoanInstallment.id == installment_id,
                LoanInstallment.loan_id == loan_id,
                LoanInstallment.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if loan is None or installment is None:
        return None
    remaining = _total(installment) - await _installment_paid(db, installment.id)
    debit = Posting.__table__.alias("loan_payment_debit")
    credit = Posting.__table__.alias("loan_payment_credit")
    conditions = [
        FinancialTransaction.user_id == user_id,
        FinancialTransaction.type == "transfer",
        FinancialTransaction.is_pending.is_(False),
        FinancialTransaction.date <= _local_today(),
        ~select(LoanPaymentLink.id)
        .where(LoanPaymentLink.transaction_id == FinancialTransaction.id)
        .exists(),
        debit.c.transaction_id == FinancialTransaction.id,
        credit.c.transaction_id == FinancialTransaction.id,
        debit.c.account_id == loan.payment_account_id,
        debit.c.direction == "debit",
        debit.c.category_id.is_(None),
        credit.c.account_id == loan.account_id,
        credit.c.direction == "credit",
        credit.c.category_id.is_(None),
        debit.c.source_currency == "PLN",
        credit.c.source_currency == "PLN",
        debit.c.source_amount == debit.c.base_amount_pln,
        credit.c.source_amount == credit.c.base_amount_pln,
        debit.c.fx_rate == 1,
        credit.c.fx_rate == 1,
        debit.c.base_amount_pln == credit.c.base_amount_pln,
        debit.c.base_amount_pln > 0,
        debit.c.base_amount_pln <= remaining,
        select(func.count(Posting.id))
        .where(Posting.transaction_id == FinancialTransaction.id)
        .scalar_subquery()
        == 2,
    ]
    statement = (
        select(
            FinancialTransaction.id,
            FinancialTransaction.date,
            FinancialTransaction.description,
            debit.c.base_amount_pln,
        )
        .select_from(FinancialTransaction)
        .join(debit, debit.c.transaction_id == FinancialTransaction.id)
        .join(credit, credit.c.transaction_id == FinancialTransaction.id)
        .where(*conditions)
    )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = (
        await db.execute(
            statement.order_by(
                FinancialTransaction.date.desc(),
                FinancialTransaction.created_at.desc(),
                FinancialTransaction.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return LoanPaymentCandidatesResponse(
        items=[
            LoanPaymentCandidate(
                transaction_id=row[0],
                transaction_date=row[1],
                description=row[2],
                amount_pln=row[3],
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
