"""Owned-schema fixtures: never create/drop shared public or production tables."""

import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import Base
from app.finance.models import (
    Account,
    ActualImportMapping,
    Category,
    CategoryBudget,
    FinancialDocument,
    FinancialTransaction,
    Posting,
    ScheduledFinanceItem,
)
from app.identity.models import User
from app.main import app as _app  # noqa: F401 - register full metadata, no lifespan
from tests.conftest import is_safe_test_database_url
from tests.test_finance.category_tree_cases import cases, uid


async def apply_categories_only(db: AsyncSession, owner: UUID, plan: object) -> dict[str, UUID]:
    """Fixture setup through existing services, not the operator under test."""
    from typing import Any, cast

    from app.finance.entities import create_category, update_category
    from app.finance.schemas import CategoryCreate, CategoryUpdate
    from scripts.category_tree_manifest import NewRef, PreparedTree

    prepared = cast(PreparedTree, plan)
    ids: dict[str, UUID] = {}

    def resolve(parent: UUID | NewRef | None) -> UUID | None:
        return ids[parent.key] if isinstance(parent, NewRef) else parent

    for node in prepared.creates:
        row = await create_category(
            db,
            owner,
            CategoryCreate(name=node.name, parent_id=resolve(node.parent), type="expense"),
        )
        ids[node.key] = row.id
    for patch in prepared.patches:
        changes: dict[str, Any] = {}
        if patch.name is not None:
            changes["name"] = patch.name
        if patch.parent_changed:
            changes["parent_id"] = resolve(patch.parent)
        await update_category(db, owner, patch.id, CategoryUpdate(**changes))
    await db.flush()
    return ids


@pytest_asyncio.fixture(autouse=True)
async def test_database(request: pytest.FixtureRequest) -> AsyncIterator[AsyncEngine | None]:
    if request.node.get_closest_marker("integration") is None:
        yield None
        return
    url = os.environ["TEST_DATABASE_URL"]
    assert is_safe_test_database_url(url), "Refusing non-local/non-test schema lifecycle"
    schema = "category_tree_test_" + uuid4().hex
    admin = create_async_engine(url, echo=False)
    engine = create_async_engine(
        url, echo=False, connect_args={"server_settings": {"search_path": schema}}
    )
    created = False
    try:
        async with admin.begin() as db:
            await db.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        async with engine.begin() as db:
            await db.run_sync(Base.metadata.create_all)
            await db.execute(
                text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)")
            )
            await db.execute(text("INSERT INTO alembic_version VALUES ('7b57f2f0bde6')"))
        yield engine
    finally:
        await engine.dispose()
        if created:
            async with admin.begin() as db:
                await db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed_owner(db: AsyncSession, *, source_tree: bool = True) -> UUID:
    owner = uuid4()
    db.add(
        User(
            id=owner,
            email=f"{owner}@test.invalid",
            password_hash="test-only",
            display_name="Synthetic",
        )
    )
    await db.flush()
    if source_tree:
        data, _ = cases()
        rows = data["categories"]
        for roots in (True, False):
            for row in rows:
                if (row["parent_id"] is None) == roots:
                    db.add(
                        Category(
                            id=UUID(row["id"]),
                            user_id=owner,
                            name=row["name"],
                            parent_id=UUID(row["parent_id"]) if row["parent_id"] else None,
                            type=row["type"],
                            source=row["source"],
                            is_active=row["is_active"],
                        )
                    )
            await db.flush()
    await db.commit()
    return owner


async def seed_ordinary_refs(db: AsyncSession, owner: UUID) -> dict[str, UUID]:
    account = Account(user_id=owner, name="Test account", type="checking", currency="PLN")
    db.add(account)
    await db.flush()
    transaction = FinancialTransaction(
        user_id=owner, date=date(2026, 1, 1), description="Test", type="expense", source="actual"
    )
    bill = FinancialDocument(user_id=owner, kind="invoice", category_id=uid(0), review="draft")
    db.add_all([transaction, bill])
    await db.flush()
    db.add_all(
        [
            Posting(
                transaction_id=transaction.id,
                account_id=account.id,
                source_amount=100,
                source_currency="PLN",
                base_amount_pln=100,
                fx_rate=1,
                direction="credit",
            ),
            Posting(
                transaction_id=transaction.id,
                category_id=uid(0),
                source_amount=100,
                source_currency="PLN",
                base_amount_pln=100,
                fx_rate=1,
                direction="debit",
            ),
            CategoryBudget(user_id=owner, category_id=uid(0), amount_pln=1000),
            ScheduledFinanceItem(
                user_id=owner,
                name="Test schedule",
                type="expense",
                account_id=account.id,
                category_id=uid(0),
                currency="PLN",
                due_day=10,
                amount_method="fixed",
                fixed_amount_pln=100,
            ),
            ActualImportMapping(
                user_id=owner, entity_type="category", actual_id="test-category", entity_id=uid(0)
            ),
            ActualImportMapping(
                user_id=owner,
                entity_type="category_group",
                actual_id="test-group",
                entity_id=uid(1),
            ),
        ]
    )
    await db.commit()
    return {"account": account.id, "transaction": transaction.id, "bill": bill.id}
