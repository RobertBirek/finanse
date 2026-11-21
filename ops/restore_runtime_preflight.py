"""Read-only compatibility check for a pinned restore runtime."""

import argparse
import configparser
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Never

from release_preflight_policy import (
    DIGEST,
    REVISION,
    SHA,
    PreflightInputError,
    ordered_lineage,
    parse_lineage,
)

MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * MAX_FILE_BYTES
MAX_MIGRATIONS = 256
VERSIONS = "backend/migrations/versions"
CONFIG = "backend/alembic.ini"
FIXED_MEMBERS = frozenset(
    {
        CONFIG,
        "backend/migrations/env.py",
        "backend/.venv/bin/alembic",
        "ops/restore-verify.sh",
    }
)
MIGRATION = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.py")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PreflightInputError(code)


def check_lineage(
    sources: dict[str, str], snapshot_revision: str, expected_head: str
) -> None:
    chain = ordered_lineage(parse_lineage(sources))
    if chain[-1] != expected_head:
        raise PreflightInputError("runtime_head_mismatch")
    if snapshot_revision not in chain:
        raise PreflightInputError("snapshot_revision_unknown")


def absolute_path(value: str) -> Path:
    path = Path(value)
    require(
        path.anchor == "/" and ".." not in path.parts and str(path) == value,
        "invalid_path",
    )
    return path


@contextmanager
def directory(base_fd: int, parts: tuple[str, ...], *, guarded: bool) -> Iterator[int]:
    fd = os.dup(base_fd)
    try:
        for part in parts:
            child = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
            if guarded:
                require(not (os.fstat(fd).st_mode & 0o022), "runtime_permissions")
        yield fd
    finally:
        os.close(fd)


def fingerprint(s: os.stat_result) -> tuple[int, ...]:
    return s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns


