"""Allegro Pay schedules backed by existing ledger transactions."""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.allegro_pay_models import (
    AllegroPayAllocation,
    AllegroPayInstallment,
    AllegroPayProfile,
    AllegroPayPurchase,
)
from app.finance.allegro_pay_schemas import PaymentInput, ProfileInput, PurchaseInput
from app.finance.credit_card_models import CreditCard
from app.finance.dates import _local_today
from app.finance.document_guards import lock_document_mutations
from app.finance.models import Account, FinancialTransaction, LoanPaymentLink
from app.finance.queries import get_account
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction


async def _profile(db: AsyncSession, owner: uuid.UUID, profile_id: uuid.UUID) -> AllegroPayProfile:
    profile = await db.scalar(
        select(AllegroPayProfile)
        .where(AllegroPayProfile.id == profile_id, AllegroPayProfile.user_id == owner)
        .with_for_update()
    )
    if profile is None:
        raise LookupError("Nie znaleziono konta Allegro Pay")
    return profile


async def save_profile(db: AsyncSession, owner: uuid.UUID, data: ProfileInput) -> AllegroPayProfile:
    await lock_document_mutations(db, owner)
    account = await db.scalar(
        select(Account)
        .where(Account.id == data.account_id, Account.user_id == owner)
        .with_for_update()
    )
    if account is None:
        raise LookupError("Nie znaleziono konta")
    card = await db.scalar(select(CreditCard.id).where(CreditCard.account_id == account.id))
    if not account.is_active or account.currency != "PLN" or card is not None:
        raise ValueError("Wybierz aktywne konto w PLN")
    profile = await db.scalar(
        select(AllegroPayProfile)
        .where(AllegroPayProfile.account_id == account.id)
        .with_for_update()
    )
    if profile is None:
        profile = AllegroPayProfile(user_id=owner, account_id=account.id, limit_pln=data.limit_pln)
        db.add(profile)
    elif profile.user_id != owner:
        raise LookupError("Nie znaleziono konta")
    else:
        profile.limit_pln = data.limit_pln
    await db.flush()
    return profile


