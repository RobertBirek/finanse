import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_database(request):
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    from app.database import Base

    if request.node.get_closest_marker("integration") is None:
        await engine.dispose()
        yield None
        return

    schema_created = False
    try:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            schema_created = True
        except (OperationalError, OSError) as exc:
            database_url = make_url(TEST_DATABASE_URL)
            pytest.skip(
                "PostgreSQL test database unavailable at "
                f"{database_url.host or 'unknown'}:{database_url.port or 5432}: "
                f"{type(exc).__name__}"
            )

        yield engine
    finally:
        if schema_created:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_database):
    if test_database is None:
        pytest.skip("db_session requires the @pytest.mark.integration marker")

    async_session = async_sessionmaker(test_database, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session):
    from app.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app, raise_server_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_data():
    return {
        "email": "test@example.com",
        "password": "testpassword123",
        "display_name": "Test User",
    }


@pytest.fixture
def sample_account_data():
    return {
        "name": "Alior Bank",
        "type": "checking",
        "currency": "PLN",
    }


@pytest.fixture
def sample_category_data():
    return {
        "name": "Jedzenie",
        "type": "expense",
    }
