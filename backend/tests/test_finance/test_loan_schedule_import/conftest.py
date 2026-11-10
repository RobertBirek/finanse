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
        email=f"schedule-{uuid.uuid4().hex}@example.test",
        display_name="Synthetic schedule owner",
        password_hash=hash_password("synthetic-schedule-password"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def other_owner(db_session: AsyncSession) -> User:
    user = User(
        email=f"schedule-other-{uuid.uuid4().hex}@example.test",
        display_name="Other synthetic schedule owner",
        password_hash=hash_password("synthetic-other-schedule-password"),
    )
    db_session.add(user)
    await db_session.flush()
    return user
