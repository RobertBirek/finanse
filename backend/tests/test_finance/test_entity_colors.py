"""Account and category color contracts, isolated from the shared public schema."""

import importlib.util
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryCreate,
    CategoryUpdate,
    PostingCreate,
    TransactionCreate,
)
from app.finance.service import (
    create_account,
    create_category,
    create_transaction,
    get_account,
    get_categories,
)
from app.identity.router import get_current_user
from app.main import app
from tests.conftest import is_safe_test_database_url


@pytest_asyncio.fixture
async def color_db_session() -> AsyncGenerator[AsyncSession]:
    database_url = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+asyncpg://finanse:finanse@localhost:55432/finanse_test"
    )
    if not is_safe_test_database_url(database_url):
        raise ValueError("Unsafe color test database")
    schema = f"account_category_colors_{uuid.uuid4().hex}"
    engine = create_async_engine(
        database_url, pool_pre_ping=True, connect_args={"server_settings": {"search_path": schema}}
    )
    created = False
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            await connection.execute(text(f'SET search_path TO "{schema}"'))
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            await session.execute(text(f'SET search_path TO "{schema}"'))
            yield session
    finally:
        if created:
            async with engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


def test_color_schemas_accept_only_canonical_hex_or_null() -> None:
    assert AccountCreate(name="Cash", type="cash", color="#a1b2c3").color == "#A1B2C3"
    assert CategoryCreate(name="Food", type="expense", color="#00ff11").color == "#00FF11"
    assert AccountUpdate(color=None).model_dump(exclude_unset=True) == {"color": None}
    assert CategoryUpdate().model_dump(exclude_unset=True) == {}

    for schema in (AccountCreate, AccountUpdate, CategoryCreate, CategoryUpdate):
        base = (
            {"name": "Cash", "type": "cash"}
            if "Account" in schema.__name__
            else {"name": "Food", "type": "expense"}
        )
        if schema.__name__.endswith("Update"):
            base = {}
        for invalid in ("red", "#123", "#A1B2C3D", "#A1B2CZ", "var(--danger)", "#a1 b2c3"):
            with pytest.raises(ValidationError):
                schema.model_validate({**base, "color": invalid})


