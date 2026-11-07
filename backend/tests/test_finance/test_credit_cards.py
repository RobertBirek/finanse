"""Real PostgreSQL/API regressions for card limits, costs and plan classification."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.finance import service
from app.finance.models import FinancialTransaction, Posting
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    PostingCreate,
    TransactionCreate,
    TransactionUpdate,
)
from tests.test_finance.test_account_currency import client_for

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
BASE = "/api/finance/accounts/{}/credit-card"


async def setup(db):
    owner = uuid.uuid4()
    from app.identity.models import User

    db.add(
        User(
            id=owner,
            email=f"{owner}@example.test",
            password_hash="test-only",
            display_name="Card owner",
        )
    )
    await db.flush()
    account = await service.create_account(
        db, owner, AccountCreate(name="VELOBANK - karta", type="checking")
    )
    payer = await service.create_account(db, owner, AccountCreate(name="Payer", type="checking"))
    category = await service.create_category(
        db, owner, CategoryCreate(name="Interest", type="expense")
    )
    return owner, account, payer, category


def config(**changes):
    return dict(
        limit_pln=3360000,
        apr="14.50",
        cycle_close_day=17,
        due_day=12,
        grace_days=57,
        expected_version=0,
        **changes,
    )


async def debit(db, owner, account, category, amount=100000):
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            description="purchase",
            type="expense",
            transaction_date=date(2026, 10, 1),
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        ),
    )


async def payment(db, owner, account, payer, amount=50000):
    return await service.create_transaction(
        db,
        owner,
        TransactionCreate(
            description="repayment",
            type="transfer",
            transaction_date=date(2026, 11, 5),
            postings=[
                PostingCreate(
                    account_id=payer.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        ),
    )


def plan(source, **changes):
    return dict(
        request_id=str(uuid.uuid4()),
        name="New Komfort",
        source_transaction_id=str(source.id),
        principal_pln=100000,
        apr="10.99",
        count=10,
        first_due="2026-11-12",
        fees_pln=100,
        **changes,
    )


async def test_config_existing_account_and_owner_access_limits_and_pending(db_session):
    owner, card, payer, category = await setup(db_session)
    purchase = await debit(db_session, owner, card, category)
    hold = await debit(db_session, owner, card, category, 10000)
    await service.update_transaction(db_session, owner, hold.id, TransactionUpdate(is_pending=True))
    pending_credit = await payment(db_session, owner, card, payer, 5000)
    await service.update_transaction(
        db_session, owner, pending_credit.id, TransactionUpdate(is_pending=True)
    )
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        assert (await client.get(url)).status_code == 404
        response = await client.put(url, json=config())
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["debt_pln"] == 100000
        assert data["pending_debits_pln"] == 10000
        assert data["available_pln"] == 3250000
        assert data["version"] == 1
        stale = await client.put(url, json=config())
        assert stale.status_code == 409
        assert (
            await client.patch(f"/api/finance/accounts/{card.id}", json={"currency": "EUR"})
        ).status_code == 409
        assert (
            await client.patch(f"/api/finance/accounts/{card.id}", json={"type": "cash"})
        ).status_code == 409
        assert (await client.delete(f"/api/finance/accounts/{card.id}")).status_code == 409
    async with client_for(db_session, uuid.uuid4()) as client:
        assert (await client.get(url)).status_code == 404
        assert (await client.put(url, json=config())).status_code == 404
    assert purchase.id is not None


async def test_plan_does_not_add_debt_or_postings_and_has_independent_rate(db_session):
    owner, card, _, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        payload = plan(source)
        response = await client.post(url + "/plans", json=payload)
        assert response.status_code == 201, response.text
        item = response.json()
        assert str(item["apr"]) == "10.9900"
        assert item["schedule_kind"] == "estimated"
        assert sum(r["principal_pln"] for r in item["installments"]) == 100000
        repeated = await client.post(url + "/plans", json=payload)
        assert repeated.json()["id"] == item["id"]
        assert (await client.post(url + "/plans", json={**payload, "apr": "12"})).status_code == 409
        assert (await client.post(url + "/plans", json=plan(source))).status_code == 409
        data = (await client.get(url)).json()
        assert data["debt_pln"] == 100000
        assert data["available_pln"] == 3260000
        assert data["plans"][0]["remaining_principal_pln"] == 100000
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == 2


async def test_bank_schedule_replaces_estimate_without_mutating_ledger(db_session):
    owner, card, _, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
        rows = [
            {
                "number": 1,
                "due_date": "2026-11-12",
                "principal_pln": 40000,
                "interest_pln": 700,
                "fees_pln": 100,
            },
            {
                "number": 2,
                "due_date": "2026-12-12",
                "principal_pln": 60000,
                "interest_pln": 400,
                "fees_pln": 0,
            },
        ]
        changed = await client.put(
            url + f"/plans/{item['id']}/schedule",
            json={"expected_version": 1, "installments": rows},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["schedule_kind"] == "bank"
        assert changed.json()["version"] == 2
        assert (
            await client.put(
                url + f"/plans/{item['id']}/schedule",
                json={"expected_version": 2, "installments": rows[:1]},
            )
        ).status_code == 422
        assert (await client.get(url)).json()["debt_pln"] == 100000


async def test_statement_is_historical_reconciles_and_uses_actual_due_date(db_session):
    owner, card, payer, category = await setup(db_session)
    await debit(db_session, owner, card, category)
    transfer = await payment(db_session, owner, card, payer)
    url = BASE.format(card.id)
    statement = {
        "request_id": str(uuid.uuid4()),
        "period_start": "2026-09-18",
        "period_end": "2026-10-17",
        "due_date": "2026-11-13",
        "debt_pln": 100000,
        "minimum_pln": 3000,
        "source_reference": "bank statement",
    }
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        response = await client.post(url + "/statements", json=statement)
        assert response.status_code == 201, response.text
        item = response.json()
        assert item["reconciliation_difference_pln"] == 0
        assert item["due_date"] == "2026-11-13"
        assert (await client.get(url)).json()["debt_pln"] == 50000
        allocation = {
            "request_id": str(uuid.uuid4()),
            "transaction_id": str(transfer.id),
            "statement_id": item["id"],
            "amount_pln": 50000,
        }
        result = await client.post(url + "/allocations", json=allocation)
        assert result.status_code == 201, result.text
        assert (await client.post(url + "/allocations", json=allocation)).json()[
            "id"
        ] == result.json()["id"]
        item = (await client.get(url)).json()["statements"][0]
        assert item["remaining_pln"] == 50000
        assert item["minimum_remaining_pln"] == 0
        assert (
            await client.post(
                url + "/allocations", json={**allocation, "request_id": str(uuid.uuid4())}
            )
        ).status_code == 409
    with pytest.raises(ValueError, match="card"):
        await service.delete_transaction(db_session, owner, transfer.id)


async def test_partial_and_early_repayment_closes_principal_without_future_costs(db_session):
    owner, card, payer, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    first = await payment(db_session, owner, card, payer, 40000)
    second = await payment(db_session, owner, card, payer, 60000)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
        for txn, amount, remaining in [(first, 40000, 60000), (second, 60000, 0)]:
            payload = {
                "request_id": str(uuid.uuid4()),
                "transaction_id": str(txn.id),
                "plan_id": item["id"],
                "amount_pln": amount,
                "principal_pln": amount,
            }
            response = await client.post(url + "/allocations", json=payload)
            assert response.status_code == 201, response.text
            data = (await client.get(url)).json()
            assert data["plans"][0]["remaining_principal_pln"] == remaining
        assert data["plans"][0]["status"] == "closed"
        assert data["debt_pln"] == 0
        assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 3
        attempt = await client.put(
            url + f"/plans/{item['id']}/schedule",
            json={"expected_version": 1, "installments": item["installments"]},
        )
        assert attempt.status_code == 409


async def test_charges_refunds_idempotency_and_net_expense_reporting(db_session):
    owner, card, _, category = await setup(db_session)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        expense = {
            "request_id": str(uuid.uuid4()),
            "kind": "interest",
            "amount_pln": 507,
            "category_id": str(category.id),
            "booking_date": "2026-11-07",
            "description": "Bank interest",
        }
        created = await client.post(url + "/charges", json=expense)
        assert created.status_code == 201, created.text
        assert (await client.post(url + "/charges", json=expense)).json()["id"] == created.json()[
            "id"
        ]
        correction = await client.post(
            url + "/charges",
            json={
                **expense,
                "request_id": str(uuid.uuid4()),
                "kind": "interest_refund",
                "amount_pln": 141,
            },
        )
        assert correction.status_code == 201, correction.text
        assert (await client.get(url)).json()["debt_pln"] == 366
    report = await service.get_financial_summary(db_session, owner, month=11, year=2026)
    assert report.expense_total_pln == 366
    assert report.income_total_pln == 0
    rows = (await db_session.execute(select(Posting))).scalars().all()
    assert (
        sum(p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln for p in rows) == 0
    )
    assert len(rows) == 4


async def test_foreign_sources_and_wrong_currency_are_rejected(db_session):
    owner, card, _, _category = await setup(db_session)
    other_owner, other_card, _, other_category = await setup(db_session)
    source = await debit(db_session, other_owner, other_card, other_category)
    euro = await service.create_account(
        db_session, owner, AccountCreate(name="EUR", type="credit", currency="EUR")
    )
    async with client_for(db_session, owner) as client:
        assert (await client.put(BASE.format(euro.id), json=config())).status_code == 422
        await client.put(BASE.format(card.id), json=config())
        assert (
            await client.post(BASE.format(card.id) + "/plans", json=plan(source))
        ).status_code == 422


async def test_profile_edit_is_versioned_audited_and_estimate_never_books(db_session):
    owner, card, _, _ = await setup(db_session)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        changed = await client.put(url, json={**config(), "expected_version": 1, "apr": "12.25"})
        assert changed.status_code == 200, changed.text
        assert changed.json()["version"] == 2
        assert changed.json()["apr"] == "12.2500"
        estimated = await client.post(
            url + "/interest-estimate", json={"principal_pln": 100000, "apr": "14.50", "days": 30}
        )
        assert estimated.json() == {
            "estimated_interest_pln": 1192,
            "method": "simple_ACT_365",
            "is_estimate": True,
            "grace_period_assessed": False,
        }
        overflow = await client.post(
            url + "/interest-estimate",
            json={"principal_pln": 9007199254740991, "apr": "100", "days": 3660},
        )
        assert overflow.status_code == 422
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0


async def test_existing_charge_link_does_not_double_book_and_protects_dates(db_session):
    owner, card, _, category = await setup(db_session)
    txn = await debit(db_session, owner, card, category, 507)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        payload = {
            "request_id": str(uuid.uuid4()),
            "kind": "interest",
            "amount_pln": 507,
            "category_id": str(category.id),
            "booking_date": "2026-10-01",
            "description": "Existing interest",
            "existing_transaction_id": str(txn.id),
        }
        response = await client.post(url + "/charges", json=payload)
        assert response.status_code == 201, response.text
        assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1
        assert (
            await client.patch(f"/api/finance/transactions/{txn.id}", json={"is_pending": True})
        ).status_code == 409
        assert (
            await client.post(url + "/plans", json={**plan(txn), "principal_pln": 507, "count": 1})
        ).status_code == 409
        # The explicit date editor cannot bypass the same source lock.
        response = await client.patch(
            f"/api/finance/transactions/{txn.id}/dates",
            json={
                "booking_date": "2026-10-02",
                "purchase_date": "2026-10-01",
                "expected_version": 0,
                "expected_updated_at": txn.updated_at.isoformat(),
            },
        )
        assert response.status_code == 409


async def test_same_transfer_can_explain_statement_and_plan_but_not_two_plans_twice(db_session):
    owner, card, payer, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    transfer = await payment(db_session, owner, card, payer)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
        statement = (
            await client.post(
                url + "/statements",
                json={
                    "request_id": str(uuid.uuid4()),
                    "period_start": "2026-09-18",
                    "period_end": "2026-10-17",
                    "due_date": "2026-11-12",
                    "debt_pln": 100000,
                    "minimum_pln": 3000,
                    "source_reference": "bank",
                },
            )
        ).json()
        common = {"transaction_id": str(transfer.id), "amount_pln": 50000}
        allocated = await client.post(
            url + "/allocations",
            json={
                **common,
                "request_id": str(uuid.uuid4()),
                "plan_id": item["id"],
                "principal_pln": 50000,
            },
        )
        assert allocated.status_code == 201, allocated.text
        assert (
            await client.post(
                url + "/allocations",
                json={**common, "request_id": str(uuid.uuid4()), "statement_id": statement["id"]},
            )
        ).status_code == 201
        assert (await client.get(url)).json()["debt_pln"] == 50000
        assert (
            await client.delete(url + "/allocations/" + allocated.json()["id"])
        ).status_code == 204
        assert (await client.get(url)).json()["plans"][0]["remaining_principal_pln"] == 100000


async def test_concurrent_payment_allocations_cannot_consume_one_transfer_twice(
    db_session, test_database
):
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.finance.credit_card_schemas import AllocationCreate
    from app.finance.credit_cards import CardConflict, allocate

    owner, card, payer, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    txn = await payment(db_session, owner, card, payer)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
    await db_session.commit()
    factory = async_sessionmaker(test_database, expire_on_commit=False)

    async def attempt():
        async with factory() as session, session.begin():
            try:
                await allocate(
                    session,
                    owner,
                    card.id,
                    AllocationCreate(
                        request_id=uuid.uuid4(),
                        transaction_id=txn.id,
                        plan_id=item["id"],
                        amount_pln=50000,
                        principal_pln=50000,
                    ),
                )
                return "allocated"
            except CardConflict:
                return "conflict"

    assert sorted(await asyncio.gather(attempt(), attempt())) == ["allocated", "conflict"]


async def test_foreign_payment_targets_and_pending_payments_cannot_be_allocated(db_session):
    owner, card, payer, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    txn = await payment(db_session, owner, card, payer)
    await service.update_transaction(db_session, owner, txn.id, TransactionUpdate(is_pending=True))
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
        allocation = {
            "request_id": str(uuid.uuid4()),
            "plan_id": item["id"],
            "transaction_id": str(txn.id),
            "amount_pln": 50000,
            "principal_pln": 50000,
        }
        assert (await client.post(url + "/allocations", json=allocation)).status_code == 422
        assert (await client.get(url + "/candidates?kind=payment")).json()["items"] == []
    async with client_for(db_session, uuid.uuid4()) as client:
        assert (await client.post(url + "/allocations", json=allocation)).status_code == 404


async def test_mistaken_unpaid_metadata_can_be_removed_without_deleting_ledger(db_session):
    owner, card, _, category = await setup(db_session)
    source = await debit(db_session, owner, card, category)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        item = (await client.post(url + "/plans", json=plan(source))).json()
        removed = await client.delete(url + "/plans/" + item["id"])
        assert removed.status_code == 204, removed.text
        assert (await client.get(url)).json()["debt_pln"] == 100000
        assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1


async def test_review_refund_remains_a_cost_correction_in_type_based_queries(db_session):
    owner, card, _, category = await setup(db_session)
    url = BASE.format(card.id)
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        response = await client.post(
            url + "/charges",
            json={
                "request_id": str(uuid.uuid4()),
                "kind": "interest_refund",
                "amount_pln": 141,
                "category_id": str(category.id),
                "booking_date": "2026-11-07",
                "description": "Interest correction",
            },
        )
        assert response.status_code == 201, response.text
    assert await service.get_transactions(db_session, owner, txn_type="income") == []
    costs = await service.get_transactions(db_session, owner, txn_type="expense")
    assert len(costs) == 1
    assert next(p for p in costs[0].postings if p.account_id == card.id).direction == "credit"


@pytest.mark.parametrize("as_payer", [False, True])
async def test_review_loan_and_card_models_cannot_share_either_loan_account(db_session, as_payer):
    from app.finance.loan_schemas import LoanCreate

    owner, card, payer, _ = await setup(db_session)
    loan = LoanCreate(
        name="Existing loan",
        account_id=payer.id if as_payer else card.id,
        payment_account_id=card.id if as_payer else payer.id,
    )
    await service.create_loan(db_session, owner, loan)
    async with client_for(db_session, owner) as client:
        response = await client.put(BASE.format(card.id), json=config())
        assert response.status_code == 422, response.text
    owner2, card2, payer2, _ = await setup(db_session)
    async with client_for(db_session, owner2) as client:
        assert (await client.put(BASE.format(card2.id), json=config())).status_code == 200
    with pytest.raises(ValueError, match="card"):
        await service.create_loan(
            db_session,
            owner2,
            LoanCreate(
                name="New loan",
                account_id=payer2.id if as_payer else card2.id,
                payment_account_id=card2.id if as_payer else payer2.id,
            ),
        )


async def test_review_card_source_string_alone_cannot_enable_a_refund(db_session):
    owner, card, _, category = await setup(db_session)
    with pytest.raises(ValueError, match="direction"):
        await service.create_transaction(
            db_session,
            owner,
            TransactionCreate(
                type="expense",
                source="credit_card",
                description="untrusted reversal",
                postings=[
                    PostingCreate(
                        account_id=card.id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="credit",
                    ),
                    PostingCreate(
                        category_id=category.id,
                        source_amount=100,
                        base_amount_pln=100,
                        direction="debit",
                    ),
                ],
            ),
        )


async def test_removed_charge_metadata_cannot_replay_a_booking_with_the_old_request_key(db_session):
    owner, card, _, category = await setup(db_session)
    url = BASE.format(card.id)
    payload = {
        "request_id": str(uuid.uuid4()),
        "kind": "interest",
        "amount_pln": 507,
        "category_id": str(category.id),
        "booking_date": "2026-11-07",
        "description": "Bank interest",
    }
    async with client_for(db_session, owner) as client:
        await client.put(url, json=config())
        created = await client.post(url + "/charges", json=payload)
        assert created.status_code == 201, created.text
        assert (await client.delete(url + "/charges/" + created.json()["id"])).status_code == 204
        retry = await client.post(url + "/charges", json=payload)
        assert retry.status_code == 409, retry.text
        assert (await client.get(url)).json()["debt_pln"] == 507
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1


async def test_foreign_statement_id_does_not_reveal_whether_it_has_allocations(db_session):
    owner, card, _, _ = await setup(db_session)
    other, other_card, payer, category = await setup(db_session)
    await debit(db_session, other, other_card, category)
    txn = await payment(db_session, other, other_card, payer)
    foreign_url = BASE.format(other_card.id)
    async with client_for(db_session, other) as client:
        await client.put(foreign_url, json=config())
        statement = (
            await client.post(
                foreign_url + "/statements",
                json={
                    "request_id": str(uuid.uuid4()),
                    "period_start": "2026-09-18",
                    "period_end": "2026-10-17",
                    "due_date": "2026-11-12",
                    "debt_pln": 100000,
                    "minimum_pln": 3000,
                    "source_reference": "Bank",
                },
            )
        ).json()
        assert (
            await client.post(
                foreign_url + "/allocations",
                json={
                    "request_id": str(uuid.uuid4()),
                    "transaction_id": str(txn.id),
                    "statement_id": statement["id"],
                    "amount_pln": 50000,
                },
            )
        ).status_code == 201
    async with client_for(db_session, owner) as client:
        url = BASE.format(card.id)
        await client.put(url, json=config())
        assert (await client.delete(url + "/statements/" + statement["id"])).status_code == 404