async def _transaction(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID
) -> FinancialTransaction:
    transaction = await db.scalar(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if transaction is None:
        raise LookupError("Nie znaleziono transakcji")
    return transaction


async def add_purchase(
    db: AsyncSession, owner: uuid.UUID, profile_id: uuid.UUID, data: PurchaseInput
) -> AllegroPayPurchase:
    await lock_document_mutations(db, owner)
    profile = await _profile(db, owner, profile_id)
    existing_request = await db.scalar(
        select(AllegroPayPurchase).where(
            AllegroPayPurchase.profile_id == profile.id,
            AllegroPayPurchase.request_id == data.request_id,
        )
    )
    payload = data.model_dump(mode="json")
    if existing_request is not None:
        if existing_request.request_payload != payload:
            raise ValueError("Identyfikator żądania został użyty dla innego zakupu")
        return existing_request
    if data.transaction_id is None:
        assert data.category_id is not None
        amount = data.principal_pln
        transaction = await create_transaction(
            db,
            owner,
            TransactionCreate(
                description=data.name,
                type="expense",
                transaction_date=data.purchase_date,
                postings=[
                    PostingCreate(
                        account_id=profile.account_id,
                        direction="debit",
                        source_amount=amount,
                        base_amount_pln=amount,
                    ),
                    PostingCreate(
                        category_id=data.category_id,
                        direction="credit",
                        source_amount=amount,
                        base_amount_pln=amount,
                    ),
                ],
            ),
        )
        await db.refresh(transaction, attribute_names=["postings"])
    else:
        transaction = await _transaction(db, owner, data.transaction_id)
    account_postings = [p for p in transaction.postings if p.account_id == profile.account_id]
    if (
        transaction.type != "expense"
        or transaction.is_pending
        or len(account_postings) != 1
        or account_postings[0].direction != "debit"
        or account_postings[0].source_currency != "PLN"
        or account_postings[0].source_amount != data.principal_pln
        or account_postings[0].base_amount_pln != data.principal_pln
    ):
        raise ValueError("Wydatek nie odpowiada kwocie i kontu zakupu")
    existing = await db.scalar(
        select(AllegroPayPurchase.id).where(AllegroPayPurchase.transaction_id == transaction.id)
    )
    if existing is not None:
        raise ValueError("Wydatek jest już powiązany z zakupem")
    purchase = AllegroPayPurchase(
        user_id=owner,
        profile_id=profile.id,
        transaction_id=transaction.id,
        name=data.name,
        purchase_date=data.purchase_date,
        principal_pln=data.principal_pln,
        request_id=data.request_id,
        request_payload=payload,
    )
    db.add(purchase)
    await db.flush()
    db.add_all(
        [
            AllegroPayInstallment(
                user_id=owner, purchase_id=purchase.id, number=index, **item.model_dump()
            )
            for index, item in enumerate(data.installments, 1)
        ]
    )
    await db.flush()
    return purchase


async def allocate_payment(
    db: AsyncSession, owner: uuid.UUID, profile_id: uuid.UUID, data: PaymentInput
) -> None:
    await lock_document_mutations(db, owner)
    profile = await _profile(db, owner, profile_id)
    transaction = await _transaction(db, owner, data.transaction_id)
    credits = [
        p
        for p in transaction.postings
        if p.account_id == profile.account_id and p.direction == "credit"
    ]
    debits = [
        p
        for p in transaction.postings
        if p.account_id is not None
        and p.account_id != profile.account_id
        and p.direction == "debit"
    ]
    if (
        transaction.type != "transfer"
        or transaction.is_pending
        or transaction.date > _local_today()
        or len(transaction.postings) != 2
        or len(credits) != 1
        or len(debits) != 1
        or any(
            p.source_currency != "PLN" or p.source_amount != p.base_amount_pln
            for p in transaction.postings
        )
        or credits[0].base_amount_pln != debits[0].base_amount_pln
    ):
        raise ValueError("Wybierz zaksięgowany przelew PLN na konto Allegro Pay")
    if await db.scalar(
        select(LoanPaymentLink.id).where(LoanPaymentLink.transaction_id == transaction.id)
    ):
        raise ValueError("Przelew jest już powiązany ze spłatą kredytu")
    existing = (
        await db.scalars(
            select(AllegroPayAllocation).where(
                AllegroPayAllocation.transaction_id == transaction.id
            )
        )
    ).all()
    if existing:
        actual = {item.installment_id: item.amount_pln for item in existing}
        requested = {item.installment_id: item.amount_pln for item in data.allocations}
        if actual == requested:
            return
        raise ValueError("Ta spłata jest już przypisana")
    if sum(item.amount_pln for item in data.allocations) > credits[0].base_amount_pln:
        raise ValueError("Przypisania przekraczają kwotę przelewu")
    ids = [item.installment_id for item in data.allocations]
    installments = (
        await db.scalars(
            select(AllegroPayInstallment)
            .join(AllegroPayPurchase, AllegroPayPurchase.id == AllegroPayInstallment.purchase_id)
            .where(
                AllegroPayInstallment.id.in_(ids),
                AllegroPayInstallment.user_id == owner,
                AllegroPayPurchase.profile_id == profile.id,
            )
            .order_by(AllegroPayInstallment.id)
            .with_for_update(of=AllegroPayInstallment)
        )
    ).all()
    by_id = {item.id: item for item in installments}
    if len(by_id) != len(ids):
        raise LookupError("Nie znaleziono raty")
    paid: dict[uuid.UUID, int] = {
        installment_id: int(amount)
        for installment_id, amount in (
            await db.execute(
                select(
                    AllegroPayAllocation.installment_id, func.sum(AllegroPayAllocation.amount_pln)
                )
                .where(AllegroPayAllocation.installment_id.in_(ids))
                .group_by(AllegroPayAllocation.installment_id)
            )
        ).all()
    }
    for item in data.allocations:
        installment = by_id[item.installment_id]
        total = installment.principal_pln + installment.interest_pln + installment.fees_pln
        if int(paid.get(item.installment_id, 0)) + item.amount_pln > total:
            raise ValueError("Przypisanie przekracza kwotę raty")
        db.add(
            AllegroPayAllocation(
                user_id=owner,
                installment_id=item.installment_id,
                transaction_id=transaction.id,
                amount_pln=item.amount_pln,
            )
        )
    await db.flush()


async def overview(db: AsyncSession, owner: uuid.UUID, profile_id: uuid.UUID) -> dict:
    profile = await _profile(db, owner, profile_id)
    account = await get_account(db, owner, profile.account_id)
    assert account is not None
    purchases = (
        await db.scalars(
            select(AllegroPayPurchase)
            .where(AllegroPayPurchase.profile_id == profile.id)
            .order_by(AllegroPayPurchase.purchase_date.desc(), AllegroPayPurchase.id)
        )
    ).all()
    ids = [purchase.id for purchase in purchases]
    installments = (
        await db.scalars(
            select(AllegroPayInstallment)
            .where(AllegroPayInstallment.purchase_id.in_(ids))
            .order_by(AllegroPayInstallment.due_date, AllegroPayInstallment.number)
        )
    ).all()
    installment_ids = [item.id for item in installments]
    allocations = (
        await db.scalars(
            select(AllegroPayAllocation).where(
                AllegroPayAllocation.installment_id.in_(installment_ids)
            )
        )
    ).all()
    by_installment: dict[uuid.UUID, list[AllegroPayAllocation]] = defaultdict(list)
    by_purchase: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for allocation in allocations:
        by_installment[allocation.installment_id].append(allocation)
    for item in installments:
        links = by_installment[item.id]
        paid = sum(link.amount_pln for link in links)
        total = item.principal_pln + item.interest_pln + item.fees_pln
        by_purchase[item.purchase_id].append(
            {
                "id": item.id,
                "number": item.number,
                "due_date": item.due_date,
                "principal_pln": item.principal_pln,
                "interest_pln": item.interest_pln,
                "fees_pln": item.fees_pln,
                "total_pln": total,
                "paid_pln": paid,
                "remaining_pln": total - paid,
                "payments": [
                    {"transaction_id": link.transaction_id, "amount_pln": link.amount_pln}
                    for link in links
                ],
            }
        )
    scheduled_remaining = sum(row["remaining_pln"] for rows in by_purchase.values() for row in rows)
    future_costs = sum(
        row["interest_pln"] + row["fees_pln"] for rows in by_purchase.values() for row in rows
    )
    return {
        "id": profile.id,
        "account_id": account.id,
        "account_name": account.name,
        "limit_pln": profile.limit_pln,
        "ledger_balance_pln": account.balance_pln,
        "scheduled_remaining_pln": scheduled_remaining,
        "scheduled_costs_pln": future_costs,
        "available_pln": min(profile.limit_pln, max(0, profile.limit_pln + account.balance_pln))
        if profile.limit_pln is not None
        else None,
        "purchases": [
            {
                "id": p.id,
                "name": p.name,
                "purchase_date": p.purchase_date,
                "principal_pln": p.principal_pln,
                "transaction_id": p.transaction_id,
                "installments": by_purchase[p.id],
            }
            for p in purchases
        ],
    }


async def unlink_payment(
    db: AsyncSession, owner: uuid.UUID, profile_id: uuid.UUID, transaction_id: uuid.UUID
) -> None:
    await lock_document_mutations(db, owner)
    profile = await _profile(db, owner, profile_id)
    await _transaction(db, owner, transaction_id)
    links = (
        await db.scalars(
            select(AllegroPayAllocation)
            .join(AllegroPayInstallment, AllegroPayInstallment.id == AllegroPayAllocation.installment_id)
            .join(AllegroPayPurchase, AllegroPayPurchase.id == AllegroPayInstallment.purchase_id)
            .where(
                AllegroPayAllocation.user_id == owner,
                AllegroPayAllocation.transaction_id == transaction_id,
                AllegroPayPurchase.profile_id == profile.id,
            )
            .with_for_update(of=AllegroPayAllocation)
        )
    ).all()
    if not links:
        raise LookupError("Nie znaleziono przypisania spłaty")
    for link in links:
        await db.delete(link)
    await db.flush()
