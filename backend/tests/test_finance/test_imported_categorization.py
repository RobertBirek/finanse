"""Human corrections of imported expenses never rewrite bank evidence or money."""

import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.audit.models import AuditEvent
from app.finance import service
from app.finance.categorization import apply_categorization
from app.finance.categorization_context import CategorizationError, build_preview, load_context
from app.finance.categorization_schemas import CategorizationApply, CategorizationPart
from app.finance.imports.commit import commit_import
from app.finance.imports.models import ImportEvidence
from app.finance.models import (
    ActualImportMapping,
    FinanceCommandReceipt,
    LoanAgreement,
    LoanInstallment,
    LoanPaymentLink,
    Posting,
    TransactionDateMetadata,
)
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.rule_models import TransactionCategorizationOrigin
from app.finance.schemas import AccountCreate, CategoryCreate
from app.finance.suggestion_models import CategorizationSuggestionJob
from scripts import migrate_actual
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import
from tests.test_finance.test_bill_payments import create_owner
from tests.test_finance.test_categorization import apply, columns, path, preview, setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def imported(db, source="actual", *, archived=False):
    owner, txn, account, food, home = await setup(db)
    txn.source = source
    if source == "actual":
        txn.description = "[actual:category-edit-fixture] Synthetic imported expense"
        db.add(
            ActualImportMapping(
                user_id=owner,
                entity_type="transaction",
                actual_id="category-edit-fixture",
                entity_id=txn.id,
            )
        )
    if archived:
        account.is_active = False
    await db.commit()
    await db.refresh(txn, attribute_names=["updated_at"])
    return owner, txn, account, food, home


async def rows(db, model):
    return [columns(r) for r in (await db.scalars(select(model).order_by(model.id))).all()]


async def add_loan(db, owner, txn, account):
    loan_account = await service.create_account(
        db, owner, AccountCreate(name="Loan balance", type="credit", currency="PLN")
    )
    agreement = LoanAgreement(
        user_id=owner, name="Loan", account_id=loan_account.id, payment_account_id=account.id
    )
    db.add(agreement)
    await db.flush()
    installment = LoanInstallment(
        user_id=owner,
        loan_id=agreement.id,
        number=1,
        due_date=date(2026, 2, 2),
        principal_pln=10000,
        interest_pln=0,
        fees_pln=0,
    )
    db.add(installment)
    await db.flush()
    db.add(LoanPaymentLink(user_id=owner, installment_id=installment.id, transaction_id=txn.id))
    await db.commit()


@pytest.mark.parametrize(
    "source,archived", [("actual", False), ("actual", True), ("bank_import", False)]
)
async def test_reviewed_import_category_correction_preserves_account_and_provenance(
    db_session, source, archived
):
    db = db_session
    owner, txn, account, food, home = await imported(db, source, archived=archived)
    payment = next(p for p in txn.postings if p.account_id)
    payment_before, txn_before = columns(payment), columns(txn)
    mappings = await rows(db, ActualImportMapping)
    async with client_for(db, owner) as client:
        context = (await client.get(path(txn))).json()
        assert context["eligibility"]["allowed"] is True
        p = await preview(
            client, txn, [{"category_id": str(home.id), "amount_minor": 10000}], context
        )
        result = await apply(client, txn, p, "human-import-correction")
        assert result.status_code == 200, result.text
        assert result.json()["eligibility"]["allowed"] is True
        assert result.json()["parts"] == [{"category_id": str(home.id), "amount_minor": 10000}]
        replay = await apply(client, txn, p, "human-import-correction")
        assert replay.json() == result.json()
    await db.refresh(payment)
    await db.refresh(txn)
    assert columns(payment) == payment_before
    assert {k: v for k, v in columns(txn).items() if k != "updated_at"} == {
        k: v for k, v in txn_before.items() if k != "updated_at"
    }
    assert await rows(db, ActualImportMapping) == mappings
    assert (await service.get_account(db, owner, account.id)).balance_pln == -10000
    report = await service.get_category_summary(db, owner, 2, 2026)
    totals = {c.category_id: c.total_pln for c in report.categories}
    assert totals.get(food.id, 0) == 0 and totals[home.id] == 10000
    assert (await service.get_financial_summary(db, owner, 2, 2026)).expense_total_pln == 10000
    origin = await db.scalar(
        select(TransactionCategorizationOrigin).where(
            TransactionCategorizationOrigin.transaction_id == txn.id
        )
    )
    assert origin.origin == "manual"
    assert (
        await db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "apply_expense_categorization")
        )
        == 1
    )
    for model in [TransactionRuleEvent, CategorizationSuggestionJob]:
        assert await db.scalar(select(func.count()).select_from(model)) == 0
    if source == "actual":
        assert await migrate_actual.check_idempotent(db, owner, "category-edit-fixture") is True