class ReadBudget:
    def __init__(self) -> None:
        self.remaining = MAX_TOTAL_BYTES

    def pinned_bytes(
        self, parent_fd: int, name: str, pin: str, *, guarded: bool
    ) -> bytes:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode), "input_type_invalid")
        if guarded:
            require(not (before.st_mode & 0o022), "runtime_permissions")
        limit = min(MAX_FILE_BYTES, self.remaining)
        require(before.st_size <= limit, "input_limit_exceeded")
        with os.fdopen(
            os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
            ),
            "rb",
        ) as f:
            original = fingerprint(before)
            require(fingerprint(os.fstat(f.fileno())) == original, "input_changed")
            data = f.read(limit + 1)
            require(len(data) <= limit, "input_limit_exceeded")
            require(
                fingerprint(os.fstat(f.fileno())) == original
                and fingerprint(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
                == original,
                "input_changed",
            )
        self.remaining -= len(data)
        require(hashlib.sha256(data).hexdigest() == pin, "input_digest_mismatch")
        return data


def unique_object(items: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(items)
    require(len(result) == len(items), "duplicate_json_key")
    return result


def reject_constant(_value: str) -> object:
    raise PreflightInputError("invalid_json")


def read_manifest(
    root_fd: int, value: str, pin: str, budget: ReadBudget
) -> dict[str, object]:
    path = absolute_path(value)
    require(bool(path.name), "invalid_path")
    with directory(root_fd, path.parts[1:-1], guarded=False) as fd:
        raw = budget.pinned_bytes(fd, path.name, pin, guarded=False)
    decoded = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
    if not isinstance(decoded, dict):
        raise PreflightInputError("invalid_json")
    return decoded


def runtime_pins(
    manifest: dict[str, object], runtime_root: Path, scope: dict[str, str]
) -> tuple[str, dict[str, str]]:
    require(
        set(manifest)
        == {"version", "runtime_root", "runtime_revision", "scope", "files"}
        and type(manifest["version"]) is int
        and manifest["version"] == 1
        and manifest["runtime_root"] == str(runtime_root),
        "runtime_manifest_invalid",
    )
    require(manifest["scope"] == scope, "scope_mismatch")
    revision, members = manifest["runtime_revision"], manifest["files"]
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        raise PreflightInputError("runtime_manifest_invalid")
    if not isinstance(members, list) or len(members) > MAX_MIGRATIONS + len(
        FIXED_MEMBERS
    ):
        raise PreflightInputError("runtime_manifest_invalid")
    pins: dict[str, str] = {}
    for member in members:
        if not isinstance(member, dict) or set(member) != {"path", "sha256"}:
            raise PreflightInputError("runtime_manifest_invalid")
        name, pin = member["path"], member["sha256"]
        if (
            not isinstance(name, str)
            or not isinstance(pin, str)
            or not DIGEST.fullmatch(pin)
            or name in pins
            or (
                name not in FIXED_MEMBERS
                and not (
                    name.startswith(VERSIONS + "/")
                    and MIGRATION.fullmatch(name.removeprefix(VERSIONS + "/"))
                )
            )
        ):
            raise PreflightInputError("runtime_manifest_invalid")
        pins[name] = pin
    require(FIXED_MEMBERS <= pins.keys(), "runtime_manifest_invalid")
    return revision, pins


def check_alembic_config(data: bytes) -> None:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(data.decode("utf-8"))
    allowed = {"script_location", "prepend_sys_path", "sqlalchemy.url"}
    require(
        not cfg.defaults()
        and cfg.has_section("alembic")
        and set(cfg["alembic"]) <= allowed
        and cfg["alembic"].get("script_location") == "migrations"
        and cfg["alembic"].get("prepend_sys_path", ".") == ".",
        "alembic_config_unsupported",
    )


def collect_sources(
    runtime_fd: int, pins: dict[str, str], budget: ReadBudget
) -> dict[str, str]:
    for name in sorted(FIXED_MEMBERS):
        parts = tuple(name.split("/"))
        with directory(runtime_fd, parts[:-1], guarded=True) as fd:
            raw = budget.pinned_bytes(fd, parts[-1], pins[name], guarded=True)
        if name == CONFIG:
            check_alembic_config(raw)

    with directory(runtime_fd, tuple(VERSIONS.split("/")), guarded=True) as fd:
        before = fingerprint(os.fstat(fd))
        names: set[str] = set()
        with os.scandir(fd) as entries:
            for entry in entries:
                if entry.name == "__pycache__" and entry.is_dir(follow_symlinks=False):
                    continue
                require(
                    len(names) < MAX_MIGRATIONS
                    and bool(MIGRATION.fullmatch(entry.name)),
                    "migration_layout_unsupported",
                )
                names.add(f"{VERSIONS}/{entry.name}")
        require(names == pins.keys() - FIXED_MEMBERS, "runtime_members_mismatch")
        sources = {
            name: budget.pinned_bytes(
                fd, name.rsplit("/", 1)[1], pins[name], guarded=True
            ).decode("utf-8")
            for name in sorted(names)
        }
        require(fingerprint(os.fstat(fd)) == before, "input_changed")
        return sources


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise PreflightInputError("invalid_arguments")


def evaluate(args: argparse.Namespace) -> dict[str, object]:
    require(
        bool(SHA.fullmatch(args.candidate))
        and bool(REVISION.fullmatch(args.expected_head))
        and all(
            DIGEST.fullmatch(value)
            for value in (
                args.snapshot_id,
                args.snapshot_manifest_sha256,
                args.runtime_manifest_sha256,
            )
        ),
        "invalid_arguments",
    )
    root = absolute_path(args.runtime_root)
    require(root != Path("/"), "invalid_path")
    budget = ReadBudget()
    host_fd = os.open("/", DIR_FLAGS)
    try:
        runtime = read_manifest(
            host_fd, args.runtime_manifest, args.runtime_manifest_sha256, budget
        )
        scope: dict[str, str] = {
            "phase": args.phase,
            "candidate": args.candidate,
            "snapshot_id": args.snapshot_id,
            "snapshot_manifest_sha256": args.snapshot_manifest_sha256,
            "expected_head": args.expected_head,
        }
        revision, pins = runtime_pins(runtime, root, scope)
        snapshot = read_manifest(
            host_fd, args.snapshot_manifest, args.snapshot_manifest_sha256, budget
        )
        snapshot_revision = snapshot.get("alembic_revision")
        if not isinstance(snapshot_revision, str) or not REVISION.fullmatch(
            snapshot_revision
        ):
            raise PreflightInputError("snapshot_manifest_invalid")
        with (
            directory(host_fd, root.parts[1:-1], guarded=False) as parent,
            directory(parent, (root.name,), guarded=True) as fd,
        ):
            sources = collect_sources(fd, pins, budget)
        check_lineage(sources, snapshot_revision, args.expected_head)
    finally:
        os.close(host_fd)
    return {
        **scope,
        "runtime_revision": revision,
        "runtime_manifest_sha256": args.runtime_manifest_sha256,
        "snapshot_revision": snapshot_revision,
    }


def main(argv: list[str] | None = None) -> int:
    parser = Parser(prog="restore-runtime-preflight", allow_abbrev=False)
    parser.add_argument(
        "--phase", choices=("rehearsal", "after_rollout"), required=True
    )
    for flag in (
        "candidate",
        "runtime-root",
        "runtime-manifest",
        "runtime-manifest-sha256",
        "snapshot-id",
        "snapshot-manifest",
        "snapshot-manifest-sha256",
        "expected-head",
    ):
        parser.add_argument("--" + flag, required=True)
    report: dict[str, object] = {"version": 1, "compatible": False, "authorized": False}
    try:
        report.update(evaluate(parser.parse_args(argv)), compatible=True)
    except PreflightInputError as exc:
        report["reason_code"] = exc.code
    except (OSError, ValueError, RecursionError, configparser.Error):
        report["reason_code"] = "input_unavailable_or_invalid"
    print(json.dumps(report, sort_keys=True))
    return 0 if report["compatible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
