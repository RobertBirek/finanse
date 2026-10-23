"""Incremental imports must not mistake new source entities for unmapped history."""

import sqlite3
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import Account, Category, FinancialTransaction
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction
from scripts import migrate_actual as importer


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_old_mapping",
    [
        None,
        "account",
        "category",
        "category_group",
        "wrong-group",
        "no-groups",
        "absent-source",
        "absent-source-account",
        "absent-source-foreign-parent",
    ],
)
async def test_incremental_entities_require_complete_historical_provenance(
    db_session: AsyncSession, missing_old_mapping: str | None
) -> None:
    user = uuid.uuid4()
    account = await create_account(
        db_session, user, AccountCreate(name="Original", type="checking")
    )
    group = await create_category(db_session, user, CategoryCreate(name="Group", type="expense"))
    category = await create_category(
        db_session, user, CategoryCreate(name="Original", type="expense", parent_id=group.id)
    )
    account.source = category.source = group.source = "actual"
    txn = await create_transaction(
        db_session,
        user,
        TransactionCreate(
            transaction_date=date(2026, 10, 1),
            description="[actual:old-tx] preserved description",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=account.id, source_amount=100, base_amount_pln=100, direction="debit"
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit",
                ),
            ],
        ),
    )
    for kind, source_id, entity in [
        ("account", "old-account", account),
        ("category", "old-category", category),
        ("category_group", "old-group", group),
        ("transaction", "old-tx", txn),
    ]:
        omit = (
            kind == missing_old_mapping
            or (missing_old_mapping == "no-groups" and kind == "category_group")
            or (missing_old_mapping == "absent-source-account" and kind == "account")
        )
        if not omit:
            entity_id = (
                category.id
                if missing_old_mapping == "wrong-group" and kind == "category_group"
                else entity.id
            )
            await importer._store_mapping(db_session, user, kind, source_id, entity_id)
    parser = SimpleNamespace(
        get_accounts=lambda: [
            {
                "actual_id": "old-account",
                "name": "Original",
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
            },
            {
                "actual_id": "new-account",
                "name": "New",
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
            },
        ],
        get_categories=lambda: [
            {
                "actual_id": "old-category",
                "name": "Original",
                "type": "expense",
                "group_actual_id": "old-group",
            },
            {
                "actual_id": "new-category",
                "name": "New",
                "type": "expense",
                "group_actual_id": "new-group",
            },
        ],
        get_category_groups=lambda: [
            {"actual_id": "old-group", "name": "Group", "type": "expense"},
            {"actual_id": "new-group", "name": "New group", "type": "expense"},
        ],
    )
    source = [
        {
            "actual_id": "old-tx",
            "postings": [
                {
                    "account_actual_id": "old-account",
                    "category_actual_id": None,
                    "source_amount": 100,
                    "source_currency": "PLN",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "old-account",
                    "category_actual_id": "old-category",
                    "source_amount": 100,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ],
        }
    ]
    if missing_old_mapping == "no-groups":

        def no_groups() -> list:
            raise sqlite3.OperationalError("no such table: category_groups")

        parser.get_category_groups = no_groups
        category.parent_id = None
    if missing_old_mapping in {
        "absent-source",
        "absent-source-account",
        "absent-source-foreign-parent",
    }:
        source = []
    if missing_old_mapping == "absent-source-foreign-parent":
        group.user_id = uuid.uuid4()
        # This group is absent from the source as well, so only stored history
        # can prove (or reject) its ownership.
        parser.get_category_groups = list
    if missing_old_mapping in {
        "account",
        "category",
        "category_group",
        "wrong-group",
        "absent-source-account",
        "absent-source-foreign-parent",
    }:
        with pytest.raises(importer.LegacyActualMappingError):
            await importer.resolve_ids(db_session, user, parser, source)
        assert await db_session.scalar(select(func.count(Account.id))) == 1
        assert await db_session.scalar(select(func.count(Category.id))) == 2
    else:
        acct_map, cat_map, group_map, _, _ = await importer.resolve_ids(
            db_session, user, parser, source
        )
        assert acct_map["old-account"] == account.id and acct_map["new-account"] != account.id
        assert cat_map["old-category"] == category.id and cat_map["new-category"] != category.id
        if missing_old_mapping == "no-groups":
            assert group_map == {}
        else:
            assert group_map["old-group"] == group.id and group_map["new-group"] != group.id
        # Repeating the resolution reuses mappings, it never duplicates entities.
        again = await importer.resolve_ids(db_session, user, parser, source)
        assert again[:3] == (acct_map, cat_map, group_map)
        assert await db_session.scalar(select(func.count(Account.id))) == 2
        assert await db_session.scalar(select(func.count(Category.id))) == (
            3 if missing_old_mapping == "no-groups" else 4
        )
    assert await db_session.scalar(select(func.count(FinancialTransaction.id))) == 1
    assert txn.description == "[actual:old-tx] preserved description"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["account", "category"])
