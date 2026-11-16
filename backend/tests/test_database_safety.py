"""Offline guard contracts: external database adapters are always replaced."""

from __future__ import annotations

import inspect
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

URL = "postgresql+asyncpg://bank_import_task_c1:password-SENSITIVE@127.0.0.1:5432/finanse_test"
TARGET = {
    "driver": "postgresql+asyncpg",
    "host": "127.0.0.1",
    "port": 5432,
    "database": "finanse_test",
    "role": "bank_import_task_c1",
}
CONTEXT = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_RUN_ID": "100",
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_JOB": "backend_tests",
    "ADVISOR_TEST_DB_GROUP": "ordinary-1",
    "ADVISOR_TEST_DB_COMMIT": "a" * 40,
}


def module() -> Any:
    from tests import database_safety

    return database_safety


def document() -> dict[str, Any]:
    return {
        "version": 1,
        "purpose": "advisor-test-db-lifecycle",
        "issuer": "github-ephemeral-postgres",
        "target": dict(TARGET),
        "db_oid": 12345,
        "system_identifier": "987654321",
        "db_owner": "bank_import_task_c1",
        "nonce": "b" * 32,
        "run_id": "100",
        "run_attempt": "1",
        "job": "backend_tests",
        "group": "ordinary-1",
        "commit": "a" * 40,
    }


def observation() -> dict[str, Any]:
    return {
        "database": "finanse_test",
        "role": "bank_import_task_c1",
        "owner": "bank_import_task_c1",
        "oid": 12345,
        "system_identifier": "987654321",
        "nonce": "b" * 32,
    }


@pytest.fixture
def permit_file(tmp_path: Path) -> Path:
    tmp_path.chmod(0o700)
    path = tmp_path / "permit.json"
    path.write_text(json.dumps(document()))
    path.chmod(0o600)
    return path


def environment(path: Path) -> dict[str, str]:
    return CONTEXT | {"ADVISOR_TEST_DB_PERMIT": str(path)}


def test_valid_permit_is_not_a_credential_or_mutable_target(permit_file: Path) -> None:
    safety = module()
    permit = safety.load_permit(URL, environment(permit_file))
    safety.check_identity(permit, observation())
    assert "password-SENSITIVE" not in repr(permit)
    assert "b" * 32 not in repr(permit)
    with pytest.raises((AttributeError, TypeError)):
        permit.nonce = "c" * 32
    with pytest.raises((AttributeError, TypeError)):
        permit.target.database = "production"


@pytest.mark.parametrize("env", [{}, {"CI": "true"}, {"GITHUB_ACTIONS": "true"}, CONTEXT])
def test_no_implicit_allowlist(env: dict[str, str]) -> None:
    with pytest.raises(module().DatabaseSafetyError):
        module().load_permit(URL, env)


@pytest.mark.parametrize(
    "case",
    ["relative", "symlink", "fifo", "public", "parent_public", "too_large", "json", "owner"],
)
def test_invalid_private_permit_refused(
    permit_file: Path, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = module()
    path = permit_file
    if case == "relative":
        path = Path("permit.json")
    elif case == "symlink":
        path = permit_file.parent / "link"
        path.symlink_to(permit_file)
    elif case == "fifo":
        permit_file.unlink()
        os.mkfifo(permit_file, 0o600)
    elif case == "public":
        permit_file.chmod(0o644)
    elif case == "parent_public":
        permit_file.parent.chmod(0o755)
    elif case == "too_large":
        permit_file.write_text("x" * 16385)
    elif case == "json":
        permit_file.write_text("{broken")
    elif case == "owner":
        monkeypatch.setattr(safety.os, "geteuid", lambda: -1)
    with pytest.raises(safety.DatabaseSafetyError):
        safety.load_permit(URL, environment(path))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("version", True),
        ("purpose", "other"),
        ("issuer", "local-adoption"),
        ("db_oid", True),
        ("system_identifier", "0"),
        ("db_owner", "other"),
        ("nonce", "bad"),
        ("run_id", "99"),
        ("run_attempt", "2"),
        ("job", "other"),
        ("group", "ordinary-2"),
        ("commit", "c" * 40),
        ("extra", "reuse"),
    ],
)
def test_permit_fields_bound_to_run(permit_file: Path, key: str, value: Any) -> None:
    data = document()
    data[key] = value
    permit_file.write_text(json.dumps(data))
    with pytest.raises(module().DatabaseSafetyError):
        module().load_permit(URL, environment(permit_file))


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("/finanse_test", "/finanse"),
        URL.replace("127.0.0.1", "production"),
        URL.replace("5432", "55431"),
        URL.replace("bank_import_task_c1", "finanse"),
        URL + "?host=production",
        URL.replace("+asyncpg", ""),
        "not-a-url",
        "postgresql+asyncpg:///finanse_test",
        URL.replace("127.0.0.1", "localhost"),
    ],
)
def test_target_mismatch_and_query_override_refused(permit_file: Path, url: str) -> None:
    with pytest.raises(module().DatabaseSafetyError) as error:
        module().load_permit(url, environment(permit_file))
    assert "password-SENSITIVE" not in str(error.value)


