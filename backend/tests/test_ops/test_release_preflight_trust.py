"""Real file/JSON checks; never inspect a service or connect to a database."""

import hashlib
import importlib
import json
import os
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

OPS = Path(__file__).resolve().parents[3] / "ops"


def api() -> Any:
    if str(OPS) not in sys.path:
        sys.path.insert(0, str(OPS))
    return importlib.import_module("release_preflight_trust")


def write_private(tmp_path: Path, raw: bytes) -> tuple[Path, str]:
    tmp_path.chmod(0o700)
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    return path, hashlib.sha256(raw).hexdigest()


def toolchain_record() -> dict[str, Any]:
    executable = Path("/usr/bin/true").resolve()
    pin = {
        "path": str(executable),
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "mode": executable.stat().st_mode & 0o7777,
        "uid": 0,
    }
    return {
        "version": 1,
        "executables": {name: dict(pin) for name in ("git", "docker", "compose")},
        "postgres": {
            "container_id": "4" * 64,
            "image_id": "sha256:" + "d" * 64,
            "uid": 999,
            "gid": 999,
            "env_executable": "/usr/bin/env",
            "psql_executable": "/usr/lib/postgresql/16/bin/psql",
            "socket_directory": "/var/run/postgresql",
            "port": 5432,
            "auth": "peer",
        },
        "limits": {
            "max_file_bytes": 65536,
            "max_yaml_nodes": 2048,
            "max_yaml_depth": 32,
            "max_output_bytes": 131072,
        },
    }


@pytest.mark.parametrize("kind", ["duplicate", "extra", "digest", "nan", "not_object"])
def test_private_json_rejects_duplicates_extra_fields_and_bad_digest(tmp_path, kind):
    module = api()
    raw = b'{"private":"canary-secret","private":"other"}'
    if kind == "nan":
        raw = b'{"private":NaN}'
    elif kind == "not_object":
        raw = b'["canary-secret"]'
    elif kind == "extra":
        raw = json.dumps({**toolchain_record(), "apply": True}).encode()
    elif kind == "digest":
        raw = b'{"private":"canary-secret"}'
    path, digest = write_private(tmp_path, raw)
    with pytest.raises(module.PreflightInputError) as error:
        if kind == "extra":
            module.load_toolchain(path, digest)
        else:
            module.read_private_json(path, "0" * 64 if kind == "digest" else digest)
    assert "canary-secret" not in str(error.value)


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o400])
def test_private_input_requires_exact_permissions(tmp_path, mode):
    module = api()
    path, digest = write_private(tmp_path, b'{"safe":1}')
    path.chmod(mode)
    with pytest.raises(module.PreflightInputError):
        module.read_private_json(path, digest)


def test_valid_private_json_is_read_without_modification(tmp_path):
    module = api()
    raw = b'{"safe":1}'
    path, digest = write_private(tmp_path, raw)
    before = path.stat()
    assert module.read_private_json(path, digest) == {"safe": 1}
    assert path.read_bytes() == raw
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("kind", ["write", "symlink", "parent", "digest", "owner", "mode"])
def test_binary_pin_rejects_group_write_symlink_and_untrusted_parent(tmp_path, kind):
    module = api()
    tmp_path.chmod(0o700)
    path = tmp_path / "tool"
    path.write_bytes(b"#!/bin/sh\nexit 0\n")
    path.chmod(0o700)
    mode = 0o700
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    uid = os.geteuid()
    if kind == "write":
        path.chmod(0o770)
        mode = 0o770
    elif kind == "parent":
        tmp_path.chmod(0o770)
    elif kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(path)
        path = link
    elif kind == "digest":
        digest = "0" * 64
    elif kind == "owner":
        uid += 1
    elif kind == "mode":
        mode = 0o500
    pin = module.FilePin(path, digest, mode, uid)
    with pytest.raises(module.PreflightInputError):
        module.verify_pinned_file(pin, owner_uid=os.geteuid())


def test_verified_file_returns_pinned_bytes_and_detects_later_change(tmp_path):
    module = api()
    tmp_path.chmod(0o700)
    path = tmp_path / "tool"
    path.write_bytes(b"#!/bin/sh\nexit 0\n")
    path.chmod(0o700)
    pin = module.FilePin(path, hashlib.sha256(path.read_bytes()).hexdigest(), 0o700, os.geteuid())
    assert module.verify_pinned_file(pin, owner_uid=os.geteuid()) == b"#!/bin/sh\nexit 0\n"
    path.write_bytes(b"#!/bin/sh\nexit 9\n")
    with pytest.raises(module.PreflightInputError):
        module.verify_pinned_file(pin, owner_uid=os.geteuid())


@pytest.mark.parametrize(
    "kind",
    [
        "missing_pg",
        "missing_limit",
        "bool_limit",
        "root_pg",
        "tcp",
        "port",
        "extra_pg",
        "binary_owner",
        "version_bool",
    ],
)
def test_toolchain_requires_explicit_pg_identity_and_input_limits(tmp_path, kind):
    module = api()
    record = toolchain_record()
    if kind == "missing_pg":
        del record["postgres"]["uid"]
    elif kind == "missing_limit":
        del record["limits"]["max_yaml_depth"]
    elif kind == "bool_limit":
        record["limits"]["max_yaml_nodes"] = True
    elif kind == "root_pg":
        record["postgres"]["uid"] = 0
    elif kind == "tcp":
        record["postgres"]["socket_directory"] = "tcp://foreign.invalid"
    elif kind == "port":
        record["postgres"]["port"] = 0
    elif kind == "extra_pg":
        record["postgres"]["password"] = "canary-secret"
    elif kind == "binary_owner":
        record["executables"]["git"]["uid"] = 12345
    elif kind == "version_bool":
        record["version"] = True
    path, digest = write_private(tmp_path, json.dumps(record).encode())
    with pytest.raises(module.PreflightInputError):
        module.load_toolchain(path, digest)


def test_valid_toolchain_is_immutable_and_has_no_implicit_endpoint(tmp_path):
    module = api()
    path, digest = write_private(tmp_path, json.dumps(toolchain_record()).encode())
    tools = module.load_toolchain(path, digest)
    assert tools.postgres.uid == 999
    assert tools.postgres.socket_directory == "/var/run/postgresql"
    assert tools.limits.max_output_bytes == 131072
    with pytest.raises(FrozenInstanceError):
        tools.postgres.port = 6543
