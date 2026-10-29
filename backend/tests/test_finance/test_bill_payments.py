import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.documents.models import Document
from app.finance.bills import approve_bill
from app.finance.bills_schemas import (
    AllocationCreate,
    BillApprove,
    BillPaymentCreate,
    MutationContext,
)
from app.finance.dates import _local_today
from app.finance.models import (
    Account,
    Category,
    DocumentPaymentAllocation,
    FinancialDocument,
    FinancialTransaction,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
    Posting,
)
from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transactions import create_transaction
from app.identity.models import User
from app.inbox.models import InboxItem

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def setup_bill(
    db, owner: uuid.UUID, amount: int = 10_000, currency: str = "PLN"
) -> FinancialDocument:
    bill = FinancialDocument(user_id=owner)
    db.add(bill)
    await db.flush()
    await approve_bill(
        db,
        owner,
        bill.id,
        BillApprove(
            version=1,
            kind="invoice",
            supplier_name="Supplier",
            description="Bill",
            total_minor=amount,
            currency=currency,
        ),
        context=MutationContext(idempotency_key=f"approve-{bill.id}"),
    )
    return bill


async def create_owner(db) -> uuid.UUID:
    user = User(email=f"{uuid.uuid4()}@example.test", password_hash="x", display_name="Owner")
    db.add(user)
    await db.flush()
    return user.id


async def expense(
    db,
    owner: uuid.UUID,
    amount: int,
    *,
    pending: bool = False,
    days: int = 0,
    kind: str = "expense",
) -> tuple[uuid.UUID, Account, Category]:
    account = Account(
        user_id=owner, name=f"Account {uuid.uuid4()}", type="checking", currency="PLN"
    )
    category = Category(
        user_id=owner,
        name=f"Category {uuid.uuid4()}",
        type="income" if kind == "income" else "expense",
    )
    db.add_all([account, category])
    await db.flush()
    transaction = await create_transaction(
        db,
        owner,
        TransactionCreate(
            transaction_date=_local_today() + timedelta(days=days),
            description="Expense",
            type=kind,
            is_pending=pending,
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    fx_rate=1,
                    direction="credit" if kind == "income" else "debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=amount,
                    source_currency="PLN",
                    base_amount_pln=amount,
                    fx_rate=1,
                    direction="debit" if kind == "income" else "credit",
                ),
            ],
        ),
    )
    posting = next(item for item in transaction.postings if item.account_id == account.id)
    return posting.id, account, category


async def test_allocate_partial_full_then_unlink(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, unlink_payment

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    first, _, _ = await expense(db_session, owner, 4_000)
    second, _, _ = await expense(db_session, owner, 6_000)
    partial = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=first, amount_minor=4_000),
        context=MutationContext(idempotency_key="allocate-one"),
    )
    assert (partial.paid_minor, partial.remaining_minor, partial.reconciliation) == (
        4_000,
        6_000,
        "partial",
    )
    full = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=3, posting_id=second, amount_minor=6_000),
        context=MutationContext(idempotency_key="allocate-two"),
    )
    assert (full.paid_minor, full.remaining_minor, full.reconciliation) == (10_000, 0, "full")
    allocation = await db_session.scalar(
        select(DocumentPaymentAllocation).where(
            DocumentPaymentAllocation.financial_document_id == bill.id,
            DocumentPaymentAllocation.posting_id == second,
        )
    )
    result = await unlink_payment(
        db_session,
        owner,
        bill.id,
        allocation.id,
        full.version,
        context=MutationContext(idempotency_key="unlink"),
    )
    assert (result.paid_minor, result.remaining_minor, result.reconciliation) == (
        4_000,
        6_000,
        "partial",
    )


@pytest.mark.parametrize(
    "pending,days,kind",
    [(True, 0, "expense"), (False, 1, "expense"), (False, 0, "transfer"), (False, 0, "income")],
)
async def test_rejects_non_eligible_posting(
    db_session, pending: bool, days: int, kind: str
) -> None:
    from app.finance.bill_payments import allocate_payment

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    posting, _, _ = await expense(db_session, owner, 10_000, pending=pending, days=days, kind=kind)
    with pytest.raises(ValueError):
        await allocate_payment(
            db_session,
            owner,
            bill.id,
            AllocationCreate(version=2, posting_id=posting, amount_minor=1),
            context=MutationContext(idempotency_key=f"invalid-{kind}-{pending}-{days}"),
        )


