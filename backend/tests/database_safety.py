"""Fail-closed test DB permits. No application data or implicit local approval."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import stat
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncConnection

from ci_tools.partition import GROUPS

IDENTITY_SQL = """
SELECT current_database() AS database, current_user AS role,
       pg_get_userbyid(d.datdba) AS owner, d.oid AS oid,
       (SELECT system_identifier::text FROM pg_control_system()) AS system_identifier,
       shobj_description(d.oid, 'pg_database') AS nonce
FROM pg_database d WHERE d.datname = current_database()
"""
PUBLIC_OBJECTS_SQL = """
SELECT EXISTS (
 SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public'
 UNION ALL
 SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname='public'
 UNION ALL
 SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
 WHERE n.nspname='public'
)
"""
MAX_PERMIT_BYTES = 16384


class DatabaseSafetyError(ValueError):
    """Deliberately credential-free safety failure; never a skippable DB outage."""


@dataclass(frozen=True)
class DatabaseTarget:
    driver: str
    host: str
    port: int
    database: str
    role: str


@dataclass(frozen=True)
class DatabasePermit:
    target: DatabaseTarget
    db_oid: int
    system_identifier: str
    db_owner: str
    nonce: str = field(repr=False)
    run_id: str
    run_attempt: str
    job: str
    group: str
    commit: str
    version: int = 1
    purpose: str = "advisor-test-db-lifecycle"
    issuer: str = "github-ephemeral-postgres"


def _target(url: str) -> DatabaseTarget:
    try:
        parsed = make_url(url)
        if (
            parsed.drivername != "postgresql+asyncpg"
            or parsed.host not in {"127.0.0.1", "localhost"}
            or parsed.port not in {5432, 55432}
            or parsed.database != "finanse_test"
            or not re.fullmatch(r"bank_import_task_[0-9a-f]+", parsed.username or "")
            or parsed.query
        ):
            raise DatabaseSafetyError("Test database target refused")
        return DatabaseTarget(
            parsed.drivername,
            str(parsed.host),
            int(parsed.port),
            parsed.database,
            str(parsed.username),
        )
    except (ArgumentError, ValueError, TypeError):
        raise DatabaseSafetyError("Test database target refused") from None


def _context(environ: Mapping[str, str]) -> dict[str, str]:
    context = {
        "run_id": environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": environ.get("GITHUB_JOB", ""),
        "group": environ.get("ADVISOR_TEST_DB_GROUP", ""),
        "commit": environ.get("ADVISOR_TEST_DB_COMMIT", ""),
    }
    if (
        environ.get("GITHUB_ACTIONS") != "true"
        or "PYTEST_XDIST_WORKER" in environ
        or not re.fullmatch(r"[1-9][0-9]*", context["run_id"])
        or not re.fullmatch(r"[1-9][0-9]*", context["run_attempt"])
        or context["job"] != "backend_tests"
        or context["group"] not in GROUPS
        or not re.fullmatch(r"[0-9a-f]{40}", context["commit"])
    ):
        raise DatabaseSafetyError("Explicit ephemeral test-run context required")
    return context


def _directory(path: Path) -> int:
    if not path.is_absolute():
        raise DatabaseSafetyError("Absolute private permit path required")
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        os.close(descriptor)
        raise DatabaseSafetyError("Private owned permit directory required")
    return descriptor


def load_permit(url: str, environ: Mapping[str, str]) -> DatabasePermit:
    """Read a private permit and validate all context before any fixture DB I/O."""
    try:
        target = _target(url)
        context = _context(environ)
        path = Path(environ.get("ADVISOR_TEST_DB_PERMIT", ""))
        directory = _directory(path)
        try:
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
            )
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077
                    or info.st_size > MAX_PERMIT_BYTES
                ):
                    raise DatabaseSafetyError("Private owned bounded permit file required")
                data = json.loads(stream.read(MAX_PERMIT_BYTES + 1))
        finally:
            os.close(directory)
        keys = set(DatabasePermit.__dataclass_fields__)
        if (
            not isinstance(data, dict)
            or set(data) != keys
            or type(data["version"]) is not int
            or data["version"] != 1
            or data["purpose"] != "advisor-test-db-lifecycle"
            or data["issuer"] != "github-ephemeral-postgres"
            or data["target"] != asdict(target)
            or type(data["target"]["port"]) is not int
            or any(data[key] != value for key, value in context.items())
            or type(data["db_oid"]) is not int
            or not 0 < data["db_oid"] < 2**32
            or not isinstance(data["system_identifier"], str)
            or not re.fullmatch(r"[1-9][0-9]*", data["system_identifier"])
            or data["db_owner"] != target.role
            or not isinstance(data["nonce"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", data["nonce"])
        ):
            raise DatabaseSafetyError("Invalid or foreign test-run permit")
        return DatabasePermit(**(data | {"target": target}))
    except (OSError, ValueError, TypeError, KeyError):
        raise DatabaseSafetyError("Test database permit missing, unsafe or foreign") from None


def _base_identity(target: DatabaseTarget, observed: Mapping[str, object]) -> None:
    if (
        observed.get("database") != target.database
        or observed.get("role") != target.role
        or observed.get("owner") != target.role
        or type(observed.get("oid")) is not int
        or not 0 < int(str(observed["oid"])) < 2**32
        or not isinstance(observed.get("system_identifier"), str)
        or not re.fullmatch(r"[1-9][0-9]*", str(observed["system_identifier"]))
    ):
        raise DatabaseSafetyError("PostgreSQL test database identity refused")


def check_identity(permit: DatabasePermit, observed: Mapping[str, object]) -> None:
    _base_identity(permit.target, observed)
    if (
        observed.get("oid") != permit.db_oid
        or observed.get("system_identifier") != permit.system_identifier
        or observed.get("nonce") != permit.nonce
    ):
        raise DatabaseSafetyError("PostgreSQL test database identity changed")


async def verify_sqlalchemy(connection: AsyncConnection, permit: DatabasePermit) -> None:
    try:
        row = (await connection.execute(text(IDENTITY_SQL))).mappings().one()
        check_identity(permit, dict(row))
    except Exception:  # noqa: BLE001 - fail closed and redact driver/SQL exception credentials
        raise DatabaseSafetyError("PostgreSQL identity verification refused") from None


async def verify_asyncpg(connection: asyncpg.Connection, permit: DatabasePermit) -> None:
    try:
        row = await connection.fetchrow(IDENTITY_SQL)
        if row is None:
            raise DatabaseSafetyError("Missing database identity")
        check_identity(permit, dict(row))
    except Exception:  # noqa: BLE001 - fail closed and redact driver/SQL exception credentials
        raise DatabaseSafetyError("PostgreSQL identity verification refused") from None


async def _connect(url: str) -> asyncpg.Connection:
    # The raw DSN never appears in an exception or repr produced by this helper.
    dsn = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    return await asyncpg.connect(dsn, timeout=5, command_timeout=5)


async def verify_target(url: str, permit: DatabasePermit) -> None:
    connection = None
    try:
        if _target(url) != permit.target:
            raise DatabaseSafetyError("Foreign probe target")
        connection = await _connect(url)
        await verify_asyncpg(connection, permit)
    except Exception:  # noqa: BLE001 - redact connection/driver credentials at the safety boundary
        raise DatabaseSafetyError("Test database readonly probe refused") from None
    finally:
        if connection is not None:
            await connection.close()


def _refuse_existing(directory: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise DatabaseSafetyError("Permit destination already exists")


def _publish(directory: int, name: str, permit: DatabasePermit) -> None:
    temporary = secrets.token_hex(16) + ".tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory,
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(asdict(permit), stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    finally:
        os.unlink(temporary, dir_fd=directory)


async def issue_ci_permit(url: str, path: Path, environ: Mapping[str, str]) -> None:
    """Called only by the trusted job provisioning a new ephemeral PostgreSQL."""
    directory = None
    connection = None
    try:
        target = _target(url)
        context = _context(environ)
        directory = _directory(path)
        _refuse_existing(directory, path.name)
        connection = await _connect(url)
        row = await connection.fetchrow(IDENTITY_SQL)
        if row is None:
            raise DatabaseSafetyError("Missing fresh database identity")
        _base_identity(target, dict(row))
        if row["nonce"] is not None or await connection.fetchval(PUBLIC_OBJECTS_SQL):
            raise DatabaseSafetyError("Fresh empty unmarked ephemeral database required")
        permit = DatabasePermit(
            target=target,
            db_oid=row["oid"],
            system_identifier=row["system_identifier"],
            db_owner=row["owner"],
            nonce=secrets.token_hex(16),
            run_id=context["run_id"],
            run_attempt=context["run_attempt"],
            job=context["job"],
            group=context["group"],
            commit=context["commit"],
        )
        quoted = await connection.fetchval("SELECT quote_literal($1::text)", permit.nonce)
        if quoted != "'" + permit.nonce + "'":
            raise DatabaseSafetyError("Unexpected server quoting")
        # COMMENT is a utility command: only the server-quoted literal is inserted.
        await connection.execute('COMMENT ON DATABASE "finanse_test" IS ' + quoted)
        await verify_asyncpg(connection, permit)
        _publish(directory, path.name, permit)
    except Exception:  # noqa: BLE001 - no driver, SQL or filesystem details in issuer errors
        raise DatabaseSafetyError("Ephemeral test database permit issuance refused") from None
    finally:
        try:
            if connection is not None:
                await connection.close()
        finally:
            if directory is not None:
                os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue-ci-permit", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(
            issue_ci_permit(
                os.environ.get("TEST_DATABASE_URL", ""), args.issue_ci_permit, os.environ
            )
        )
    except DatabaseSafetyError:
        print("Ephemeral test DB permit refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