@pytest.mark.asyncio
async def test_color_services_persist_reset_and_preserve_ledger(
    color_db_session: AsyncSession,
) -> None:
    owner = uuid.uuid4()
    account = await create_account(
        color_db_session, owner, AccountCreate(name="Cash", type="cash", color="#abc123")
    )
    parent = await create_category(
        color_db_session, owner, CategoryCreate(name="Food", type="expense", color="#123abc")
    )
    child = await create_category(
        color_db_session,
        owner,
        CategoryCreate(name="Groceries", type="expense", parent_id=parent.id),
    )
    transaction = await create_transaction(
        color_db_session,
        owner,
        TransactionCreate(
            description="Ledger stays untouched",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id, source_amount=100, base_amount_pln=100, direction="debit"
                ),
                PostingCreate(
                    category_id=child.id, source_amount=100, base_amount_pln=100, direction="credit"
                ),
            ],
        ),
    )
    mapping_id = uuid.uuid4()
    await color_db_session.execute(
        text(
            "INSERT INTO actual_import_mappings (id, user_id, entity_type, actual_id, entity_id) "
            "VALUES (:id, :owner, 'category', 'immutable-mapping', :entity_id)"
        ),
        {"id": mapping_id, "owner": owner, "entity_id": child.id},
    )
    ledger_before = (
        await color_db_session.execute(
            text(
                "SELECT id, transaction_id, account_id, category_id, source_amount, base_amount_pln FROM postings ORDER BY id"
            )
        )
    ).all()
    entity_state_before = (
        await color_db_session.execute(
            text(
                "SELECT name, type, currency, source, is_active, is_budget_account "
                "FROM accounts WHERE id = :id"
            ),
            {"id": account.id},
        )
    ).one()
    category_state_before = (
        await color_db_session.execute(
            text("SELECT name, parent_id, type, source, is_active FROM categories WHERE id = :id"),
            {"id": child.id},
        )
    ).one()
    mappings_before = (
        await color_db_session.execute(
            text(
                "SELECT id, user_id, entity_type, actual_id, entity_id FROM actual_import_mappings"
            )
        )
    ).all()

    from app.finance.service import update_account, update_category

    await update_account(color_db_session, owner, account.id, AccountUpdate(color="#00ff11"))
    await update_category(color_db_session, owner, child.id, CategoryUpdate(color="#ff00aa"))
    await update_category(color_db_session, owner, child.id, CategoryUpdate())
    await update_account(color_db_session, owner, account.id, AccountUpdate(color=None))

    persisted_account = await get_account(color_db_session, owner, account.id)
    persisted_categories = {
        category.id: category for category in await get_categories(color_db_session, owner)
    }
    assert persisted_account is not None and persisted_account.color is None
    assert persisted_categories[parent.id].color == "#123ABC"
    assert persisted_categories[child.id].color == "#FF00AA"
    assert persisted_categories[child.id].parent_id == parent.id
    assert (
        entity_state_before
        == (
            await color_db_session.execute(
                text(
                    "SELECT name, type, currency, source, is_active, is_budget_account "
                    "FROM accounts WHERE id = :id"
                ),
                {"id": account.id},
            )
        ).one()
    )
    assert (
        category_state_before
        == (
            await color_db_session.execute(
                text(
                    "SELECT name, parent_id, type, source, is_active FROM categories WHERE id = :id"
                ),
                {"id": child.id},
            )
        ).one()
    )
    assert (
        mappings_before
        == (
            await color_db_session.execute(
                text(
                    "SELECT id, user_id, entity_type, actual_id, entity_id FROM actual_import_mappings"
                )
            )
        ).all()
    )
    assert transaction.id is not None
    assert (
        ledger_before
        == (
            await color_db_session.execute(
                text(
                    "SELECT id, transaction_id, account_id, category_id, source_amount, base_amount_pln FROM postings ORDER BY id"
                )
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_color_api_is_owner_scoped_persistent_and_database_checked(
    color_db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, other = uuid.uuid4(), uuid.uuid4()
    account = await create_account(color_db_session, owner, AccountCreate(name="Cash", type="cash"))
    category = await create_category(
        color_db_session, owner, CategoryCreate(name="Food", type="expense")
    )

    async def override_db() -> AsyncGenerator[AsyncSession]:
        yield color_db_session

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setitem(
        app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=owner)
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/finance/accounts/{account.id}", json={"color": "#abcdef"}
            )
            assert response.status_code == 200
            assert response.json()["color"] == "#ABCDEF"
            response = await client.get(f"/api/finance/accounts/{account.id}")
            assert response.status_code == 200
            assert response.json()["color"] == "#ABCDEF"
            response = await client.get("/api/finance/accounts")
            assert response.status_code == 200
            assert response.json()[0]["color"] == "#ABCDEF"

            response = await client.patch(
                f"/api/finance/categories/{category.id}", json={"color": "#fedcba"}
            )
            assert response.status_code == 200
            assert response.json()["color"] == "#FEDCBA"
            response = await client.get("/api/finance/categories")
            assert response.status_code == 200
            assert response.json()[0]["color"] == "#FEDCBA"
            response = await client.patch(
                f"/api/finance/categories/{category.id}", json={"color": None}
            )
            assert response.status_code == 200
            assert response.json()["color"] is None

            monkeypatch.setitem(
                app.dependency_overrides, get_current_user, lambda: SimpleNamespace(id=other)
            )
            response = await client.patch(
                f"/api/finance/accounts/{account.id}", json={"color": "#FFFFFF"}
            )
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()

    await color_db_session.execute(
        text("UPDATE accounts SET color = '#123456' WHERE id = :id"), {"id": account.id}
    )
    with pytest.raises(IntegrityError):
        await color_db_session.execute(
            text("UPDATE categories SET color = 'red' WHERE id = :id"), {"id": category.id}
        )


@pytest.mark.asyncio
async def test_color_migration_is_additive_and_preserves_legacy_ledger(
    color_db_session: AsyncSession,
) -> None:
    owner = uuid.uuid4()
    account = await create_account(
        color_db_session, owner, AccountCreate(name="Legacy cash", type="cash")
    )
    category = await create_category(
        color_db_session, owner, CategoryCreate(name="Legacy food", type="expense")
    )
    await create_transaction(
        color_db_session,
        owner,
        TransactionCreate(
            description="Legacy ledger",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account.id, source_amount=200, base_amount_pln=200, direction="debit"
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=200,
                    base_amount_pln=200,
                    direction="credit",
                ),
            ],
        ),
    )
    await color_db_session.commit()
    ledger_before = (
        await color_db_session.execute(text("SELECT * FROM postings ORDER BY id"))
    ).all()
    await color_db_session.execute(
        text("ALTER TABLE accounts DROP CONSTRAINT ck_accounts_color_hex")
    )
    await color_db_session.execute(
        text("ALTER TABLE categories DROP CONSTRAINT ck_categories_color_hex")
    )
    await color_db_session.execute(text("ALTER TABLE accounts DROP COLUMN color"))
    await color_db_session.execute(text("ALTER TABLE categories DROP COLUMN color"))
    await color_db_session.commit()

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/f3a9d17c2e4b_add_entity_colors.py"
    )
    spec = importlib.util.spec_from_file_location("add_entity_colors", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await color_db_session.connection()

    def upgrade(sync_connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(sync_connection)):
            migration.upgrade()

    await connection.run_sync(upgrade)
    assert (
        ledger_before
        == (await color_db_session.execute(text("SELECT * FROM postings ORDER BY id"))).all()
    )
    assert (
        await color_db_session.execute(
            text("SELECT color FROM accounts WHERE id = :id"), {"id": account.id}
        )
    ).scalar_one() is None
    with pytest.raises(IntegrityError):
        await color_db_session.execute(
            text("UPDATE accounts SET color = 'blue' WHERE id = :id"), {"id": account.id}
        )


@pytest.mark.parametrize("saved_table", ["accounts", "categories"])
async def test_color_downgrade_refuses_saved_preferences_before_dropping_any_column(
    color_db_session: AsyncSession, saved_table: str
) -> None:
    owner = uuid.uuid4()
    account = await create_account(
        color_db_session,
        owner,
        AccountCreate(
            name="Cash", type="cash", color="#123ABC" if saved_table == "accounts" else None
        ),
    )
    category = await create_category(
        color_db_session,
        owner,
        CategoryCreate(
            name="Food", type="expense", color="#456DEF" if saved_table == "categories" else None
        ),
    )
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/f3a9d17c2e4b_add_entity_colors.py"
    )
    spec = importlib.util.spec_from_file_location("color_retention_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await color_db_session.connection()

    def downgrade(conn: Connection) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()

    with pytest.raises(RuntimeError, match="saved colors"):
        await connection.run_sync(downgrade)
    assert (
        await color_db_session.execute(
            text("SELECT color FROM accounts WHERE id=:id"), {"id": account.id}
        )
    ).scalar_one() == ("#123ABC" if saved_table == "accounts" else None)
    assert (
        await color_db_session.execute(
            text("SELECT color FROM categories WHERE id=:id"), {"id": category.id}
        )
    ).scalar_one() == ("#456DEF" if saved_table == "categories" else None)


async def test_color_empty_downgrade_reupgrade_preserves_legacy_rows(
    color_db_session: AsyncSession,
) -> None:
    owner = uuid.uuid4()
    await create_account(color_db_session, owner, AccountCreate(name="Cash", type="cash"))
    await create_category(color_db_session, owner, CategoryCreate(name="Food", type="expense"))
    before = {
        table: (
            await color_db_session.execute(
                text(f"SELECT (to_jsonb(t)-'color')::text FROM {table} t ORDER BY id")
            )
        )
        .scalars()
        .all()
        for table in ["accounts", "categories"]
    }
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/f3a9d17c2e4b_add_entity_colors.py"
    )
    spec = importlib.util.spec_from_file_location("color_empty_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await color_db_session.connection()

    def roundtrip(conn: Connection) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            migration.upgrade()

    await connection.run_sync(roundtrip)
    for table, rows in before.items():
        assert (
            await color_db_session.execute(
                text(f"SELECT (to_jsonb(t)-'color')::text FROM {table} t ORDER BY id")
            )
        ).scalars().all() == rows
        assert (
            await color_db_session.scalar(
                text(f"SELECT count(*) FROM {table} WHERE color IS NOT NULL")
            )
            == 0
        )
