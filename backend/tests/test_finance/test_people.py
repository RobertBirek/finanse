"""Person assignment preserves money and rejects stale or ambiguous attribution."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.finance import service
from app.finance.categorization_context import columns
from app.finance.models import ActualImportMapping, FinancialTransaction, Posting
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.main import app  # noqa: F401 - register the full test schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def gift(db, *, currency="PLN", owner=None, amount=10000, base=10000):
    owner = owner or uuid.uuid4()
    account = await service.create_account(
        db, owner, AccountCreate(name="Bank", type="checking", currency=currency)
    )
    cat = await service.create_category(db, owner, CategoryCreate(name="Gift", type="income"))
    txn = await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            description="Source gift",
            type="income",
            transaction_date=date(2026, 1, 1),
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    source_currency=currency,
                    base_amount_pln=base,
                    fx_rate=Decimal(base) / Decimal(amount),
                    direction="credit",
                ),
                PostingCreate(
                    category_id=cat.id,
                    source_amount=amount,
                    source_currency=currency,
                    base_amount_pln=base,
                    fx_rate=Decimal(base) / Decimal(amount),
                    direction="debit",
                ),
            ],
        ),
    )
    await db.commit()
    return owner, txn, account, cat


async def person(db, owner, **kw):
    from app.finance.people import create_person
    from app.finance.person_schemas import PersonCreate
    from app.identity.models import User

    if await db.get(User, owner) is None:
        db.add(
            User(
                id=owner,
                email=f"{owner}@example.test",
                password_hash="synthetic",
                display_name="Owner",
            )
        )
        await db.flush()

    return await create_person(db, owner, PersonCreate(name="Person", **kw))


async def link(db, owner, txn_id, person_id, *, key=None, snapshot=None):
    from app.finance.people import link_gift
    from app.finance.person_context import get_person_link_context
    from app.finance.person_schemas import GiftLinkRequest

    ctx = await get_person_link_context(db, owner, txn_id)
    return await link_gift(
        db,
        owner,
        txn_id,
        GiftLinkRequest(
            person_id=person_id,
            expected_transaction_snapshot=snapshot or ctx.snapshot,
        ),
        idempotency_key=key or uuid.uuid4().hex,
    )


async def ledger(db):
    return {
        model.__tablename__: [
            columns(r)
            for r in (
                await db.scalars(
                    select(model).order_by(model.id).execution_options(populate_existing=True)
                )
            ).all()
        ]
        for model in [FinancialTransaction, Posting, ActualImportMapping]
    }


@pytest.mark.parametrize(
    "source,currency", [("manual", "PLN"), ("actual", "PLN"), ("bank_import", "EUR")]
)
async def test_link_and_unlink_preserve_ledger_provenance_balances_and_reports(
    db_session, source, currency
):
    from app.finance.people import unlink_gift
    from app.finance.person_schemas import GiftUnlinkRequest

    owner, txn, _, _ = await gift(db_session, currency=currency)
    txn.source = source
    if source == "actual":
        db_session.add(
            ActualImportMapping(
                user_id=owner, entity_type="transaction", actual_id="source-id", entity_id=txn.id
            )
        )
    await db_session.commit()
    p = await person(db_session, owner)
    before = await ledger(db_session)
    report = await service.get_financial_summary(db_session, owner, 1, 2026)
    result = await link(db_session, owner, txn.id, p.id)
    assert result.person.id == p.id
    assert await ledger(db_session) == before
    assert await service.get_financial_summary(db_session, owner, 1, 2026) == report
    unlinked = await unlink_gift(
        db_session,
        owner,
        txn.id,
        GiftUnlinkRequest(expected_transaction_snapshot=result.snapshot),
        idempotency_key="unlink",
    )
    assert unlinked.person is None
    assert await ledger(db_session) == before
    assert await service.get_financial_summary(db_session, owner, 1, 2026) == report


async def test_assignment_replay_conflict_stale_and_foreign_scope(db_session):
    from app.finance.people import PersonError
    from app.finance.person_context import get_person_link_context

    owner, txn, _, _ = await gift(db_session)
    first, second = await person(db_session, owner), await person(db_session, owner)
    before = await ledger(db_session)
    original = await get_person_link_context(db_session, owner, txn.id)
    saved = await link(db_session, owner, txn.id, first.id, key="save", snapshot=original.snapshot)
    assert (
        await link(db_session, owner, txn.id, first.id, key="save", snapshot=original.snapshot)
        == saved
    )
    for kwargs, expected in [({"key": "save"}, "idempotency"), ({}, "assigned")]:
        with pytest.raises(PersonError, match=expected):
            await link(db_session, owner, txn.id, second.id, **kwargs)
    with pytest.raises(PersonError, match="changed"):
        await link(db_session, owner, txn.id, first.id, snapshot="0" * 64)
    foreign = await person(db_session, uuid.uuid4())
    with pytest.raises(LookupError):
        await link(db_session, owner, txn.id, foreign.id)
    assert await ledger(db_session) == before


@pytest.mark.parametrize(
    "bad",
    [
        "expense_category",
        "pending",
        "expense",
        "transfer",
        "exchange",
        "refund",
        "unbalanced",
        "foreign_category",
        "document",
    ],
)
async def test_invalid_gift_is_not_reclassified_or_written(db_session, bad):
    from app.finance.people import PersonError

    owner, txn, _, cat = await gift(db_session)
    ps = list(
        (await db_session.scalars(select(Posting).where(Posting.transaction_id == txn.id))).all()
    )
    if bad == "expense_category":
        cat.type = "expense"
    elif bad == "foreign_category":
        cat.user_id = uuid.uuid4()
    elif bad == "pending":
        txn.is_pending = True
    elif bad in {"expense", "transfer", "exchange"}:
        txn.type = bad
    elif bad == "refund":
        for post in ps:
            post.direction = "debit" if post.account_id else "credit"
    elif bad == "unbalanced":
        ps[0].base_amount_pln += 1
    elif bad == "document":
        from app.finance.models import DocumentPaymentAllocation, FinancialDocument

        doc = FinancialDocument(user_id=owner)
        db_session.add(doc)
        await db_session.flush()
        db_session.add(
            DocumentPaymentAllocation(
                user_id=owner, financial_document_id=doc.id, posting_id=ps[0].id, amount_minor=100
            )
        )
    await db_session.commit()
    p = await person(db_session, owner)
    before = await ledger(db_session)
    with pytest.raises(PersonError) as caught:
        await link(db_session, owner, txn.id, p.id)
    assert caught.value.status == 422
    assert await ledger(db_session) == before


async def test_person_archive_cas_and_reference_account_validation(db_session):
    from app.finance.people import PersonError, update_person
    from app.finance.person_schemas import PersonUpdate

    owner, txn, bank, _ = await gift(db_session)
    with pytest.raises(PersonError):
        await person(db_session, owner, reference_account_id=bank.id)
    ref = await service.create_account(
        db_session, owner, AccountCreate(name="Reference", type="checking", is_budget_account=False)
    )
    p = await person(db_session, owner, reference_account_id=ref.id)
    ctx = await link(db_session, owner, txn.id, p.id)
    archived = await update_person(
        db_session, owner, p.id, PersonUpdate(expected_version=p.version, is_active=False)
    )
    assert not archived.is_active and archived.version == 2
    with pytest.raises(PersonError):
        await update_person(db_session, owner, p.id, PersonUpdate(expected_version=1, name="Stale"))
    # Archival must not trap existing gifts: owner may still unlink.
    from app.finance.people import unlink_gift
    from app.finance.person_schemas import GiftUnlinkRequest

    assert (
        await unlink_gift(
            db_session,
            owner,
            txn.id,
            GiftUnlinkRequest(expected_transaction_snapshot=ctx.snapshot),
            idempotency_key="unlink",
        )
    ).person is None
    with pytest.raises(PersonError, match="inactive"):
        await link(db_session, owner, txn.id, p.id)


async def test_concurrent_gift_assignment_has_one_winner(db_session, test_database):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.finance.people import PersonError
    from app.finance.person_context import get_person_link_context
    from app.finance.person_models import PersonTransactionLink

    owner, txn, _, _ = await gift(db_session)
    first, second = await person(db_session, owner), await person(db_session, owner)
    ctx = await get_person_link_context(db_session, owner, txn.id)
    txn_id = txn.id
    await db_session.commit()
    factory = async_sessionmaker(test_database, expire_on_commit=False)

    async def assign(person_id):
        async with factory() as db:
            try:
                result = await link(db, owner, txn_id, person_id, snapshot=ctx.snapshot)
                await db.commit()
                return result
            except PersonError as error:
                await db.rollback()
                return error

    results = await asyncio.wait_for(asyncio.gather(assign(first.id), assign(second.id)), 15)
    assert sum(isinstance(value, PersonError) for value in results) == 1
    links = list((await db_session.scalars(select(PersonTransactionLink))).all())
    assert len(links) == 1


async def test_loan_payment_reference_cannot_be_attributed_as_gift(db_session):
    from app.finance.models import LoanAgreement, LoanInstallment, LoanPaymentLink
    from app.finance.people import PersonError

    owner, txn, bank, _ = await gift(db_session)
    debt = await service.create_account(
        db_session, owner, AccountCreate(name="Debt", type="credit")
    )
    agreement = LoanAgreement(
        user_id=owner, name="Synthetic", account_id=debt.id, payment_account_id=bank.id
    )
    db_session.add(agreement)
    await db_session.flush()
    installment = LoanInstallment(
        user_id=owner,
        loan_id=agreement.id,
        number=1,
        due_date=date(2026, 1, 1),
        principal_pln=10000,
        interest_pln=0,
        fees_pln=0,
    )
    db_session.add(installment)
    await db_session.flush()
    db_session.add(
        LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=txn.id)
    )
    await db_session.commit()
    p = await person(db_session, owner)
    with pytest.raises(PersonError) as error:
        await link(db_session, owner, txn.id, p.id)
    assert error.value.status == 422
