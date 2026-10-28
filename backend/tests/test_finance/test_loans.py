"""First-slice loan schedule contracts; linked ledger rows remain immutable."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance import service
from app.finance.loan_schemas import (
    LoanCreate,
    LoanInstallmentCreate,
    LoanInstallmentUpdate,
    LoanUpdate,
)
from app.finance.models import FinancialTransaction, LoanPaymentLink, Posting
from app.finance.schemas import AccountCreate, PostingCreate, TransactionCreate, TransactionUpdate
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_loan_installment_reports_planned_components_without_ledger_mutation(
    db_session,
) -> None:
    """A plan is not a financial transaction or a recognized cost."""
    owner = uuid.uuid4()
    debt = await service.create_account(
        db_session, owner, AccountCreate(name="Debt", type="credit")
    )
    payer = await service.create_account(
        db_session, owner, AccountCreate(name="Payer", type="checking")
    )

    loan = await service.create_loan(
        db_session,
        owner,
        LoanCreate(name="Audi Q7", account_id=debt.id, payment_account_id=payer.id),
    )
    installment = await service.create_loan_installment(
        db_session,
        owner,
        loan.id,
        LoanInstallmentCreate(
            number=1,
            due_date=date(2026, 11, 1),
            principal_pln=90_000,
            interest_pln=9_000,
            fees_pln=1_000,
        ),
    )

    detail = await service.get_loan(db_session, owner, loan.id)

    assert detail is not None
    assert installment.id == detail.installments[0].id
    assert detail.total_planned_pln == 100_000
    assert detail.paid_pln == 0
    assert detail.remaining_pln == 100_000
    assert detail.installments[0].total_pln == 100_000
    assert detail.installments[0].payment_status == "unpaid"
    assert detail.requires_accounting_review is True


async def test_linked_transfer_is_partial_idempotent_and_immutable(db_session) -> None:
    owner = uuid.uuid4()
    debt = await service.create_account(
        db_session, owner, AccountCreate(name="Debt", type="credit")
    )
    payer = await service.create_account(
        db_session, owner, AccountCreate(name="Payer", type="checking")
    )
    loan = await service.create_loan(
        db_session, owner, LoanCreate(name="Q7", account_id=debt.id, payment_account_id=payer.id)
    )
    installment = await service.create_loan_installment(
        db_session,
        owner,
        loan.id,
        LoanInstallmentCreate(
            number=1, due_date=date(2026, 1, 1), principal_pln=100_000, interest_pln=0, fees_pln=0
        ),
    )
    transaction = await service.create_transaction(
        db_session,
        owner,
        TransactionCreate(
            description="loan transfer",
            type="transfer",
            transaction_date=date(2026, 1, 1),
            postings=[
                PostingCreate(
                    account_id=payer.id,
                    source_amount=40_000,
                    base_amount_pln=40_000,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=debt.id,
                    source_amount=40_000,
                    base_amount_pln=40_000,
                    direction="credit",
                ),
            ],
        ),
    )

    detail = await service.link_loan_payment(
        db_session, owner, loan.id, installment.id, transaction.id
    )
    repeated = await service.link_loan_payment(
        db_session, owner, loan.id, installment.id, transaction.id
    )

    assert detail is not None and repeated is not None
    assert detail.installments[0].paid_pln == 40_000
    assert detail.installments[0].remaining_pln == 60_000
    with pytest.raises(ValueError, match="linked loan payment"):
        await service.update_transaction(
            db_session, owner, transaction.id, TransactionUpdate(is_pending=True)
        )
    with pytest.raises(ValueError, match="linked loan payment"):
        await service.delete_transaction(db_session, owner, transaction.id)


async def setup_loan(db: AsyncSession):
    owner = uuid.uuid4()
    debt = await service.create_account(db, owner, AccountCreate(name="Debt", type="credit"))
    payer = await service.create_account(db, owner, AccountCreate(name="Payer", type="checking"))
    loan = await service.create_loan(
        db,
        owner,
        LoanCreate(name="Synthetic loan", account_id=debt.id, payment_account_id=payer.id),
    )
    installment = await service.create_loan_installment(
        db,
        owner,
        loan.id,
        LoanInstallmentCreate(
            number=1,
            due_date=date(2026, 1, 1),
            principal_pln=90_000,
            interest_pln=9_000,
            fees_pln=1_000,
        ),
    )
    return owner, debt, payer, loan, installment


async def transfer(db, owner, debt, payer, amount, **kwargs):
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            type="transfer",
            transaction_date=date(2026, 1, 1),
            description="Existing payment",
            postings=[
                PostingCreate(
                    account_id=payer.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=debt.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
            **kwargs,
        ),
    )


async def ledger_snapshot(db):
    return [
        tuple(row)
        for table in (FinancialTransaction.__table__, Posting.__table__)
        for row in (await db.execute(select(table).order_by(table.c.id))).all()
    ]


async def test_full_link_unlink_preserves_every_ledger_column(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    first = await transfer(db_session, owner, debt, payer, 40_000)
    second = await transfer(db_session, owner, debt, payer, 60_000)
    extra = await transfer(db_session, owner, debt, payer, 1)
    before = await ledger_snapshot(db_session)
    for transaction in (first, second):
        detail = await service.link_loan_payment(
            db_session, owner, loan.id, installment.id, transaction.id
        )
    assert detail.installments[0].payment_status == "paid"
    assert detail.remaining_pln == 0
    with pytest.raises(ValueError, match="exceeds"):
        await service.link_loan_payment(db_session, owner, loan.id, installment.id, extra.id)
    with pytest.raises(ValueError, match="linked"):
        await service.update_loan_installment(
            db_session, owner, loan.id, installment.id, LoanInstallmentUpdate(principal_pln=200_000)
        )
    with pytest.raises(ValueError, match="linked"):
        await service.delete_loan_installment(db_session, owner, loan.id, installment.id)
    assert await service.unlink_loan_payment(
        db_session, owner, loan.id, detail.installments[0].payments[0].id
    )
    assert (await service.get_loan(db_session, owner, loan.id)).installments[
        0
    ].payment_status == "partial"
    assert await ledger_snapshot(db_session) == before


async def test_linked_transfer_allows_effectively_unchanged_date_and_pending(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 40_000)
    await service.link_loan_payment(db_session, owner, loan.id, installment.id, payment.id)
    result = await service.update_transaction(
        db_session,
        owner,
        payment.id,
        TransactionUpdate(
            transaction_date=payment.date, is_pending=False, description="Clarified description"
        ),
    )
    assert result.description == "Clarified description"


@pytest.mark.parametrize("linked", [False, True])
async def test_transaction_patch_returns_eagerly_loaded_postings(db_session, linked):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 40_000)
    if linked:
        await service.link_loan_payment(db_session, owner, loan.id, installment.id, payment.id)
    async with client_for(db_session, owner) as client:
        response = await client.patch(
            f"/api/finance/transactions/{payment.id}", json={"description": "Clarified"}
        )
    assert response.status_code == 200
    assert len(response.json()["postings"]) == 2


@pytest.mark.parametrize("kind", ["pending", "future", "reverse", "fx", "currency"])
async def test_ineligible_existing_transfers_are_not_candidates_or_linkable(db_session, kind):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 40_000)
    await db_session.refresh(payment, ["postings"])
    if kind == "pending":
        payment.is_pending = True
    elif kind == "future":
        payment.date = date(2099, 1, 1)
    elif kind == "reverse":
        for p in payment.postings:
            p.direction = "credit" if p.direction == "debit" else "debit"
    elif kind == "fx":
        payment.postings[0].fx_rate = 2
    else:
        payment.postings[0].source_currency = "EUR"
    await db_session.flush()
    result = await service.get_loan_payment_candidates(
        db_session, owner, loan.id, installment.id, 20, 0
    )
    assert result.total == 0
    with pytest.raises(ValueError, match="eligible"):
        await service.link_loan_payment(db_session, owner, loan.id, installment.id, payment.id)


async def test_candidates_paginate_and_linked_transfer_cannot_cover_another_installment(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payments = [await transfer(db_session, owner, debt, payer, 10_000) for _ in range(3)]
    pages = [
        await service.get_loan_payment_candidates(
            db_session, owner, loan.id, installment.id, 2, offset
        )
        for offset in (0, 2)
    ]
    assert pages[0].total == pages[1].total == 3
    assert {p.transaction_id for page in pages for p in page.items} == {p.id for p in payments}
    await service.link_loan_payment(db_session, owner, loan.id, installment.id, payments[0].id)
    other = await service.create_loan_installment(
        db_session,
        owner,
        loan.id,
        LoanInstallmentCreate(
            number=2, due_date=date(2026, 2, 1), principal_pln=100_000, interest_pln=0, fees_pln=0
        ),
    )
    with pytest.raises(ValueError, match="already linked"):
        await service.link_loan_payment(db_session, owner, loan.id, other.id, payments[0].id)
    result = await service.get_loan_payment_candidates(db_session, owner, loan.id, other.id, 20, 0)
    assert result.total == 2


async def test_api_ownership_conflicts_and_archived_account_guards(db_session):
    owner, debt, payer, loan, _installment = await setup_loan(db_session)
    async with client_for(db_session, uuid.uuid4()) as client:
        assert (await client.get(f"/api/finance/loans/{loan.id}")).status_code == 404
        assert (
            await client.patch(f"/api/finance/loans/{loan.id}", json={"name": "Stolen"})
        ).status_code == 404
        response = await client.post(
            "/api/finance/loans",
            json={
                "name": "Foreign",
                "account_id": str(debt.id),
                "payment_account_id": str(payer.id),
            },
        )
        assert response.status_code == 404
    await service.update_loan(db_session, owner, loan.id, LoanUpdate(is_active=False))
    async with client_for(db_session, owner) as client:
        for account in (debt, payer):
            response = await client.get(f"/api/finance/accounts/{account.id}")
            assert response.json()["can_change_currency"] is False
            assert (
                await client.patch(f"/api/finance/accounts/{account.id}", json={"currency": "EUR"})
            ).status_code == 409
            assert (await client.delete(f"/api/finance/accounts/{account.id}")).status_code == 409


async def test_api_duplicate_is_safe_conflict_without_sql_details(db_session):
    owner, _debt, _payer, loan, _installment = await setup_loan(db_session)
    async with client_for(db_session, owner) as client:
        response = await client.post(
            f"/api/finance/loans/{loan.id}/installments",
            json={
                "number": 1,
                "due_date": "2026-01-01",
                "principal_pln": 100,
                "interest_pln": 0,
                "fees_pln": 0,
            },
        )
    assert response.status_code == 409
    assert "INSERT" not in response.text
    assert "asyncpg" not in response.text


@pytest.mark.parametrize("first", ["link", "edit", "delete"])
async def test_link_and_transaction_mutations_serialize(db_session, first):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 40_000)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as one, sessions() as two:
        if first == "link":
            await service.link_loan_payment(one, owner, loan.id, installment.id, payment.id)
        elif first == "edit":
            await service.update_transaction(
                one, owner, payment.id, TransactionUpdate(is_pending=True)
            )
        else:
            await service.delete_transaction(one, owner, payment.id)
        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            if first == "link":
                await service.delete_transaction(two, owner, payment.id)
            else:
                await service.link_loan_payment(two, owner, loan.id, installment.id, payment.id)
        await two.rollback()
        await one.commit()
        with pytest.raises((ValueError, LookupError)):
            if first == "link":
                await service.delete_transaction(two, owner, payment.id)
            else:
                await service.link_loan_payment(two, owner, loan.id, installment.id, payment.id)


async def test_concurrent_payments_cannot_overfill_installment(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    first = await transfer(db_session, owner, debt, payer, 60_000)
    second = await transfer(db_session, owner, debt, payer, 60_000)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as one, sessions() as two:
        # Keep a stale identity map in the second connection as well.
        await service.get_loan(two, owner, loan.id)
        await service.link_loan_payment(one, owner, loan.id, installment.id, first.id)
        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            await service.link_loan_payment(two, owner, loan.id, installment.id, second.id)
        await two.rollback()
        await one.commit()
        with pytest.raises(ValueError, match="exceeds"):
            await service.link_loan_payment(two, owner, loan.id, installment.id, second.id)
        assert len((await two.scalars(select(LoanPaymentLink))).all()) == 1


async def test_link_refreshes_previously_cached_installment_total(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 60_000)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as reader, sessions() as changer:
        from app.finance.models import LoanInstallment

        cached = await reader.get(LoanInstallment, installment.id)
        assert cached.principal_pln == 90_000
        await service.update_loan_installment(
            changer, owner, loan.id, installment.id, LoanInstallmentUpdate(principal_pln=30_000)
        )
        await changer.commit()
        with pytest.raises(ValueError, match="exceeds"):
            await service.link_loan_payment(reader, owner, loan.id, installment.id, payment.id)


async def test_unlink_uses_the_same_loan_serialization_as_link(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 40_000)
    detail = await service.link_loan_payment(db_session, owner, loan.id, installment.id, payment.id)
    link_id = detail.installments[0].payments[0].id
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as one, sessions() as two:
        # Creating a different installment holds only the agreement row.
        await service.create_loan_installment(
            one,
            owner,
            loan.id,
            LoanInstallmentCreate(
                number=2, due_date=date(2026, 2, 1), principal_pln=1, interest_pln=0, fees_pln=0
            ),
        )
        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            await service.unlink_loan_payment(two, owner, loan.id, link_id)
        await two.rollback()
        await one.commit()
        assert await service.unlink_loan_payment(two, owner, loan.id, link_id)


@pytest.mark.parametrize("first", ["loan", "currency"])
async def test_empty_loan_creation_and_currency_change_serialize(db_session, first):
    from app.finance.schemas import AccountUpdate

    owner = uuid.uuid4()
    debt = await service.create_account(
        db_session, owner, AccountCreate(name="Debt", type="credit")
    )
    payer = await service.create_account(
        db_session, owner, AccountCreate(name="Payer", type="checking")
    )
    data = LoanCreate(name="Loan", account_id=debt.id, payment_account_id=payer.id)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as one, sessions() as two:
        if first == "loan":
            await service.create_loan(one, owner, data)
        else:
            await service.update_account(one, owner, payer.id, AccountUpdate(currency="EUR"))
        await two.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(DBAPIError, match="lock timeout"):
            if first == "loan":
                await service.update_account(two, owner, payer.id, AccountUpdate(currency="EUR"))
            else:
                await service.create_loan(two, owner, data)
        await two.rollback()
        await one.commit()
        with pytest.raises(ValueError):
            if first == "loan":
                await service.update_account(two, owner, payer.id, AccountUpdate(currency="EUR"))
            else:
                await service.create_loan(two, owner, data)


async def test_api_complete_metadata_workflow_and_owner_scope(db_session):
    owner, debt, payer, loan, installment = await setup_loan(db_session)
    payment = await transfer(db_session, owner, debt, payer, 100_000)
    before = await ledger_snapshot(db_session)
    summary_before = (
        await service.get_financial_summary(db_session, owner, month=1, year=2026)
    ).model_dump()
    path = f"/api/finance/loans/{loan.id}"
    async with client_for(db_session, owner) as client:
        assert (await client.get("/api/finance/loans")).json()[0]["id"] == str(loan.id)
        assert (await client.patch(path, json={"name": "Renamed"})).json()["name"] == "Renamed"
        result = await client.get(f"{path}/installments/{installment.id}/payment-candidates")
        assert result.status_code == 200 and result.json()["total"] == 1
        result = await client.post(
            f"{path}/installments/{installment.id}/payments",
            json={"transaction_id": str(payment.id)},
        )
        assert result.status_code == 200 and result.json()["paid_pln"] == 100_000
        link_id = result.json()["installments"][0]["payments"][0]["id"]
        assert (
            await client.patch(f"/api/finance/transactions/{payment.id}", json={"is_pending": True})
        ).status_code == 409
        assert (await client.delete(f"/api/finance/transactions/{payment.id}")).status_code == 409
    async with client_for(db_session, uuid.uuid4()) as client:
        checks = [
            await client.patch(f"{path}/installments/{installment.id}", json={"number": 3}),
            await client.delete(f"{path}/installments/{installment.id}"),
            await client.post(
                f"{path}/installments",
                json={
                    "number": 2,
                    "due_date": "2026-02-01",
                    "principal_pln": 1,
                    "interest_pln": 0,
                    "fees_pln": 0,
                },
            ),
            await client.get(f"{path}/installments/{installment.id}/payment-candidates"),
            await client.post(
                f"{path}/installments/{installment.id}/payments",
                json={"transaction_id": str(payment.id)},
            ),
            await client.delete(f"{path}/payments/{link_id}"),
        ]
        assert all(response.status_code == 404 for response in checks)
    async with client_for(db_session, owner) as client:
        assert (await client.delete(f"{path}/payments/{link_id}")).status_code == 204
        assert (
            await client.patch(
                f"{path}/installments/{installment.id}", json={"principal_pln": 80_000}
            )
        ).json()["total_pln"] == 90_000
        assert (await client.delete(f"{path}/installments/{installment.id}")).status_code == 204
    assert await ledger_snapshot(db_session) == before
    assert (
        await service.get_financial_summary(db_session, owner, month=1, year=2026)
    ).model_dump() == summary_before