@pytest.mark.parametrize("source", ["actual", "bank_import"])
async def test_import_permission_does_not_open_default_automation_or_receipt_preview(
    db_session, source
):
    owner, txn, _, _, home = await imported(db_session, source)
    ctx = await load_context(db_session, owner, txn.id)
    assert ctx.eligibility().allowed is False
    with pytest.raises(CategorizationError):
        build_preview(ctx, [CategorizationPart(category_id=home.id, amount_minor=10000)])


@pytest.mark.parametrize(
    "blocked", ["loan", "unknown", "foreign_mapping", "refund", "fx", "pending", "foreign_target"]
)
async def test_import_correction_still_rejects_unsafe_cases(db_session, blocked):
    owner, txn, account, _, home = await imported(db_session)
    if blocked == "loan":
        await add_loan(db_session, owner, txn, account)
    elif blocked == "unknown":
        txn.source = "untrusted_external_source"
    elif blocked == "foreign_mapping":
        mapping = await db_session.scalar(select(ActualImportMapping))
        mapping.user_id = uuid.uuid4()
    elif blocked == "refund":
        for p in txn.postings:
            p.direction = "credit" if p.account_id else "debit"
    elif blocked == "fx":
        account.currency = "EUR"
    elif blocked == "pending":
        txn.is_pending = True
    else:
        home.user_id = uuid.uuid4()
    await db_session.commit()
    before = await rows(db_session, Posting)
    async with client_for(db_session, owner) as client:
        response = await client.get(path(txn))
        ctx = response.json()
        if blocked != "foreign_target":
            assert ctx["eligibility"]["allowed"] is False
        response = await client.post(
            path(txn) + "/preview",
            json={
                "expected_version": ctx["version"],
                "expected_context_snapshot": ctx["context_snapshot"],
                "parts": [{"category_id": str(home.id), "amount_minor": 10000}],
            },
        )
        assert response.status_code in {409, 422}
    assert await rows(db_session, Posting) == before


@pytest.mark.parametrize("change", ["loan", "mapping", "archive_target"])
async def test_import_link_or_category_change_after_review_rejects_approval(db_session, change):
    owner, txn, account, _, home = await imported(db_session)
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        if change == "loan":
            await add_loan(db_session, owner, txn, account)
        elif change == "mapping":
            mapping = await db_session.scalar(select(ActualImportMapping))
            mapping.actual_id = "changed-source-identity"
        else:
            home.is_active = False
        await db_session.commit()
        response = await apply(client, txn, p)
        assert response.status_code == 409, response.text