async def test_record_payment_retry_creates_one_expense(db_session) -> None:
    from app.finance.bill_payments import record_bill_payment

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    _, account, category = await expense(db_session, owner, 1)
    data = BillPaymentCreate(
        version=2,
        account_id=account.id,
        category_id=category.id,
        payment_date=_local_today(),
        amount_minor=10_000,
        description="Confirmed",
        confirm_new_payment=True,
    )
    first = await record_bill_payment(
        db_session, owner, bill.id, data, context=MutationContext(idempotency_key="pay")
    )
    replay = await record_bill_payment(
        db_session, owner, bill.id, data, context=MutationContext(idempotency_key="pay")
    )
    assert first == replay
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Posting).where(Posting.account_id == account.id)
        )
        == 2
    )
    payment = await db_session.scalar(
        select(FinancialTransaction).where(FinancialTransaction.source == "document_payment")
    )
    assert payment is not None
    postings = list(
        await db_session.scalars(select(Posting).where(Posting.transaction_id == payment.id))
    )
    assert len(postings) >= 2
    assert (
        sum(
            item.base_amount_pln if item.direction == "debit" else -item.base_amount_pln
            for item in postings
        )
        == 0
    )


async def test_candidates_hide_cross_owner_and_prioritize_legacy_target(db_session) -> None:
    from app.finance.bill_payments import get_payment_candidates
    from app.finance.models import FinancialDocumentSource

    owner = await create_owner(db_session)
    other = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    eligible, _, _ = await expense(db_session, owner, 10_000)
    hidden, _, _ = await expense(db_session, other, 10_000)
    legacy_txn_id = await db_session.scalar(
        select(Posting.transaction_id).where(Posting.id == eligible)
    )
    document = Document(
        user_id=owner,
        filename="legacy.pdf",
        original_name="legacy.pdf",
        mime_type="application/pdf",
        sha256_hash=uuid.uuid4().hex * 2,
        size_bytes=1,
        storage_path="test/legacy.pdf",
    )
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        FinancialDocumentSource(
            user_id=owner, financial_document_id=bill.id, document_id=document.id
        )
    )
    db_session.add(
        InboxItem(
            user_id=owner,
            content="legacy",
            source_type="document",
            target_type="transaction",
            target_id=legacy_txn_id,
            is_processed=True,
            classified_by="legacy",
            agent_suggestion={"document_id": str(document.id)},
        )
    )
    page = await get_payment_candidates(db_session, owner, bill.id, limit=10, offset=0)
    assert [item.posting_id for item in page.items] == [eligible]
    assert page.items[0].legacy_inbox_reference == str(legacy_txn_id)
    assert hidden not in {item.posting_id for item in page.items}


async def test_fx_and_loan_linked_expenses_are_not_allocatable(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, get_payment_candidates

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    fx_account = Account(user_id=owner, name="EUR", type="checking", currency="EUR")
    category = Category(user_id=owner, name="FX category", type="expense")
    db_session.add_all([fx_account, category])
    await db_session.flush()
    transaction = await create_transaction(
        db_session,
        owner,
        TransactionCreate(
            transaction_date=_local_today(),
            description="FX expense",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=fx_account.id,
                    source_amount=100,
                    source_currency="EUR",
                    base_amount_pln=400,
                    fx_rate=4,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=400,
                    source_currency="PLN",
                    base_amount_pln=400,
                    fx_rate=1,
                    direction="credit",
                ),
            ],
        ),
    )
    fx_posting = next(item for item in transaction.postings if item.account_id)
    normal, account, _ = await expense(db_session, owner, 10_000)
    agreement = LoanAgreement(
        user_id=owner, name="Loan", account_id=account.id, payment_account_id=fx_account.id
    )
    db_session.add(agreement)
    await db_session.flush()
    installment = LoanInstallment(
        user_id=owner,
        loan_id=agreement.id,
        number=1,
        due_date=_local_today(),
        principal_pln=10_000,
        interest_pln=0,
        fees_pln=0,
    )
    db_session.add(installment)
    await db_session.flush()
    transaction_id = await db_session.scalar(
        select(Posting.transaction_id).where(Posting.id == normal)
    )
    db_session.add(
        LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=transaction_id)
    )
    page = await get_payment_candidates(db_session, owner, bill.id, limit=10, offset=0)
    assert {item.posting_id for item in page.items}.isdisjoint({fx_posting.id, normal})
    with pytest.raises(ValueError):
        await allocate_payment(
            db_session,
            owner,
            bill.id,
            AllocationCreate(version=2, posting_id=fx_posting.id, amount_minor=1),
            context=MutationContext(idempotency_key="fx"),
        )