def test_parallel_worker_cannot_use_permit(permit_file: Path) -> None:
    with pytest.raises(module().DatabaseSafetyError):
        module().load_permit(URL, environment(permit_file) | {"PYTEST_XDIST_WORKER": "gw0"})


@pytest.mark.parametrize("key", list(observation()))
def test_each_identity_field_is_checked(permit_file: Path, key: str) -> None:
    safety = module()
    permit = safety.load_permit(URL, environment(permit_file))
    observed = observation()
    observed[key] = "wrong"
    with pytest.raises(safety.DatabaseSafetyError):
        safety.check_identity(permit, observed)


class FakePostgres:
    def __init__(self, *, fresh: bool = False) -> None:
        self.row = observation()
        if fresh:
            self.row["nonce"] = None
        self.nonempty = False
        self.closed = False
        self.executed: list[str] = []
        self.quoted: list[str] = []

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any]:
        return dict(self.row)

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "quote_literal" in query:
            self.quoted.append(args[0])
            return "'" + args[0] + "'"
        assert "EXISTS" in query
        return self.nonempty

    async def execute(self, query: str, *args: Any) -> None:
        self.executed.append(query)
        if query.startswith('COMMENT ON DATABASE "finanse_test" IS '):
            self.row["nonce"] = query.rsplit("'", 2)[1]

    async def close(self) -> None:
        self.closed = True


async def test_identity_adapters_use_database_facts_and_close_probe(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = module()
    permit = safety.load_permit(URL, environment(permit_file))
    pg = FakePostgres()
    await safety.verify_asyncpg(pg, permit)
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: observation()))
    connection = SimpleNamespace(execute=AsyncMock(return_value=result))
    await safety.verify_sqlalchemy(connection, permit)
    connect = AsyncMock(return_value=pg)
    monkeypatch.setattr(safety.asyncpg, "connect", connect)
    await safety.verify_target(URL, permit)
    assert pg.closed
    assert connect.call_args.kwargs["timeout"] == 5
    assert connect.call_args.kwargs["command_timeout"] == 5