async def test_parallel_imported_decisions_only_apply_one_reviewed_snapshot(db_session):
    owner, txn, _, _food, home = await imported(db_session)
    txn_id = txn.id
    async with client_for(db_session, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
    await db_session.commit()
    data = CategorizationApply(
        expected_version=p["expected_version"],
        expected_preview_snapshot=p["preview_snapshot"],
        parts=p["after_parts"],
        confirmed=True,
    )
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def approve(key):
        async with sessions() as db:
            try:
                result = await apply_categorization(db, owner, txn_id, data, idempotency_key=key)
                await db.commit()
                return result
            except CategorizationError:
                await db.rollback()
                return None

    results = await asyncio.wait_for(asyncio.gather(approve("first"), approve("second")), 20)
    assert sum(r is not None for r in results) == 1


async def test_real_bank_commit_evidence_and_receipt_survive_category_edit_and_replay(
    db_session, tmp_path, monkeypatch
):
    db = db_session
    owner = await create_owner(db)
    case, request = await confirmed_import(db, owner, tmp_path, monkeypatch)
    committed = await commit_import(db, owner, case.batch_id, request, "bank-original")
    txn_id = committed.transaction_ids[0]
    txn = await service.get_transaction(db, owner, txn_id)
    home = await service.create_category(db, owner, CategoryCreate(name="Naprawy", type="expense"))
    await db.commit()
    references = await rows(db, ImportEvidence)
    original_receipt = [
        r for r in await rows(db, FinanceCommandReceipt) if r["action"] == "bank_import.commit"
    ]
    payment = next(p for p in txn.postings if p.account_id)
    original_payment = columns(payment)
    async with client_for(db, owner) as client:
        p = await preview(
            client, txn, [{"category_id": str(home.id), "amount_minor": payment.source_amount}]
        )
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
    again = await commit_import(db, owner, case.batch_id, request, "bank-original")
    assert again == committed
    assert await rows(db, ImportEvidence) == references
    assert [
        r for r in await rows(db, FinanceCommandReceipt) if r["action"] == "bank_import.commit"
    ] == original_receipt
    await db.refresh(payment)
    assert columns(payment) == original_payment
    current = await service.get_transaction(db, owner, txn_id)
    assert next(p.category_id for p in current.postings if p.category_id) == home.id


async def test_bank_evidence_change_after_preview_invalidates_human_approval(
    db_session, tmp_path, monkeypatch
):
    db = db_session
    owner = await create_owner(db)
    case, request = await confirmed_import(db, owner, tmp_path, monkeypatch)
    committed = await commit_import(db, owner, case.batch_id, request, "bank-preview")
    txn = await service.get_transaction(db, owner, committed.transaction_ids[0])
    home = await service.create_category(db, owner, CategoryCreate(name="Repairs", type="expense"))
    await db.commit()
    async with client_for(db, owner) as client:
        p = await preview(
            client,
            txn,
            [
                {
                    "category_id": str(home.id),
                    "amount_minor": next(p.source_amount for p in txn.postings if p.account_id),
                }
            ],
        )
        evidence = await db.scalar(
            select(ImportEvidence).where(ImportEvidence.transaction_id == txn.id)
        )
        evidence.attributed_source_amount -= 1
        await db.commit()
        before = await rows(db, Posting)
        result = await apply(client, txn, p)
        assert result.status_code == 409, result.text
    assert await rows(db, Posting) == before


async def test_existing_import_split_and_dates_remain_valid_after_reassignment(db_session):
    db = db_session
    owner, txn, account, _food, home = await imported(db_session)
    metadata = TransactionDateMetadata(
        user_id=owner,
        transaction_id=txn.id,
        purchase_date=date(2026, 2, 1),
        booking_date=date(2026, 2, 2),
        purchase_date_source="import",
        booking_date_source="import",
        version=1,
    )
    db.add(metadata)
    category = next(p for p in txn.postings if p.category_id)
    category.source_amount = category.base_amount_pln = 6000
    txn.postings.append(
        Posting(
            transaction_id=txn.id,
            category_id=home.id,
            source_amount=4000,
            base_amount_pln=4000,
            source_currency="PLN",
            fx_rate=1,
            direction="credit",
            is_budget_impact=category.is_budget_impact,
        )
    )
    await db.commit()
    reference = columns(metadata)
    async with client_for(db, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        result = await apply(client, txn, p)
        assert result.status_code == 200, result.text
    await db.refresh(metadata)
    assert columns(metadata) == reference
    assert (await service.get_account(db, owner, account.id)).balance_pln == -10000


async def test_actual_reimport_provenance_guard_fails_closed_without_overwriting_correction(
    db_session,
):
    db = db_session
    owner, txn, account, food, home = await imported(db)
    for kind, actual_id, entity in [("account", "a", account), ("category", "food", food)]:
        await migrate_actual._store_mapping(db, owner, kind, actual_id, entity.id)
    await db.commit()
    async with client_for(db, owner) as client:
        p = await preview(client, txn, [{"category_id": str(home.id), "amount_minor": 10000}])
        assert (await apply(client, txn, p)).status_code == 200
    # A fresh archive with source-absent history cannot prove a local target using
    # old source IDs; it must stop, never guess a mapping or restore the old category.
    before = await rows(db, Posting)
    parser = SimpleNamespace(get_categories=list, get_category_groups=list)
    with pytest.raises(migrate_actual.LegacyActualMappingError, match="category"):
        await migrate_actual._backfill_legacy_mappings(db, owner, parser, [])
    assert await rows(db, Posting) == before


@pytest.mark.parametrize("operation", ["insert", "update", "delete"])
async def test_actual_mapping_writer_cannot_change_reviewed_context_until_commit(
    db_session, operation
):
    owner, txn, _, _, _ = await imported(db_session)
    txn_id = txn.id
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    await db_session.commit()
    async with sessions() as reviewer, sessions() as writer:
        await load_context(reviewer, owner, txn_id, lock=True)
        await writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
        # A separate connection must wait even for a new mapping (no row to lock).
        with pytest.raises(DBAPIError, match="lock timeout"):
            if operation == "insert":
                await migrate_actual._store_mapping(
                    writer, owner, "transaction", "new-source", txn_id
                )
            elif operation == "update":
                await writer.execute(
                    update(ActualImportMapping)
                    .where(ActualImportMapping.entity_id == txn_id)
                    .values(actual_id="changed")
                )
            else:
                await writer.execute(
                    delete(ActualImportMapping).where(ActualImportMapping.entity_id == txn_id)
                )
        await writer.rollback()
        await reviewer.commit()
        # Once review commits, legitimate provenance attachment can proceed.
        assert (
            await migrate_actual._store_mapping(
                writer, owner, "transaction", "after-review", txn_id
            )
            == txn_id
        )
        await writer.commit()
