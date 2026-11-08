"""Real Alembic test databases owned exclusively by an explicitly approved runner."""

import os
import re
import sys
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from tests.conftest import is_safe_test_database_url


@dataclass(frozen=True)
class MigrationDatabase:
    url: str = field(repr=False)
    connection: asyncpg.Connection
    backend: Path

    async def migrate(self, command: str, target: str) -> str:
        import asyncio

        if command not in {"upgrade", "downgrade"}:
            raise ValueError("Only real migration commands are supported")
        environment = os.environ.copy()
        environment["DATABASE_URL"] = self.url
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-m",
            "alembic",
            command,
            target,
            cwd=self.backend,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        text = stdout.decode()
        if process.returncode:
            raise RuntimeError(text)
        return text


@pytest_asyncio.fixture
async def owned_migration_database() -> AsyncIterator[MigrationDatabase]:
    url = os.environ.get("BANK_IMPORT_MIGRATION_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL", ""
    )
    if (
        not is_safe_test_database_url(url)
        or os.environ.get("BANK_IMPORT_MIGRATIONS_ALLOWED") != "owned_no_port_runner"
    ):
        pytest.fail("Real migration tests require the approved isolated runner, not an existing DB")
    parsed = make_url(url)
    if not parsed.username or not re.fullmatch(r"bank_import_task_[0-9a-f]+", parsed.username):
        pytest.fail("Migration runner must use its exclusively owned task role")
    options = {
        "host": parsed.host,
        "port": parsed.port,
        "user": parsed.username,
        "password": parsed.password,
    }
    admin = await asyncpg.connect(database=parsed.database, **options)
    name = "finanse_bank_import_migration_" + uuid.uuid4().hex
    connection: asyncpg.Connection | None = None
    oid: int | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        oid = await admin.fetchval(
            "SELECT oid FROM pg_database WHERE datname=$1 AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
            name,
        )
        if oid is None:
            raise RuntimeError("New test database ownership was not confirmed")
        connection = await asyncpg.connect(database=name, **options)
        yield MigrationDatabase(
            url=parsed.set(database=name).render_as_string(hide_password=False),
            connection=connection,
            backend=Path(__file__).resolve().parents[1],
        )
    finally:
        if connection is not None:
            await connection.close()
        if oid is not None:
            actual = await admin.fetchval(
                "SELECT oid FROM pg_database WHERE datname=$1 AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                name,
            )
            if actual != oid:
                raise RuntimeError("Refuse cleanup: scratch database ownership/OID changed")
            active = await admin.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE datid=$1", oid
            )
            if active:
                raise RuntimeError("Refuse cleanup: owned scratch database still has connections")
            await admin.execute(f'DROP DATABASE "{name}"')
        await admin.close()