async def test_incremental_rejects_swapped_posting_mappings(
    db_session: AsyncSession, role: str
) -> None:
    user = uuid.uuid4()
    first = await create_account(db_session, user, AccountCreate(name="First", type="checking"))
    if role == "account":
        second = await create_account(
            db_session, user, AccountCreate(name="Second", type="checking")
        )
        legs = [
            PostingCreate(
                account_id=first.id, source_amount=100, base_amount_pln=100, direction="debit"
            ),
            PostingCreate(
                account_id=second.id, source_amount=100, base_amount_pln=100, direction="credit"
            ),
        ]
        accounts = [("a", first), ("b", second)]
        categories = []
        source_legs = [
            {
                "account_actual_id": "a",
                "category_actual_id": None,
                "source_amount": 100,
                "source_currency": "PLN",
                "direction": "credit",
            },
            {
                "account_actual_id": "b",
                "category_actual_id": None,
                "source_amount": 100,
                "source_currency": "PLN",
                "direction": "debit",
            },
        ]
        mappings = [("account", "a", second.id), ("account", "b", first.id)]
    else:
        cat_a = await create_category(
            db_session, user, CategoryCreate(name="First", type="expense")
        )
        cat_b = await create_category(
            db_session, user, CategoryCreate(name="Second", type="expense")
        )
        legs = [
            PostingCreate(
                account_id=first.id, source_amount=200, base_amount_pln=200, direction="debit"
            ),
            PostingCreate(
                category_id=cat_a.id, source_amount=100, base_amount_pln=100, direction="credit"
            ),
            PostingCreate(
                category_id=cat_b.id, source_amount=100, base_amount_pln=100, direction="credit"
            ),
        ]
        accounts = [("a", first)]
        categories = [("c1", cat_a), ("c2", cat_b)]
        source_legs = [
            {
                "account_actual_id": "a",
                "category_actual_id": None,
                "source_amount": 200,
                "source_currency": "PLN",
                "direction": "credit",
            },
            {
                "account_actual_id": "a",
                "category_actual_id": "c1",
                "source_amount": 100,
                "source_currency": "PLN",
                "direction": "debit",
            },
            {
                "account_actual_id": "a",
                "category_actual_id": "c2",
                "source_amount": 100,
                "source_currency": "PLN",
                "direction": "debit",
            },
        ]
        mappings = [
            ("account", "a", first.id),
            ("category", "c1", cat_b.id),
            ("category", "c2", cat_a.id),
        ]
    txn = await create_transaction(
        db_session,
        user,
        TransactionCreate(
            transaction_date=date(2026, 10, 1),
            description="[actual:old-tx] preserved",
            type="transfer" if role == "account" else "expense",
            source="actual",
            postings=legs,
        ),
    )
    for kind, source_id, entity_id in mappings + [("transaction", "old-tx", txn.id)]:
        await importer._store_mapping(db_session, user, kind, source_id, entity_id)
    parser = SimpleNamespace(
        get_accounts=lambda: (
            [
                {
                    "actual_id": source_id,
                    "name": entity.name,
                    "type": "checking",
                    "currency": "PLN",
                    "is_budget_account": True,
                }
                for source_id, entity in accounts
            ]
            + [
                {
                    "actual_id": "new",
                    "name": "New",
                    "type": "checking",
                    "currency": "PLN",
                    "is_budget_account": True,
                }
            ]
        ),
        get_categories=lambda: [
            {
                "actual_id": source_id,
                "name": entity.name,
                "type": "expense",
                "group_actual_id": None,
            }
            for source_id, entity in categories
        ],
        get_category_groups=list,
    )
    with pytest.raises(importer.LegacyActualMappingError):
        await importer.resolve_ids(
            db_session, user, parser, [{"actual_id": "old-tx", "postings": source_legs}]
        )
    assert await db_session.scalar(select(func.count(Account.id))) == len(accounts)
    assert await db_session.scalar(select(func.count(Category.id))) == len(categories)
    assert txn.description == "[actual:old-tx] preserved"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["account", "category", "category_group"])
