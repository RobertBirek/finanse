"""Approved category changes preserve the payment and its external references."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, inspect, select

from app.audit.models import AuditEvent
from app.finance import service
from app.finance.actual_history import transaction_fingerprint
from app.finance.models import (
    ActualImportMapping,
    DocumentPaymentAllocation,
    FinanceCommandReceipt,
    FinancialTransaction,
)
from app.finance.schemas import CategoryCreate
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_guards import allocated
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_transaction_search import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize(
    "kind",
    [
        "loan",
        "refund",
        "unbalanced",
        "missing_category",
        "mixed_budget",
        "inactive_account",
        "document_payment",
    ],
)
async def test_additional_eligibility_does_not_repair_or_rewrite_ledger(db_session, kind):
    from app.finance.models import LoanAgreement, LoanInstallment, LoanPaymentLink, Posting
    from app.finance.schemas import AccountCreate

    owner, txn, account, _food, home = await setup(db_session)
    if kind == "loan":
        other = await service.create_account(
            db_session, owner, AccountCreate(name="Loan account", type="credit", currency="PLN")
        )
        agreement = LoanAgreement(
            user_id=owner, name="Synthetic loan", account_id=other.id, payment_account_id=account.id
        )
        db_session.add(agreement)
        await db_session.flush()
        installment = LoanInstallment(
            user_id=owner,
            loan_id=agreement.id,
            number=1,
            due_date=date(2026, 2, 2),
            principal_pln=10000,
            interest_pln=0,
            fees_pln=0,
        )
        db_session.add(installment)
        await db_session.flush()
        db_session.add(
            LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=txn.id)
        )
    if kind == "refund":
        for p in txn.postings:
            p.direction = "credit" if p.account_id else "debit"
    if kind == "unbalanced":
        txn.postings[0].base_amount_pln += 1
    if kind == "missing_category":
        next(p for p in txn.postings if p.category_id).category_id = None
    if kind == "mixed_budget":
        category = next(p for p in txn.postings if p.category_id)
        category.source_amount = category.base_amount_pln = 8000
        posting = Posting(
            transaction_id=txn.id,
            category_id=home.id,
            source_currency="PLN",
            source_amount=2000,
            base_amount_pln=2000,
            fx_rate=1,
            direction="credit",
            is_budget_impact=not category.is_budget_impact,
        )
        txn.postings.append(posting)
        db_session.add(posting)
    if kind == "inactive_account":
        account.is_active = False
    if kind == "document_payment":
        txn.source = "document_payment"
    await db_session.flush()
    await db_session.refresh(txn, attribute_names=["updated_at", "postings"])
    await db_session.commit()
    original = transaction_fingerprint(txn)
    async with client_for(db_session, owner) as client:
        response = await client.get(path(txn))
        assert response.status_code == 200, response.text
        assert response.json()["eligibility"]["allowed"] == (
            kind in {"inactive_account", "document_payment"}
        )
    assert transaction_fingerprint(txn) == original


async def test_target_archive_after_preview_requires_a_new_decision(db_session):
    owner, txn, _, _, home = await setup(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        home.is_active = False
        await db_session.flush()
        await db_session.commit()
        response = await apply(client, txn, p)
        assert response.status_code == 409, response.text


def columns(row):
    return {c.key: getattr(row, c.key) for c in row.__mapper__.column_attrs}


def path(txn):
    return f"/api/finance/transactions/{inspect(txn).identity[0]}/categorization"


async def setup(db):
    owner = await create_owner(db)
    txn, account, food = await seed(db, owner, day=date(2026, 2, 2), amount=10000)
    home = await service.create_category(db, owner, CategoryCreate(name="Chemia", type="expense"))
    await db.commit()
    return owner, txn, account, food, home


async def preview(client, txn, parts, context=None):
    if context is None:
        response = await client.get(path(txn))
        assert response.status_code == 200, response.text
        context = response.json()
    response = await client.post(
        path(txn) + "/preview",
        json={
            "expected_version": context["version"],
            "expected_context_snapshot": context["context_snapshot"],
            "parts": parts,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def apply(client, txn, p, key=None):
    return await client.post(
        path(txn) + "/apply",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={
            "expected_version": p["expected_version"],
            "expected_preview_snapshot": p["preview_snapshot"],
            "parts": p["after_parts"],
            "confirmed": True,
        },
    )


async def test_split_merge_preserves_payment_identity_and_report_totals(db_session):
    owner, txn, account, food, home = await setup(db_session)
    account_post = next(p for p in txn.postings if p.account_id)
    original = columns(account_post)
    async with client_for(db_session, owner) as client:
        context = (await client.get(path(txn))).json()
        assert context.get("version") == 0, "Context must exist without mutating legacy records"
        p = await preview(
            client,
            txn,
            [
                {"category_id": str(food.id), "amount_minor": 8000},
                {"category_id": str(home.id), "amount_minor": 2000},
            ],
            context,
        )
        assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
        assert result.json()["version"] == 1 and result.json()["source"] == "manual"
        assert columns(account_post) == original
        assert (
            len(txn.postings) == 3
            and sum(
                p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
                for p in txn.postings
            )
            == 0
        )
        report = await service.get_category_summary(db_session, owner, month=2, year=2026)
        assert {x.category_id: x.total_pln for x in report.categories} == {
            food.id: 8000,
            home.id: 2000,
        }
        assert (await service.get_account(db_session, owner, account.id)).balance_pln == -10000
        p = await preview(client, txn, [{"category_id": str(food.id), "amount_minor": 10000}])
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
        assert result.json()["version"] == 2 and len(txn.postings) == 2
    assert columns(account_post) == original and txn.date == date(2026, 2, 2)
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 1


async def test_allocations_and_generic_guards_survive_category_change(db_session):
    owner, _bill_id, txn_id, _, _, _ = await allocated(db_session)
    txn = await service.get_transaction(db_session, owner, txn_id)
    category = await service.create_category(
        db_session, owner, CategoryCreate(name="Chemia", type="expense")
    )
    allocations = list((await db_session.scalars(select(DocumentPaymentAllocation))).all())
    before = [columns(x) for x in allocations]
    account_post = next(p for p in txn.postings if p.account_id)
    old = columns(account_post)
    async with client_for(db_session, owner) as client:
        p = await preview(
            client,
            txn,
            [{"category_id": str(category.id), "amount_minor": account_post.source_amount}],
        )
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
        assert (await client.delete(f"/api/finance/transactions/{txn_id}")).status_code == 409
    assert [columns(x) for x in allocations] == before and columns(account_post) == old


async def test_receipt_replay_noop_and_key_reuse(db_session):
    owner, txn, _, food, home = await setup(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        key = uuid.uuid4().hex
        first = await apply(client, txn, p, key)
        assert first.status_code == 200, first.text
        again = await apply(client, txn, p, key)
        assert again.json() == first.json()
        different = {**p, "after_parts": [{"category_id": str(food.id), "amount_minor": 10000}]}
        assert (await apply(client, txn, different, key)).status_code == 409
        assert (await apply(client, txn, p)).status_code == 409
        same = await preview(client, txn, p["after_parts"])
        no_op = await apply(client, txn, same)
        assert no_op.status_code == 200 and no_op.json()["version"] == 1
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "apply_expense_categorization")
        )
        == 1
    )


@pytest.mark.parametrize("amount", [9999, 10001, 0, -1, 1.2, True, 9007199254740992])
async def test_bad_amount_never_writes(db_session, amount):
    owner, txn, _, _, home = await setup(db_session)
    before = transaction_fingerprint(txn)
    async with client_for(db_session, owner) as client:
        context = await client.get(path(txn))
        assert context.status_code == 200, context.text
        response = await client.post(
            path(txn) + "/preview",
            json={
                "expected_version": 0,
                "expected_context_snapshot": context.json()["context_snapshot"],
                "parts": [{"category_id": str(home.id), "amount_minor": amount}],
            },
        )
        assert response.status_code == 422, response.text
    txn = await service.get_transaction(db_session, owner, inspect(txn).identity[0])
    assert transaction_fingerprint(txn) == before
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


@pytest.mark.parametrize(
    "protection",
    ["actual", "mapping", "pending", "income", "transfer", "exchange", "other_source", "fx"],
)
async def test_human_context_allows_imported_expenses_but_keeps_unsupported_guards(
    db_session, protection
):
    owner, txn, _, _, _ = await setup(db_session)
    if protection == "mapping":
        db_session.add(
            ActualImportMapping(
                user_id=owner, entity_type="transaction", actual_id="synthetic", entity_id=txn.id
            )
        )
    elif protection == "pending":
        txn.is_pending = True
    elif protection in {"income", "transfer", "exchange"}:
        txn.type = protection
    elif protection == "fx":
        txn.postings[0].source_currency = "EUR"
    else:
        txn.source = protection
    await db_session.flush()
    async with client_for(db_session, owner) as client:
        response = await client.get(path(txn))
        assert response.status_code == 200, response.text
        assert response.json()["eligibility"]["allowed"] == (protection in {"actual", "mapping"})


async def test_target_rename_or_ledger_change_invalidates_preview(db_session):
    owner, txn, _, _, home = await setup(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        home.name = "New meaning"
        await db_session.flush()
        result = await apply(client, txn, p)
        assert result.status_code == 409, result.text
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


async def test_foreign_context_and_apply_are404(db_session):
    owner, txn, _, _, home = await setup(db_session)
    other = await create_owner(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
    async with client_for(db_session, other) as client:
        assert (await client.get(path(txn))).status_code == 404
        assert (await apply(client, txn, p)).status_code == 404


@pytest.mark.parametrize(
    "target", ["missing", "foreign", "inactive", "income", "duplicate", "empty"]
)
async def test_invalid_category_targets_are422_without_receipts(db_session, target):
    owner, txn, _, food, home = await setup(db_session)
    if target == "inactive":
        home.is_active = False
    if target == "income":
        home.type = "income"
    if target == "foreign":
        home.user_id = await create_owner(db_session)
    await db_session.flush()
    await db_session.commit()
    target_id = uuid.uuid4() if target == "missing" else home.id
    parts = [{"category_id": str(target_id), "amount_minor": 10000}]
    if target == "duplicate":
        parts = [{"category_id": str(food.id), "amount_minor": 5000}] * 2
    if target == "empty":
        parts = []
    async with client_for(db_session, owner) as client:
        context = (await client.get(path(txn))).json()
        response = await client.post(
            path(txn) + "/preview",
            json={
                "expected_version": 0,
                "expected_context_snapshot": context["context_snapshot"],
                "parts": parts,
            },
        )
    assert response.status_code == 422, response.text
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


async def test_manual_confirmation_imported_target_and_date_budget_preserved(db_session):
    from app.finance.models import TransactionCategorizationState, TransactionDateMetadata
    from app.finance.schemas import CategoryBudgetCreate

    owner, txn, _, food, home = await setup(db_session)
    txn_id = txn.id
    home.source = "actual"
    metadata = TransactionDateMetadata(
        transaction_id=txn_id,
        user_id=owner,
        purchase_date=date(2026, 1, 30),
        purchase_date_source="manual",
        booking_date=date(2026, 2, 2),
        booking_date_source="manual",
        version=1,
    )
    db_session.add(metadata)
    await db_session.flush()
    before_dates = columns(metadata)
    await service.create_budget(
        db_session, owner, CategoryBudgetCreate(category_id=food.id, amount_pln=10000)
    )
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        p = await preview(
            client,
            txn,
            [
                {"category_id": str(food.id), "amount_minor": 8000},
                {"category_id": str(home.id), "amount_minor": 2000},
            ],
        )
        response = await apply(client, txn, p)
        assert response.status_code == 200, response.text
    assert columns(metadata) == before_dates
    budget = await service.get_budget_status(db_session, owner, month=1, year=2026)
    assert budget.total_spent_pln == 8000
    assert (
        await service.get_financial_summary(db_session, owner, month=2, year=2026)
    ).expense_total_pln == 0
    assert home.source == "actual"
    state = await db_session.scalar(
        select(TransactionCategorizationState).where(
            TransactionCategorizationState.transaction_id == txn_id
        )
    )
    assert state.source == "manual" and state.before_snapshot_sha256 != state.after_snapshot_sha256


async def test_posting_edit_without_parent_timestamp_invalidates_preview(db_session):
    owner, txn, _, _, home = await setup(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        old = txn.updated_at
        txn.postings[0].fx_rate_source = "changed"
        await db_session.flush()
        assert txn.updated_at == old
        response = await apply(client, txn, p)
        assert response.status_code == 409, response.text


async def test_audit_failure_rolls_back_postings_state_and_receipt(db_session, monkeypatch):
    from app.finance import categorization
    from app.finance.categorization_schemas import CategorizationApply
    from app.finance.models import TransactionCategorizationState

    owner, txn, _, _, home = await setup(db_session)
    txn_id = txn.id
    before = transaction_fingerprint(txn)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
    await db_session.commit()

    async def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(categorization, "log_event", fail)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        async with db_session.begin_nested():
            await categorization.apply_categorization(
                db_session,
                owner,
                txn_id,
                CategorizationApply(
                    expected_version=p["expected_version"],
                    expected_preview_snapshot=p["preview_snapshot"],
                    parts=p["after_parts"],
                    confirmed=True,
                ),
                idempotency_key="audit-fail",
            )
    restored = await service.get_transaction(db_session, owner, txn_id)
    assert transaction_fingerprint(restored) == before
    assert (
        await db_session.scalar(select(func.count()).select_from(TransactionCategorizationState))
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0