async def test_audit_failure_rolls_back_new_expense_and_allocation(db_session, monkeypatch) -> None:
    from app.finance import bill_payments

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    _, account, category = await expense(db_session, owner, 1)

    async def fail_audit(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(bill_payments, "log_event", fail_audit)
    with pytest.raises(RuntimeError, match="audit failed"):
        await bill_payments.record_bill_payment(
            db_session,
            owner,
            bill.id,
            BillPaymentCreate(
                version=2,
                account_id=account.id,
                category_id=category.id,
                payment_date=_local_today(),
                amount_minor=10_000,
                description="Payment",
                confirm_new_payment=True,
            ),
            context=MutationContext(idempotency_key="audit-failure"),
        )
    await db_session.rollback()
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(FinancialTransaction)
            .where(FinancialTransaction.source == "document_payment")
        )
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(DocumentPaymentAllocation)) == 0


async def test_inactive_account_can_link_history_but_cannot_record_new_payment(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, record_bill_payment

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    posting, account, category = await expense(db_session, owner, 10_000)
    account.is_active = False
    linked = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=posting, amount_minor=5_000),
        context=MutationContext(idempotency_key="inactive-link"),
    )
    assert linked.paid_minor == 5_000
    with pytest.raises(ValueError, match="payment_account_not_eligible"):
        await record_bill_payment(
            db_session,
            owner,
            bill.id,
            BillPaymentCreate(
                version=linked.version,
                account_id=account.id,
                category_id=category.id,
                payment_date=_local_today(),
                amount_minor=5_000,
                description="New",
                confirm_new_payment=True,
            ),
            context=MutationContext(idempotency_key="inactive-new"),
        )


async def test_split_category_expense_links_once_without_ledger_write(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, unlink_payment

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    account = Account(user_id=owner, name="Split", type="checking", currency="PLN")
    categories = [
        Category(user_id=owner, name=f"Split {number}", type="expense") for number in range(2)
    ]
    db_session.add_all([account, *categories])
    await db_session.flush()
    transaction = await create_transaction(
        db_session,
        owner,
        TransactionCreate(
            transaction_date=_local_today(),
            description="Split expense",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=10_000,
                    source_currency="PLN",
                    base_amount_pln=10_000,
                    fx_rate=1,
                    direction="debit",
                ),
                *[
                    PostingCreate(
                        category_id=category.id,
                        source_amount=5_000,
                        source_currency="PLN",
                        base_amount_pln=5_000,
                        fx_rate=1,
                        direction="credit",
                    )
                    for category in categories
                ],
            ],
        ),
    )
    posting = next(item for item in transaction.postings if item.account_id)
    before = await db_session.scalar(select(func.count()).select_from(Posting))
    allocated = await allocate_payment(
        db_session,
        owner,
        bill.id,
        AllocationCreate(version=2, posting_id=posting.id, amount_minor=5_000),
        context=MutationContext(idempotency_key="split"),
    )
    allocation = await db_session.scalar(
        select(DocumentPaymentAllocation).where(
            DocumentPaymentAllocation.financial_document_id == bill.id
        )
    )
    with pytest.raises(ValueError, match="allocation_already_exists"):
        await allocate_payment(
            db_session,
            owner,
            bill.id,
            AllocationCreate(version=allocated.version, posting_id=posting.id, amount_minor=1),
            context=MutationContext(idempotency_key="split-repeat"),
        )
    await unlink_payment(
        db_session,
        owner,
        bill.id,
        allocation.id,
        allocated.version,
        context=MutationContext(idempotency_key="split-unlink"),
    )
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == before