@pytest.mark.parametrize("corruption", ["stale", "unowned", "wrong-model"])
async def test_incremental_rejects_invalid_unused_mapping_before_creation(
    db_session: AsyncSession, kind: str, corruption: str
) -> None:
    user = uuid.uuid4()
    entity_id = uuid.uuid4()
    if corruption != "stale":
        owner = uuid.uuid4() if corruption == "unowned" else user
        use_account = (kind == "account") != (corruption == "wrong-model")
        if use_account:
            entity = await create_account(
                db_session, owner, AccountCreate(name="Foreign", type="checking")
            )
        else:
            entity = await create_category(
                db_session, owner, CategoryCreate(name="Foreign", type="expense")
            )
        entity_id = entity.id
    await importer._store_mapping(db_session, user, kind, "invalid", entity_id)
    initial = (
        await db_session.scalar(select(func.count(Account.id))),
        await db_session.scalar(select(func.count(Category.id))),
    )
    parser = SimpleNamespace(
        get_accounts=lambda: [
            {
                "actual_id": source_id,
                "name": source_id,
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
            }
            for source_id in (["new", "invalid"] if kind == "account" else ["new"])
        ],
        get_categories=lambda: (
            [
                {
                    "actual_id": "invalid",
                    "name": "Invalid",
                    "type": "expense",
                    "group_actual_id": None,
                }
            ]
            if kind == "category"
            else []
        ),
        get_category_groups=lambda: (
            [{"actual_id": "invalid", "name": "Invalid", "type": "expense"}]
            if kind == "category_group"
            else []
        ),
    )
    with pytest.raises(importer.LegacyActualMappingError):
        await importer.resolve_ids(db_session, user, parser, [])
    assert (
        await db_session.scalar(select(func.count(Account.id))),
        await db_session.scalar(select(func.count(Category.id))),
    ) == initial


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("corruption", ["wrong-parent", "nested-group", "missing-group"])
async def test_incremental_rejects_unused_category_hierarchy_before_creation(
    db_session: AsyncSession, corruption: str
) -> None:
    user = uuid.uuid4()
    group = await create_category(db_session, user, CategoryCreate(name="Group", type="expense"))
    category = await create_category(
        db_session,
        user,
        CategoryCreate(
            name="Category",
            type="expense",
            parent_id=group.id if corruption == "nested-group" else None,
        ),
    )
    initial_categories = 2
    if corruption == "nested-group":
        parent = await create_category(
            db_session, user, CategoryCreate(name="Root", type="expense")
        )
        group.parent_id = parent.id
        initial_categories += 1
    await importer._store_mapping(db_session, user, "category", "c", category.id)
    if corruption != "missing-group":
        await importer._store_mapping(db_session, user, "category_group", "g", group.id)
    parser = SimpleNamespace(
        get_accounts=lambda: [
            {
                "actual_id": "new",
                "name": "New",
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
            }
        ],
        get_categories=lambda: [
            {"actual_id": "c", "name": "Category", "type": "expense", "group_actual_id": "g"}
        ],
        get_category_groups=lambda: [{"actual_id": "g", "name": "Group", "type": "expense"}],
    )
    with pytest.raises(importer.LegacyActualMappingError):
        await importer.resolve_ids(db_session, user, parser, [])
    assert await db_session.scalar(select(func.count(Account.id))) == 0
    assert await db_session.scalar(select(func.count(Category.id))) == initial_categories


@pytest.mark.integration
@pytest.mark.asyncio
async def test_legacy_partial_mappings_can_still_infer_owned_group(
    db_session: AsyncSession,
) -> None:
    user = uuid.uuid4()
    account = await create_account(db_session, user, AccountCreate(name="Legacy", type="checking"))
    group = await create_category(db_session, user, CategoryCreate(name="Group", type="expense"))
    category = await create_category(
        db_session, user, CategoryCreate(name="Legacy", type="expense", parent_id=group.id)
    )
    txn = await create_transaction(
        db_session,
        user,
        TransactionCreate(
            transaction_date=date(2026, 10, 1),
            description="[actual:legacy] preserve",
            type="expense",
            source="actual",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=100,
                    base_amount_pln=100,
                    direction="credit",
                ),
            ],
        ),
    )
    await importer._store_mapping(db_session, user, "account", "a", account.id)
    await importer._store_mapping(db_session, user, "category", "c", category.id)
    parser = SimpleNamespace(
        get_accounts=lambda: [
            {
                "actual_id": "a",
                "name": "Legacy",
                "type": "checking",
                "currency": "PLN",
                "is_budget_account": True,
            }
        ],
        get_categories=lambda: [
            {"actual_id": "c", "name": "Legacy", "type": "expense", "group_actual_id": "g"}
        ],
        get_category_groups=lambda: [{"actual_id": "g", "name": "Group", "type": "expense"}],
    )
    source = [
        {
            "actual_id": "legacy",
            "postings": [
                {
                    "account_actual_id": "a",
                    "category_actual_id": None,
                    "source_amount": 100,
                    "source_currency": "PLN",
                    "direction": "credit",
                },
                {
                    "account_actual_id": "a",
                    "category_actual_id": "c",
                    "source_amount": 100,
                    "source_currency": "PLN",
                    "direction": "debit",
                },
            ],
        }
    ]
    acct_map, cat_map, group_map, _, _ = await importer.resolve_ids(
        db_session, user, parser, source
    )
    assert (
        acct_map == {"a": account.id}
        and cat_map == {"c": category.id}
        and group_map == {"g": group.id}
    )
    assert await db_session.scalar(select(func.count(Account.id))) == 1
    assert await db_session.scalar(select(func.count(Category.id))) == 2
    assert await importer._get_mapping_id(db_session, user, "category_group", "g") == group.id
    assert txn.description == "[actual:legacy] preserve"