async def test_probe_failure_is_redacted_and_connection_closed(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = module()
    pg = FakePostgres()
    pg.row["oid"] = 99
    monkeypatch.setattr(safety.asyncpg, "connect", AsyncMock(return_value=pg))
    with pytest.raises(safety.DatabaseSafetyError) as error:
        await safety.verify_target(URL, safety.load_permit(URL, environment(permit_file)))
    assert pg.closed and "password-SENSITIVE" not in str(error.value)


async def test_comment_uses_fixed_database_and_server_quoted_nonce(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = module()
    tmp_path.chmod(0o700)
    pg = FakePostgres(fresh=True)
    monkeypatch.setattr(safety.asyncpg, "connect", AsyncMock(return_value=pg))
    path = tmp_path / "permit.json"
    await safety.issue_ci_permit(URL, path, CONTEXT)
    assert len(pg.quoted) == 1
    assert pg.executed == [f"COMMENT ON DATABASE \"finanse_test\" IS '{pg.quoted[0]}'"]
    assert pg.closed
    assert path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    assert data["nonce"] == pg.quoted[0]
    assert "password-SENSITIVE" not in path.read_text()
    safety.check_identity(safety.load_permit(URL, environment(path)), pg.row)


@pytest.mark.parametrize("symlink", [False, True])
async def test_issuer_refuses_existing_destination_before_io(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch, symlink: bool
) -> None:
    safety = module()
    connect = AsyncMock(side_effect=AssertionError("existing path reached DB"))
    monkeypatch.setattr(safety.asyncpg, "connect", connect)
    path = permit_file
    if symlink:
        path = permit_file.parent / "link"
        path.symlink_to(permit_file)
    before = permit_file.read_bytes()
    with pytest.raises(safety.DatabaseSafetyError):
        await safety.issue_ci_permit(URL, path, CONTEXT)
    assert permit_file.read_bytes() == before
    connect.assert_not_awaited()


@pytest.mark.parametrize("failure", ["nonempty", "role", "context", "comment", "link"])
async def test_issuer_failure_does_not_publish_permit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    safety = module()
    tmp_path.chmod(0o700)
    path = tmp_path / "permit.json"
    pg = FakePostgres(fresh=True)
    pg.nonempty = failure == "nonempty"
    if failure == "role":
        pg.row["role"] = "other"
    if failure == "comment":
        monkeypatch.setattr(pg, "execute", AsyncMock(side_effect=RuntimeError("SENSITIVE")))
    if failure == "link":
        monkeypatch.setattr(safety.os, "link", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    connect = AsyncMock(return_value=pg)
    monkeypatch.setattr(safety.asyncpg, "connect", connect)
    with pytest.raises(safety.DatabaseSafetyError) as error:
        await safety.issue_ci_permit(URL, path, {} if failure == "context" else CONTEXT)
    assert not path.exists()
    assert "SENSITIVE" not in str(error.value)
    assert not list(tmp_path.glob("*.tmp"))
    if failure == "context":
        connect.assert_not_awaited()
    else:
        assert pg.closed


async def test_permit_publish_is_complete_and_no_clobber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    safety = module()
    tmp_path.chmod(0o700)
    pg = FakePostgres(fresh=True)
    monkeypatch.setattr(safety.asyncpg, "connect", AsyncMock(return_value=pg))
    original_link = os.link
    path = tmp_path / "permit.json"

    def race(source: Any, destination: Any, **kwargs: Any) -> None:
        path.write_bytes(b"concurrent-existing-permit")
        original_link(source, destination, **kwargs)

    monkeypatch.setattr(safety.os, "link", race)
    with pytest.raises(safety.DatabaseSafetyError):
        await safety.issue_ci_permit(URL, path, CONTEXT)
    assert path.read_bytes() == b"concurrent-existing-permit"
    assert not list(tmp_path.glob("*.tmp"))


def lifecycle_module(entry: str) -> Any:
    if entry == "global":
        from tests import conftest

        return conftest
    if entry == "category":
        from tests.test_finance import category_tree_database

        return category_tree_database
    if entry == "colors":
        from tests.test_finance import test_entity_colors

        return test_entity_colors
    if entry == "migration":
        from tests import migration_fixtures

        return migration_fixtures
    from tests.test_identity import test_sessions

    return test_sessions


def request_for(*, integration: bool = True) -> Any:
    return SimpleNamespace(
        node=SimpleNamespace(get_closest_marker=lambda _: object() if integration else None)
    )


def install_permit(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    for key, value in environment(path).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TEST_DATABASE_URL", URL)
    monkeypatch.setenv("BANK_IMPORT_MIGRATION_DATABASE_URL", URL)
    monkeypatch.setenv("BANK_IMPORT_MIGRATIONS_ALLOWED", "owned_no_port_runner")


def lifecycle_generator(entry: str, fixture: Any) -> Any:
    if entry in {"global", "category"}:
        return fixture.test_database.__wrapped__(request_for())
    if entry == "colors":
        return fixture.color_db_session.__wrapped__()
    return fixture.owned_migration_database.__wrapped__()


@pytest.mark.parametrize("entry", ["global", "category", "colors", "migration", "alembic"])
async def test_all_lifecycle_entries_refuse_before_io(
    monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    safety = module()
    fixture = lifecycle_module(entry)
    attempts: list[str] = []

    def forbidden(*args: Any, **kwargs: Any) -> None:
        attempts.append("io")
        raise AssertionError("Fixture reached I/O without a permit")

    monkeypatch.delenv("ADVISOR_TEST_DB_PERMIT", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", URL)
    monkeypatch.setenv("BANK_IMPORT_MIGRATION_DATABASE_URL", URL)
    monkeypatch.setenv("BANK_IMPORT_MIGRATIONS_ALLOWED", "owned_no_port_runner")
    if hasattr(fixture, "TEST_DATABASE_URL"):
        monkeypatch.setattr(fixture, "TEST_DATABASE_URL", URL)
    if hasattr(fixture, "create_async_engine"):
        monkeypatch.setattr(fixture, "create_async_engine", forbidden)
    monkeypatch.setattr(safety.asyncpg, "connect", forbidden)
    if entry == "alembic":
        monkeypatch.setattr(fixture.subprocess, "run", forbidden)
    with pytest.raises(safety.DatabaseSafetyError):
        if entry == "alembic":
            result = fixture.run_alembic("upgrade", "head")
            if inspect.isawaitable(result):
                await result
        else:
            await anext(lifecycle_generator(entry, fixture))
    assert attempts == []


async def test_unit_fixture_does_not_load_permit_or_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = lifecycle_module("global")
    monkeypatch.delenv("ADVISOR_TEST_DB_PERMIT", raising=False)
    generator = fixture.test_database.__wrapped__(request_for(integration=False))
    assert await anext(generator) is None
    await generator.aclose()


class AsyncContext:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSQLConnection:
    def __init__(self, events: list[str], *, fail_setup: bool = False) -> None:
        self.events = events
        self.row = observation()
        self.fail_setup = fail_setup

    async def execute(self, statement: Any) -> Any:
        sql = str(statement)
        if "current_database()" in sql:
            self.events.append("identity")
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: dict(self.row)))
        self.events.append(sql)
        return None

    async def run_sync(self, function: Any) -> None:
        self.events.append(function.__name__)
        if function.__name__ == "create_all" and self.fail_setup:
            raise RuntimeError("setup failure")


class FakeEngine:
    def __init__(self, events: list[str], *, fail_setup: bool = False) -> None:
        self.connection = FakeSQLConnection(events, fail_setup=fail_setup)
        self.closed = False

    def begin(self) -> AsyncContext:
        return AsyncContext(self.connection)

    async def dispose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("entry", ["global", "category", "colors"])
@pytest.mark.parametrize("phase", ["success", "setup_failure", "identity_cleanup", "body_failure"])
async def test_lifecycle_checks_before_ddl_and_releases_resources(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch, entry: str, phase: str
) -> None:
    safety = module()
    fixture = lifecycle_module(entry)
    install_permit(monkeypatch, permit_file)
    if hasattr(fixture, "TEST_DATABASE_URL"):
        monkeypatch.setattr(fixture, "TEST_DATABASE_URL", URL)
    events: list[str] = []
    engines: list[FakeEngine] = []

    def create_engine(*args: Any, **kwargs: Any) -> FakeEngine:
        engine = FakeEngine(events, fail_setup=phase == "setup_failure")
        engines.append(engine)
        return engine

    monkeypatch.setattr(fixture, "create_async_engine", create_engine)
    if entry == "colors":
        session = SimpleNamespace(execute=AsyncMock())
        monkeypatch.setattr(
            fixture,
            "async_sessionmaker",
            lambda *a, **kw: lambda: AsyncContext(session),
        )
    from app import database as app_database

    previous = (app_database.engine, app_database.async_session_factory)
    generator = lifecycle_generator(entry, fixture)
    if phase == "setup_failure":
        with pytest.raises(RuntimeError, match="setup failure"):
            await anext(generator)
    else:
        await anext(generator)
        if phase == "identity_cleanup":
            for engine in engines:
                engine.connection.row["nonce"] = "c" * 32
            with pytest.raises(safety.DatabaseSafetyError):
                await generator.aclose()
        elif phase == "body_failure":
            with pytest.raises(RuntimeError, match="body failure"):
                await generator.athrow(RuntimeError("body failure"))
        else:
            await generator.aclose()
    drops = [event for event in events if event == "drop_all" or event.startswith("DROP SCHEMA")]
    if phase in {"setup_failure", "identity_cleanup"}:
        assert drops == []
    else:
        assert len(drops) == 1
    for index, event in enumerate(events):
        if event in {"create_all", "drop_all"} or event.startswith(
            ("CREATE SCHEMA", "DROP SCHEMA")
        ):
            assert index > 0 and events[index - 1] == "identity", events
    assert engines and all(engine.closed for engine in engines)
    assert (app_database.engine, app_database.async_session_factory) == previous


class FakeMigrationAdmin(FakePostgres):
    def __init__(self) -> None:
        super().__init__()
        self.child = FakePostgres()
        self.child.row["oid"] = 54321
        self.child.row["nonce"] = None

    async def execute(self, query: str, *args: Any) -> None:
        self.executed.append(query)
        if query.startswith("CREATE DATABASE"):
            self.child.row["database"] = query.split('"')[1]

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "pg_stat_activity" in query:
            return 0
        if "SELECT oid FROM pg_database" in query:
            return self.child.row["oid"]
        return await super().fetchval(query, *args)


def install_migration_connect(monkeypatch: pytest.MonkeyPatch, admin: FakeMigrationAdmin) -> None:
    async def connect(*args: Any, **kwargs: Any) -> FakePostgres:
        return admin if kwargs.get("database") == "finanse_test" else admin.child

    monkeypatch.setattr(module().asyncpg, "connect", connect)


@pytest.mark.parametrize("field", ["database", "oid", "system_identifier", "role"])
async def test_migrate_rechecks_child_before_each_spawn(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    fixture = lifecycle_module("migration")
    install_permit(monkeypatch, permit_file)
    admin = FakeMigrationAdmin()
    install_migration_connect(monkeypatch, admin)
    process = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b"ok", None)))
    spawn = AsyncMock(return_value=process)
    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    generator = lifecycle_generator("migration", fixture)
    database = await anext(generator)
    await database.migrate("upgrade", "head")
    previous = admin.child.row[field]
    admin.child.row[field] = "wrong"
    try:
        with pytest.raises(module().DatabaseSafetyError):
            await database.migrate("downgrade", "base")
        assert spawn.await_count == 1
    finally:
        admin.child.row[field] = previous
        await generator.aclose()
    assert admin.closed and admin.child.closed


async def test_parent_rechecked_before_scratch_drop(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = lifecycle_module("migration")
    install_permit(monkeypatch, permit_file)
    admin = FakeMigrationAdmin()
    install_migration_connect(monkeypatch, admin)
    generator = lifecycle_generator("migration", fixture)
    await anext(generator)
    admin.row["oid"] = 99
    with pytest.raises(module().DatabaseSafetyError):
        await generator.aclose()
    assert not any(sql.startswith("DROP DATABASE") for sql in admin.executed)
    assert admin.closed and admin.child.closed


async def test_alembic_refuses_identity_failure_before_subprocess(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = lifecycle_module("alembic")
    install_permit(monkeypatch, permit_file)
    pg = FakePostgres()
    pg.row["oid"] = 99
    monkeypatch.setattr(module().asyncpg, "connect", AsyncMock(return_value=pg))
    spawn = AsyncMock(side_effect=AssertionError("Unverified target reached subprocess"))
    monkeypatch.setattr(fixture.subprocess, "run", spawn)
    with pytest.raises(module().DatabaseSafetyError):
        await fixture.run_alembic("upgrade", "head")
    spawn.assert_not_called()
    assert pg.closed


@pytest.mark.parametrize("change", ["database", "host", "query"])
async def test_migration_and_alembic_targets_are_bound(
    permit_file: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    fixture = lifecycle_module("migration")
    install_permit(monkeypatch, permit_file)
    admin = FakeMigrationAdmin()
    install_migration_connect(monkeypatch, admin)
    generator = lifecycle_generator("migration", fixture)
    database = await anext(generator)
    url = database.url
    if change == "database":
        url = url.replace(database.identity.name, "finanse_test")
    elif change == "host":
        url = url.replace("127.0.0.1", "production")
    else:
        url += "?host=production"
    import asyncio

    spawn = AsyncMock(side_effect=AssertionError("Foreign URL reached subprocess"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    try:
        with pytest.raises(module().DatabaseSafetyError):
            await replace(database, url=url).migrate("upgrade", "head")
        spawn.assert_not_awaited()
    finally:
        await generator.aclose()
