import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User
from app.identity.service import hash_password
from app.main import app as _app  # noqa: F401
from tests.migration_fixtures import owned_migration_database  # noqa: F401


@pytest_asyncio.fixture
async def owner(db_session: AsyncSession) -> User:
    user = User(
        email=f"bank-import-{uuid.uuid4().hex}@example.test",
        display_name="Synthetic importer",
        password_hash=hash_password("only-a-synthetic-test-password"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def other_owner(db_session: AsyncSession) -> User:
    user = User(
        email=f"bank-import-other-{uuid.uuid4().hex}@example.test",
        display_name="Other synthetic importer",
        password_hash=hash_password("only-another-synthetic-test-password"),
    )
    db_session.add(user)
    await db_session.flush()
    return user