async def test_persisted_unbalanced_expense_is_fail_closed(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, get_payment_candidates

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    account = Account(user_id=owner, name="Malformed", type="checking", currency="PLN")
    db_session.add(account)
    await db_session.flush()
    transaction = FinancialTransaction(
        user_id=owner,
        date=_local_today(),
        description="Malformed",
        type="expense",
        is_pending=False,
    )
    db_session.add(transaction)
    await db_session.flush()
    posting = Posting(
        transaction_id=transaction.id,
        account_id=account.id,
        source_amount=10_000,
        source_currency="PLN",
        base_amount_pln=10_000,
        fx_rate=1,
        fx_rate_source="manual",
        direction="debit",
    )
    db_session.add(posting)
    await db_session.flush()
    before_version = bill.version
    assert not (await get_payment_candidates(db_session, owner, bill.id, limit=10, offset=0)).items
    with pytest.raises(ValueError, match="posting_not_eligible"):
        await allocate_payment(
            db_session,
            owner,
            bill.id,
            AllocationCreate(version=2, posting_id=posting.id, amount_minor=1),
            context=MutationContext(idempotency_key="malformed"),
        )
    assert bill.version == before_version
    assert await db_session.scalar(select(func.count()).select_from(DocumentPaymentAllocation)) == 0


async def test_allocation_sequence_preserves_ledger_and_capacity_invariants(db_session) -> None:
    from app.finance.bill_payments import allocate_payment, unlink_payment

    owner = await create_owner(db_session)
    first_bill = await setup_bill(db_session, owner, 10_000)
    second_bill = await setup_bill(db_session, owner, 10_000)
    posting_id, _, _ = await expense(db_session, owner, 7_000)

    async def ledger_snapshot() -> tuple[list[tuple], list[tuple]]:
        transactions = list(
            await db_session.scalars(select(FinancialTransaction).order_by(FinancialTransaction.id))
        )
        postings = list(await db_session.scalars(select(Posting).order_by(Posting.id)))
        return (
            [
                (item.id, item.date, item.description, item.type, item.is_pending, item.source)
                for item in transactions
            ],
            [
                (
                    item.id,
                    item.transaction_id,
                    item.account_id,
                    item.category_id,
                    item.source_amount,
                    item.source_currency,
                    item.base_amount_pln,
                    item.fx_rate,
                    item.fx_rate_source,
                    item.direction,
                    item.is_budget_impact,
                )
                for item in postings
            ],
        )

    async def assert_invariants() -> None:
        allocated = await db_session.scalar(
            select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                DocumentPaymentAllocation.posting_id == posting_id
            )
        )
        assert allocated <= 7_000
        for bill in (first_bill, second_bill):
            paid = await db_session.scalar(
                select(func.coalesce(func.sum(DocumentPaymentAllocation.amount_minor), 0)).where(
                    DocumentPaymentAllocation.financial_document_id == bill.id
                )
            )
            assert paid <= 10_000

    before = await ledger_snapshot()
    first = await allocate_payment(
        db_session,
        owner,
        first_bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=5_000),
        context=MutationContext(idempotency_key="sequence-first"),
    )
    await assert_invariants()
    assert first == await allocate_payment(
        db_session,
        owner,
        first_bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=5_000),
        context=MutationContext(idempotency_key="sequence-first"),
    )
    with pytest.raises(ValueError, match="allocation_exceeds_posting_capacity"):
        await allocate_payment(
            db_session,
            owner,
            second_bill.id,
            AllocationCreate(version=2, posting_id=posting_id, amount_minor=3_000),
            context=MutationContext(idempotency_key="sequence-too-much"),
        )
    await assert_invariants()
    second = await allocate_payment(
        db_session,
        owner,
        second_bill.id,
        AllocationCreate(version=2, posting_id=posting_id, amount_minor=2_000),
        context=MutationContext(idempotency_key="sequence-second"),
    )
    await assert_invariants()
    allocation = await db_session.scalar(
        select(DocumentPaymentAllocation).where(
            DocumentPaymentAllocation.financial_document_id == first_bill.id
        )
    )
    assert allocation is not None
    await unlink_payment(
        db_session,
        owner,
        first_bill.id,
        allocation.id,
        first.version,
        context=MutationContext(idempotency_key="sequence-unlink"),
    )
    await assert_invariants()
    assert second.paid_minor == 2_000
    assert await ledger_snapshot() == before


async def test_candidates_require_deliberate_older_search_and_explain_reasons(db_session) -> None:
    from app.finance.bill_payments import get_payment_candidates

    owner = await create_owner(db_session)
    bill = await setup_bill(db_session, owner)
    old_posting, _, _ = await expense(db_session, owner, 10_000, days=-31)
    assert not (await get_payment_candidates(db_session, owner, bill.id, limit=10, offset=0)).items
    page = await get_payment_candidates(
        db_session, owner, bill.id, limit=10, offset=0, include_older=True
    )
    candidate = next(item for item in page.items if item.posting_id == old_posting)
    assert {"amount_exact", "date_older_than_window", "eligible_expense"} <= set(candidate.reasons)
    searched = await get_payment_candidates(
        db_session, owner, bill.id, limit=10, offset=0, query="expense"
    )
    assert old_posting in {item.posting_id for item in searched.items}
