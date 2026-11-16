"""Offline guard contracts: external database adapters are always replaced."""

from __future__ import annotations

import json
import os
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
