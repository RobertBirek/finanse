import asyncio
import os
import socket

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse_test"
SAFE_TEST_DATABASE_HOSTS = {"localhost", "127.0.0.1"}
SAFE_TEST_DATABASE_PORTS = {5432, 55432}

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    DEFAULT_TEST_DATABASE_URL,
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def is_safe_test_database_url(database_url: str) -> bool:
    try:
        parsed_url = make_url(database_url)
    except (ArgumentError, ValueError):
        return False

    return (
        parsed_url.drivername == "postgresql+asyncpg"
        and parsed_url.host in SAFE_TEST_DATABASE_HOSTS
        and parsed_url.port in SAFE_TEST_DATABASE_PORTS
        and parsed_url.database == "finanse_test"
    )


def is_connection_unavailable_error(error: BaseException) -> bool:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(
            current,
            (
                ConnectionError,
                socket.gaierror,
                TimeoutError,
                asyncpg.PostgresConnectionError,
                asyncpg.exceptions.CannotConnectNowError,
            ),
        ):
            return True

        pending.extend(
            related
            for related in (
                getattr(current, "orig", None),
                current.__cause__,
                current.__context__,
            )
            if related is not None
        )
    return False


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_database(request):
    if request.node.get_closest_marker("integration") is None:
        yield None
        return

    if not is_safe_test_database_url(TEST_DATABASE_URL):
        pytest.skip(
            "Unsafe TEST_DATABASE_URL: integration schema create/drop requires a local "
            "PostgreSQL database named finanse_test on port 5432 or 55432"
        )

    from app.database import Base

    engine = None
    schema_created = False
    try:
        engine = create_async_engine(TEST_DATABASE_URL, echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            schema_created = True
        except (OperationalError, OSError) as exc:
            if not is_connection_unavailable_error(exc):
                raise
            database_url = make_url(TEST_DATABASE_URL)
            pytest.skip(
                "PostgreSQL test database unavailable at "
                f"{database_url.host or 'unknown'}:{database_url.port or 5432}: "
                f"{type(exc).__name__}"
            )

        yield engine
    finally:
        if engine is not None:
            try:
                if schema_created:
                    async with engine.begin() as conn:
                        await conn.run_sync(Base.metadata.drop_all)
            finally:
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
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
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
