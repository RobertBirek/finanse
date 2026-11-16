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
from tests.database_safety import (
    IDENTITY_SQL,
    DatabasePermit,
    DatabaseSafetyError,
    load_permit,
    verify_asyncpg,
)


@dataclass(frozen=True)
class ScratchIdentity:
    name: str
    oid: int
    role: str
    system_identifier: str


@dataclass(frozen=True)
class MigrationDatabase:
    url: str = field(repr=False)
    connection: asyncpg.Connection
    backend: Path
    permit: DatabasePermit
    identity: ScratchIdentity

    async def verify_child(self) -> None:
        try:
            parsed = make_url(self.url)
            if parsed.database != self.identity.name:
                raise DatabaseSafetyError("Foreign scratch URL")
            parent_url = parsed.set(database="finanse_test").render_as_string(hide_password=False)
            if load_permit(parent_url, os.environ) != self.permit:
                raise DatabaseSafetyError("Foreign scratch permit")
            row = await self.connection.fetchrow(IDENTITY_SQL)
            expected = {
                "database": self.identity.name,
                "role": self.identity.role,
                "owner": self.identity.role,
                "oid": self.identity.oid,
                "system_identifier": self.identity.system_identifier,
            }
            if row is None or any(row[key] != value for key, value in expected.items()):
                raise DatabaseSafetyError("Scratch database identity changed")
        except Exception:  # noqa: BLE001 - fail closed without exposing DSN/driver credentials
            raise DatabaseSafetyError("Scratch database verification refused") from None

    async def migrate(self, command: str, target: str) -> str:
        import asyncio

        if command not in {"upgrade", "downgrade"}:
            raise ValueError("Only real migration commands are supported")
        await self.verify_child()
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
    permit = load_permit(url, os.environ)
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
        "timeout": 5,
        "command_timeout": 5,
    }
    admin = await asyncpg.connect(database=parsed.database, **options)
    name = "finanse_bank_import_migration_" + uuid.uuid4().hex
    connection: asyncpg.Connection | None = None
    oid: int | None = None
    try:
        await verify_asyncpg(admin, permit)
        await admin.execute(f'CREATE DATABASE "{name}"')
        oid = await admin.fetchval(
            "SELECT oid FROM pg_database WHERE datname=$1 AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
            name,
        )
        if oid is None:
            raise RuntimeError("New test database ownership was not confirmed")
        connection = await asyncpg.connect(database=name, **options)
        database = MigrationDatabase(
            url=parsed.set(database=name).render_as_string(hide_password=False),
            connection=connection,
            backend=Path(__file__).resolve().parents[1],
            permit=permit,
            identity=ScratchIdentity(
                name=name,
                oid=oid,
                role=permit.target.role,
                system_identifier=permit.system_identifier,
            ),
        )
        await database.verify_child()
        yield database
    finally:
        try:
            if connection is not None:
                await connection.close()
            if oid is not None:
                await verify_asyncpg(admin, permit)
                actual = await admin.fetchval(
                    "SELECT oid FROM pg_database WHERE datname=$1 AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)",
                    name,
                )
                if actual != oid:
                    raise DatabaseSafetyError("Refuse cleanup: scratch ownership/OID changed")
                active = await admin.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE datid=$1", oid
                )
                if active:
                    raise DatabaseSafetyError("Refuse cleanup: scratch still has connections")
                await verify_asyncpg(admin, permit)
                await admin.execute(f'DROP DATABASE "{name}"')
        finally:
            await admin.close()
