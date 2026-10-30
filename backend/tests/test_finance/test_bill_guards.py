"""Document allocations keep their ledger identity and referenced metadata stable."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditEvent
from app.finance import service
from app.finance.bill_payments import allocate_payment
from app.finance.bills_schemas import AllocationCreate, MutationContext
from app.finance.currency_correction import apply_correction, preview_correction
from app.finance.models import (
    ActualImportMapping,
    Category,
    DocumentPaymentAllocation,
    FinancialDocument,
    FinancialTransaction,
    Posting,
)
from app.finance.nbp_rates import NbpRate, NbpRateProvider
from app.finance.schemas import AccountUpdate, TransactionUpdate
from app.finance.transactions import delete_transaction, update_transaction
from scripts.migrate_actual import replace_legacy_actual_data
from tests.test_finance.test_bill_payments import create_owner, expense, setup_bill

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def allocated(db_session):
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    posting_id, account, category = await expense(db_session, owner, 100)
    response = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=100),
        context=MutationContext(idempotency_key=f"allocation-{bill.id}"),
    )
    transaction_id = await db_session.scalar(
        select(Posting.transaction_id).where(Posting.id == posting_id)
    )
    return owner, bill, transaction_id, account, category, response


async def test_linked_expense_delete_and_identity_changes_rejected(db_session):
    owner, _bill, transaction_id, _account, _category, _ = await allocated(db_session)
    before_events = await db_session.scalar(select(func.count()).select_from(AuditEvent))
    before_postings = await db_session.scalar(
        select(func.count()).select_from(Posting).where(Posting.transaction_id == transaction_id)
    )
    with pytest.raises(ValueError, match="document payment"):
        await delete_transaction(db_session, owner, transaction_id)
    with pytest.raises(ValueError, match="document payment"):
        await update_transaction(
            db_session, owner, transaction_id, TransactionUpdate(is_pending=True)
        )
    with pytest.raises(ValueError, match="document payment"):
        await update_transaction(
            db_session,
            owner,
            transaction_id,
            TransactionUpdate(
                transaction_date=(await db_session.get(FinancialTransaction, transaction_id)).date
                + timedelta(days=1)
            ),
        )
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == before_events
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Posting)
            .where(Posting.transaction_id == transaction_id)
        )
        == before_postings
    )
    assert await db_session.get(FinancialTransaction, transaction_id) is not None


async def test_same_value_date_and_pending_patches_remain_idempotent(db_session):
    owner, _bill, transaction_id, _account, _category, _ = await allocated(db_session)
    transaction = await update_transaction(
        db_session,
        owner,
        transaction_id,
        TransactionUpdate(
            transaction_date=(await db_session.get(FinancialTransaction, transaction_id)).date
        ),
    )
    assert transaction is not None
    transaction = await update_transaction(
        db_session, owner, transaction_id, TransactionUpdate(is_pending=False)
    )
    assert transaction is not None and transaction.is_pending is False


async def test_document_account_and_category_references_restrict_mutation(db_session):
    owner, bill, _transaction_id, account, _category, _ = await allocated(db_session)
    bill.payment_account_id = account.id
    await db_session.flush()
    with pytest.raises(ValueError, match="financial document"):
        await service.update_account(db_session, owner, account.id, AccountUpdate(currency="EUR"))
    with pytest.raises(ValueError, match="financial document"):
        await service.delete_account(db_session, owner, account.id)


async def test_document_only_category_reference_rejects_delete_before_fk(db_session, monkeypatch):
    owner = await create_owner(db_session)
    category = Category(user_id=owner, name="Document-only category", type="expense")
    db_session.add(category)
    await db_session.flush()
    document = FinancialDocument(user_id=owner, category_id=category.id)
    db_session.add(document)
    await db_session.flush()

    with pytest.raises(ValueError, match="Category has records; deactivate it instead of deleting"):
        await service.delete_category(db_session, owner, category.id)
    assert await db_session.get(Category, category.id) is not None
    assert (await db_session.get(FinancialDocument, document.id)).category_id == category.id

    original_execute = db_session.execute

    class NoDocumentReference:
        def first(self):
            return None

    async def hide_document_reference(statement, *args, **kwargs):
        descriptions = getattr(statement, "column_descriptions", [])
        if descriptions and descriptions[0].get("entity") is FinancialDocument:
            return NoDocumentReference()
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", hide_document_reference)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await service.delete_category(db_session, owner, category.id)


async def replacement_expense(db_session):
    owner = await create_owner(db_session)
    posting_id, account, category = await expense(db_session, owner, 100)
    transaction = await db_session.scalar(
        select(FinancialTransaction).join(Posting).where(Posting.id == posting_id)
    )
    transaction.source = "actual"
    transaction.description = "[actual:replacement] Synthetic Actual expense"
    db_session.add(
        ActualImportMapping(
            user_id=owner,
            entity_type="transaction",
            actual_id="replacement",
            entity_id=transaction.id,
        )
    )
    await db_session.flush()
    return owner, transaction, account, category, posting_id


async def test_actual_replacement_rejects_allocated_transaction_before_dml(db_session):
    owner, transaction, account, category, posting_id = await replacement_expense(db_session)
    bill = await setup_bill(db_session, owner, amount=100)
    await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=100),
        context=MutationContext(idempotency_key="actual-replacement-allocation"),
    )
    before_events = await db_session.scalar(select(func.count()).select_from(AuditEvent))
    before_mappings = await db_session.scalar(
        select(func.count())
        .select_from(ActualImportMapping)
        .where(ActualImportMapping.user_id == owner)
    )
    before_allocations = await db_session.scalar(
        select(func.count())
        .select_from(DocumentPaymentAllocation)
        .where(DocumentPaymentAllocation.posting_id == posting_id)
    )

    with pytest.raises(ValueError, match="document payment"):
        await replace_legacy_actual_data(db_session, owner, {"replacement"})

    assert transaction.source == "actual"
    assert account.source == category.source == "manual"
    assert await db_session.get(FinancialTransaction, transaction.id) is not None
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == before_events
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(ActualImportMapping)
            .where(ActualImportMapping.user_id == owner)
        )
        == before_mappings
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DocumentPaymentAllocation)
            .where(DocumentPaymentAllocation.posting_id == posting_id)
        )
        == before_allocations
    )


@pytest.mark.parametrize("reference", ["account", "category"])
async def test_actual_replacement_rejects_document_only_metadata_reference_before_dml(
    db_session, reference
):
    owner, transaction, account, category, _posting_id = await replacement_expense(db_session)
    document = FinancialDocument(
        user_id=owner,
        payment_account_id=account.id if reference == "account" else None,
        category_id=category.id if reference == "category" else None,
    )
    db_session.add(document)
    await db_session.flush()

    with pytest.raises(ValueError, match="financial document"):
        await replace_legacy_actual_data(db_session, owner, {"replacement"})

    assert transaction.source == "actual"
    assert account.source == category.source == "manual"
    assert (await db_session.get(FinancialDocument, document.id)).id == document.id
    assert (await db_session.get(FinancialDocument, document.id)).payment_account_id == (
        account.id if reference == "account" else None
    )
    assert (await db_session.get(FinancialDocument, document.id)).category_id == (
        category.id if reference == "category" else None
    )


async def test_linked_currency_correction_is_rejected_without_audit_or_mutation(
    db_session, monkeypatch
):
    class SyntheticRates(NbpRateProvider):
        async def get_rate(self, currency, rate_date):
            assert currency == "EUR"
            return NbpRate(rate=4.1234, effective_date=rate_date, source="nbp")

    monkeypatch.setattr(NbpRateProvider, "get_rate", SyntheticRates.get_rate)
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner, amount=100)
    posting_id, account, _category = await expense(db_session, owner, 100)
    account.source = "actual"
    transaction_id = await db_session.scalar(
        select(Posting.transaction_id).where(Posting.id == posting_id)
    )
    plan = await preview_correction(db_session, owner, account.id, SyntheticRates())
    await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=100),
        context=MutationContext(idempotency_key="synthetic-correction-allocation"),
    )
    before_events = await db_session.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(ValueError, match="document payment"):
        await apply_correction(db_session, owner, plan, approved_digest=plan.digest())
    assert account.currency == "PLN"
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == before_events
    assert (
        await db_session.scalar(
            select(Posting.source_currency).where(Posting.transaction_id == transaction_id).limit(1)
        )
        == "PLN"
    )


async def test_delete_vs_allocate_two_independent_sessions_has_no_dangling_allocation(
    db_session, test_database
):
    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner, amount=100)
    posting_id, _account, _category = await expense(db_session, owner, 100)
    transaction_id = await db_session.scalar(
        select(Posting.transaction_id).where(Posting.id == posting_id)
    )
    await db_session.commit()
    sessions = async_sessionmaker(test_database, class_=AsyncSession, expire_on_commit=False)

    async def allocate_in_own_session():
        async with sessions() as session:
            try:
                result = await allocate_payment(
                    session,
                    owner,
                    bill.id,
                    AllocationCreate(version=2, posting_id=posting_id, amount_minor=100),
                    context=MutationContext(idempotency_key="race-allocate"),
                )
                await session.commit()
                return result
            except BaseException:
                await session.rollback()
                raise

    async def delete_in_own_session():
        async with sessions() as session:
            try:
                result = await delete_transaction(session, owner, transaction_id)
                await session.commit()
                return result
            except BaseException:
                await session.rollback()
                raise

    allocation_result, delete_result = await asyncio.wait_for(
        asyncio.gather(allocate_in_own_session(), delete_in_own_session(), return_exceptions=True),
        timeout=5,
    )
    async with sessions() as verify:
        allocation_count = await verify.scalar(
            select(func.count())
            .select_from(DocumentPaymentAllocation)
            .join(Posting, Posting.id == DocumentPaymentAllocation.posting_id)
            .where(DocumentPaymentAllocation.posting_id == posting_id)
        )
        transaction = await verify.get(FinancialTransaction, transaction_id)
    assert not (transaction is None and allocation_count)
    if allocation_count:
        assert not isinstance(allocation_result, BaseException)
        assert isinstance(delete_result, ValueError)
    else:
        assert isinstance(allocation_result, LookupError)
        assert delete_result is True
