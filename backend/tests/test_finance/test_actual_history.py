"""Pinned preserved history is an authorization input, never an amount override."""

import hashlib
import importlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.finance.models import Account, ActualImportMapping, Category, FinancialTransaction, Posting
from app.finance.reconciliation import CategoryBalance, SourceBalance
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction
from scripts.migrate_actual import _store_mapping


def history_module() -> Any:
    return importlib.import_module("app.finance.actual_history")


def uid(value: int) -> uuid.UUID:
    return uuid.UUID(int=value)


def example_transaction() -> FinancialTransaction:
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    transaction = FinancialTransaction(
        id=uid(4),
        user_id=uid(7),
        date=date(2026, 1, 1),
        description="[actual:kept] Text Å",
        type="expense",
        is_pending=False,
        project_id=None,
        created_by="human",
        source="actual",
        created_at=stamp,
        updated_at=stamp,
    )
    transaction.postings = [
        Posting(
            id=uid(post_id),
            transaction_id=uid(4),
            account_id=account,
            category_id=category,
            source_amount=37,
            source_currency="EUR",
            base_amount_pln=148,
            fx_rate=Decimal(4),
            fx_rate_source="manual",
            direction=direction,
            is_budget_impact=True,
            created_at=stamp,
            updated_at=stamp,
        )
        for post_id, account, category, direction in [
            (5, uid(1), None, "debit"),
            (6, None, uid(2), "credit"),
        ]
    ]
    return transaction


def expected_fingerprint() -> str:
    # Independent literal payload, including ALL database columns, not the helper's output.
    stamp = "2026-01-01T00:00:00.000000+00:00"
    payload = {
        "transaction": {
            "id": str(uid(4)),
            "user_id": str(uid(7)),
            "date": "2026-01-01",
            "description": "[actual:kept] Text Å",
            "type": "expense",
            "is_pending": False,
            "project_id": None,
            "created_by": "human",
            "source": "actual",
            "created_at": stamp,
            "updated_at": stamp,
        },
        "postings": [
            {
                "id": str(uid(5)),
                "transaction_id": str(uid(4)),
                "account_id": str(uid(1)),
                "category_id": None,
                "source_amount": 37,
                "source_currency": "EUR",
                "base_amount_pln": 148,
                "fx_rate": "4.000000",
                "fx_rate_source": "manual",
                "direction": "debit",
                "is_budget_impact": True,
                "created_at": stamp,
                "updated_at": stamp,
            },
            {
                "id": str(uid(6)),
                "transaction_id": str(uid(4)),
                "account_id": None,
                "category_id": str(uid(2)),
                "source_amount": 37,
                "source_currency": "EUR",
                "base_amount_pln": 148,
                "fx_rate": "4.000000",
                "fx_rate_source": "manual",
                "direction": "credit",
                "is_budget_impact": True,
                "created_at": stamp,
                "updated_at": stamp,
            },
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def test_fingerprint_covers_columns_with_canonical_encoding() -> None:
    module = history_module()
    transaction = example_transaction()
    assert module.transaction_fingerprint(transaction) == expected_fingerprint()
    transaction.postings.reverse()
    transaction.created_at = datetime(2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    transaction.postings[0].fx_rate = Decimal("4.000000")
    assert module.transaction_fingerprint(transaction) == expected_fingerprint()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", uid(99)),
        ("user_id", uid(99)),
        ("date", date(2026, 1, 2)),
        ("description", "[actual:kept] Text Å"),
        ("type", "income"),
        ("is_pending", True),
        ("project_id", uid(99)),
        ("created_by", "agent"),
        ("source", "manual"),
        ("created_at", datetime(2026, 1, 2, tzinfo=UTC)),
        ("updated_at", datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_any_transaction_column_invalidates_pin(field: str, value: Any) -> None:
    transaction = example_transaction()
    setattr(transaction, field, value)
    assert history_module().transaction_fingerprint(transaction) != expected_fingerprint()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", uid(99)),
        ("transaction_id", uid(99)),
        ("account_id", uid(99)),
        ("category_id", uid(99)),
        ("source_amount", 38),
        ("source_currency", "USD"),
        ("base_amount_pln", 149),
        ("fx_rate", Decimal("4.000001")),
        ("fx_rate_source", "changed"),
        ("direction", "credit"),
        ("is_budget_impact", False),
        ("created_at", datetime(2026, 1, 2, tzinfo=UTC)),
        ("updated_at", datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
def test_any_posting_column_invalidates_pin(field: str, value: Any) -> None:
    transaction = example_transaction()
    setattr(transaction.postings[0], field, value)
    assert history_module().transaction_fingerprint(transaction) != expected_fingerprint()


@pytest.mark.parametrize("fault", ["naive-time", "extra-precision", "nonfinite-rate"])
def test_fingerprint_rejects_ambiguous_numeric_and_datetime_encoding(fault: str) -> None:
    module = history_module()
    transaction = example_transaction()
    if fault == "naive-time":
        transaction.updated_at = transaction.updated_at.replace(tzinfo=None)
    else:
        transaction.postings[0].fx_rate = (
            Decimal("4.0000001") if fault == "extra-precision" else Decimal("NaN")
        )
    with pytest.raises(ValueError):
        module.transaction_fingerprint(transaction)


def manifest_data() -> dict[str, Any]:
    return {
        "version": 1,
        "source_zip_sha256": hashlib.sha256(b"archive").hexdigest(),
        "user_id": str(uid(7)),
        "transaction": {
            "actual_id": "kept",
            "pa_id": str(uid(4)),
            "snapshot_sha256": expected_fingerprint(),
        },
    }


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "zip",
        "user",
        "version",
        "bool-version",
        "unknown",
        "amount",
        "uuid",
        "hash",
        "empty-id",
    ],
)
def test_manifest_accepts_only_one_exact_identity_pin(tmp_path: Path, fault: str | None) -> None:
    module = history_module()
    data = manifest_data()
    archive = b"archive"
    if fault == "zip":
        archive = b"different archive"
    elif fault == "user":
        data["user_id"] = str(uid(99))
    elif fault == "version":
        data["version"] = 2
    elif fault == "bool-version":
        data["version"] = True
    elif fault == "unknown":
        data["tolerance"] = 100
    elif fault == "amount":
        data["transaction"]["amount"] = 37
    elif fault == "uuid":
        data["transaction"]["pa_id"] = "not-a-uuid"
    elif fault == "hash":
        data["transaction"]["snapshot_sha256"] = "not-a-hash"
    elif fault == "empty-id":
        data["transaction"]["actual_id"] = ""
    path = tmp_path / "pin.json"
    path.write_text(json.dumps(data))
    if fault:
        with pytest.raises(ValueError):
            module.load_preserved_history(path, archive, uid(7))
    else:
        manifest = module.load_preserved_history(path, archive, uid(7))
        assert manifest.transaction.pa_id == uid(4) and manifest.user_id == uid(7)


def test_contributions_come_from_postings_without_mutating_expected_maps() -> None:
    module = history_module()
    transaction = example_transaction()
    accounts = {"a": SourceBalance("a", "EUR account", "EUR", True, 100)}
    categories = {"c": CategoryBalance("c", "Category", "expense", 1000)}
    groups = {"g": CategoryBalance("g", "Group", "expense", 1000)}
    expected = module.add_preserved_history_balances(
        transaction,
        {"a": uid(1)},
        {"c": uid(2)},
        {"g": uid(3)},
        [{"actual_id": "c", "name": "Category", "type": "expense", "group_actual_id": "g"}],
        accounts,
        categories,
        groups,
    )
    assert expected[0]["a"].amount == 63
    assert expected[1]["c"].amount_pln == 852 and expected[2]["g"].amount_pln == 852
    assert (
        accounts["a"].amount == 100
        and categories["c"].amount_pln == 1000
        and groups["g"].amount_pln == 1000
    )
    assert module.transaction_fingerprint(transaction) == expected_fingerprint()


@pytest.mark.parametrize(
    "fault",
    [
        "missing-account",
        "missing-category",
        "missing-group",
        "duplicate-account",
        "currency",
        "unknown-source-category",
    ],
)
def test_unmapped_or_ambiguous_contribution_is_never_guessed(fault: str) -> None:
    module = history_module()
    account_map = {"a": uid(1)}
    category_map = {"c": uid(2)}
    group_map = {"g": uid(3)}
    accounts = {"a": SourceBalance("a", "EUR account", "EUR", True, 100)}
    source_categories = [
        {"actual_id": "c", "name": "Category", "type": "expense", "group_actual_id": "g"}
    ]
    if fault == "missing-account":
        account_map = {}
    elif fault == "missing-category":
        category_map = {}
    elif fault == "missing-group":
        group_map = {}
    elif fault == "duplicate-account":
        account_map["duplicate"] = uid(1)
    elif fault == "currency":
        accounts["a"] = SourceBalance("a", "Wrong currency", "PLN", True, 100)
    elif fault == "unknown-source-category":
        source_categories = []
    with pytest.raises(ValueError):
        module.add_preserved_history_balances(
            example_transaction(),
            account_map,
            category_map,
            group_map,
            source_categories,
            accounts,
            {"c": CategoryBalance("c", "Category", "expense", 1000)},
            {"g": CategoryBalance("g", "Group", "expense", 1000)},
        )


async def seed_history(db: AsyncSession) -> tuple[uuid.UUID, FinancialTransaction, dict[str, Any]]:
    user = uuid.uuid4()
    account = await create_account(
        db, user, AccountCreate(name="EUR", type="checking", currency="EUR")
    )
    group = await create_category(db, user, CategoryCreate(name="Group", type="expense"))
    category = await create_category(
        db, user, CategoryCreate(name="Category", type="expense", parent_id=group.id)
    )
    transaction = await create_transaction(
        db,
        user,
        TransactionCreate(
            transaction_date=date(2026, 1, 1),
            description="[actual:kept] Preserved",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=37,
                    source_currency="EUR",
                    base_amount_pln=148,
                    fx_rate=4,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=37,
                    source_currency="EUR",
                    base_amount_pln=148,
                    fx_rate=4,
                    direction="credit",
                ),
            ],
        ),
    )
    for kind, source_id, entity_id in [
        ("account", "a", account.id),
        ("category", "c", category.id),
        ("category_group", "g", group.id),
        ("transaction", "kept", transaction.id),
    ]:
        await _store_mapping(db, user, kind, source_id, entity_id)
    await db.commit()
    data = manifest_data()
    data["user_id"] = str(user)
    data["transaction"]["pa_id"] = str(transaction.id)
    data["transaction"]["snapshot_sha256"] = history_module().transaction_fingerprint(transaction)
    return user, transaction, data


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "manifest-user",
        "missing-transaction",
        "mapping-type",
        "mapping-id",
        "mapping-owner",
        "transaction-owner",
        "source",
        "prefix",
        "snapshot",
        "posting",
        "present-in-source",
        "foreign-account",
        "foreign-category",
        "foreign-group",
    ],
)
async def test_locked_validation_requires_the_exact_owned_source_absent_transaction(
    db_session: AsyncSession, fault: str | None
) -> None:
    module = history_module()
    user, transaction, data = await seed_history(db_session)
    source_ids = {"other"}
    mapping = await db_session.scalar(
        select(ActualImportMapping).where(
            ActualImportMapping.user_id == user, ActualImportMapping.entity_type == "transaction"
        )
    )
    assert mapping is not None
    if fault == "manifest-user":
        data["user_id"] = str(uuid.uuid4())
    elif fault == "missing-transaction":
        data["transaction"]["pa_id"] = str(uuid.uuid4())
    elif fault == "mapping-type":
        mapping.entity_type = "not_transaction"
    elif fault == "mapping-id":
        mapping.entity_id = uuid.uuid4()
    elif fault == "mapping-owner":
        mapping.user_id = uuid.uuid4()
    elif fault == "transaction-owner":
        transaction.user_id = uuid.uuid4()
    elif fault == "source":
        transaction.source = "manual"
    elif fault == "prefix":
        transaction.description = "[actual:another] Not the approved source"
    elif fault == "snapshot":
        transaction.description = "[actual:kept] Edited"
    elif fault == "posting":
        transaction.postings[0].fx_rate_source = "edited"
    elif fault == "present-in-source":
        source_ids.add("kept")
    elif fault == "foreign-account":
        account = await db_session.scalar(select(Account))
        assert account is not None
        account.user_id = uuid.uuid4()
    elif fault in {"foreign-category", "foreign-group"}:
        category = await db_session.scalar(
            select(Category).where(
                Category.parent_id.is_not(None)
                if fault == "foreign-category"
                else Category.parent_id.is_(None)
            )
        )
        assert category is not None
        category.user_id = uuid.uuid4()
    await db_session.commit()
    if fault in {"transaction-owner", "source", "prefix"}:
        # A matching hash alone must never authorize wrong ownership/provenance.
        await db_session.refresh(transaction)
        await db_session.refresh(transaction, attribute_names=["postings"])
        data["transaction"]["snapshot_sha256"] = module.transaction_fingerprint(transaction)
    manifest = module.PreservedHistoryManifest.model_validate(data)
    if fault:
        with pytest.raises(ValueError):
            await module.validate_preserved_history(db_session, user, manifest, source_ids)
    else:
        kept = await module.validate_preserved_history(db_session, user, manifest, source_ids)
        assert (
            kept.id == transaction.id
            and module.transaction_fingerprint(kept) == data["transaction"]["snapshot_sha256"]
        )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target", ["transaction", "posting", "account", "category", "group", "mapping"]
)
async def test_pin_holds_row_and_reference_locks_until_transaction_ends(
    db_session: AsyncSession, target: str
) -> None:
    module = history_module()
    user, transaction, data = await seed_history(db_session)
    manifest = module.PreservedHistoryManifest.model_validate(data)
    await module.validate_preserved_history(db_session, user, manifest, {"other"})
    if target == "transaction":
        statement = (
            update(FinancialTransaction)
            .where(FinancialTransaction.id == transaction.id)
            .values(description="changed")
        )
    elif target == "posting":
        statement = (
            update(Posting)
            .where(Posting.id == transaction.postings[0].id)
            .values(fx_rate_source="changed")
        )
    elif target == "account":
        statement = update(Account).where(Account.user_id == user).values(name="changed")
    elif target in {"category", "group"}:
        statement = (
            update(Category)
            .where(
                Category.user_id == user,
                Category.parent_id.is_not(None)
                if target == "category"
                else Category.parent_id.is_(None),
            )
            .values(name="changed")
        )
    else:
        statement = (
            update(ActualImportMapping)
            .where(
                ActualImportMapping.user_id == user,
                ActualImportMapping.entity_type == "transaction",
            )
            .values(entity_type="changed")
        )
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as writer:
        await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
        with pytest.raises(DBAPIError):
            await writer.execute(statement)
        await writer.rollback()
        await db_session.rollback()
        result = await writer.execute(statement)
        assert result.rowcount == 1
        await writer.rollback()
