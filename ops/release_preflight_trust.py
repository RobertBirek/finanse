"""Strict local trust inputs. No subprocesses, service reads, or approval issuance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from release_preflight_policy import PreflightInputError

HEX64 = re.compile(r"[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def require(condition: object, code: str) -> None:
    if not condition:
        raise PreflightInputError(code)


def mapping(value: object, keys: set[str] | None = None) -> dict[str, Any]:
    require(isinstance(value, dict), "trust_shape_invalid")
    result = cast(dict[str, Any], value)
    require(keys is None or set(result) == keys, "trust_shape_invalid")
    return result


def integer(value: object, minimum: int = 0) -> int:
    require(type(value) is int, "trust_number_invalid")
    result = cast(int, value)
    require(result >= minimum, "trust_number_invalid")
    return result


def token(value: object, pattern: re.Pattern[str] = HEX64) -> str:
    require(isinstance(value, str), "trust_token_invalid")
    result = cast(str, value)
    require(pattern.fullmatch(result) is not None, "trust_token_invalid")
    return result


def absolute(value: object, *, host: bool = True) -> Path:
    require(isinstance(value, (str, Path)), "trust_path_invalid")
    text = str(value)
    path = Path(text)
    require(
        path.is_absolute()
        and str(PurePosixPath(text)) == text
        and ".." not in path.parts
        and not any(c in text for c in ("\0", "\n", "\r")),
        "trust_path_invalid",
    )
    if host:
        try:
            require(path.resolve() == path, "trust_path_invalid")
        except (OSError, ValueError, RuntimeError):
            raise PreflightInputError("trust_path_invalid") from None
    return path


def identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def read_regular(path: Path, *, private: bool = False) -> bytes:
    """Read stable bytes from one regular inode; never repair permissions."""
    path = absolute(path)
    try:
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode), "trust_file_invalid")
        with os.fdopen(
            os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
        ) as f:
            opened = os.fstat(f.fileno())
            require(identity(before) == identity(opened), "trust_file_changed")
            if private:
                parent = path.parent.stat()
                require(
                    stat.S_IMODE(opened.st_mode) == 0o600
                    and stat.S_IMODE(parent.st_mode) == 0o700
                    and opened.st_uid in {0, os.geteuid()}
                    and parent.st_uid in {0, os.geteuid()},
                    "trust_permissions_invalid",
                )
            content = f.read()
            require(
                len(content) == opened.st_size
                and identity(os.fstat(f.fileno())) == identity(opened)
                and identity(path.lstat()) == identity(opened),
                "trust_file_changed",
            )
            return content
    except OSError:
        raise PreflightInputError("trust_file_unavailable") from None


def strict_json(content: bytes) -> dict[str, object]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, "trust_duplicate_key")
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise PreflightInputError("trust_json_invalid")

    try:
        result = json.loads(content, object_pairs_hook=unique, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError):
        raise PreflightInputError("trust_json_invalid") from None
    return mapping(result)


def read_private_json(path: Path, expected_sha256: str) -> dict[str, object]:
    expected = token(expected_sha256)
    content = read_regular(path, private=True)
    require(hashlib.sha256(content).hexdigest() == expected, "trust_digest_mismatch")
    return strict_json(content)


@dataclass(frozen=True)
class FilePin:
    path: Path
    sha256: str
    mode: int
    uid: int


@dataclass(frozen=True)
class PgEndpoint:
    container_id: str
    image_id: str
    uid: int
    gid: int
    env_executable: str
    psql_executable: str
    socket_directory: str
    port: int
    auth: Literal["peer", "trust"]


@dataclass(frozen=True)
class InputLimits:
    max_file_bytes: int
    max_yaml_nodes: int
    max_yaml_depth: int
    max_output_bytes: int


@dataclass(frozen=True)
class Toolchain:
    git: FilePin
    docker: FilePin
    compose: FilePin
    postgres: PgEndpoint
    limits: InputLimits


def verify_pinned_file(pin: FilePin, *, owner_uid: int = 0) -> bytes:
    path = absolute(pin.path)
    mode, uid = integer(pin.mode), integer(pin.uid)
    token(pin.sha256)
    require(
        uid == owner_uid and mode <= 0o777 and not mode & 0o022,
        "tool_permissions_invalid",
    )
    try:
        for parent in path.parents:
            info = parent.stat()
            # A root-owned sticky ancestor (e.g. /tmp) cannot replace another
            # user's existing private subtree or pinned file.
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            require(
                stat.S_ISDIR(info.st_mode)
                and info.st_uid in {0, owner_uid}
                and (not info.st_mode & 0o022 or sticky_root),
                "tool_parent_untrusted",
            )
        before = path.lstat()
        require(
            before.st_uid == uid and stat.S_IMODE(before.st_mode) == mode,
            "tool_permissions_invalid",
        )
        content = read_regular(path)
        require(identity(path.lstat()) == identity(before), "trust_file_changed")
    except OSError:
        raise PreflightInputError("trust_file_unavailable") from None
    require(hashlib.sha256(content).hexdigest() == pin.sha256, "tool_digest_mismatch")
    return content


def _executable(value: object) -> FilePin:
    record = mapping(value, {"path", "sha256", "mode", "uid"})
    pin = FilePin(
        absolute(record["path"]),
        token(record["sha256"]),
        integer(record["mode"]),
        integer(record["uid"]),
    )
    require(pin.uid == 0 and pin.mode & 0o111, "tool_permissions_invalid")
    verify_pinned_file(pin)
    return pin


def load_toolchain(path: Path, expected_sha256: str) -> Toolchain:
    root = mapping(
        read_private_json(path, expected_sha256),
        {"version", "executables", "postgres", "limits"},
    )
    require(
        type(root["version"]) is int and root["version"] == 1, "trust_version_invalid"
    )
    executables = mapping(root["executables"], {"git", "docker", "compose"})
    pg = mapping(root["postgres"], set(PgEndpoint.__dataclass_fields__))
    require(pg["auth"] in ("peer", "trust"), "pg_auth_unsupported")
    port = integer(pg["port"], 1)
    require(port <= 65535, "pg_endpoint_invalid")
    endpoint = PgEndpoint(
        container_id=token(pg["container_id"]),
        image_id=token(pg["image_id"], IMAGE_ID),
        uid=integer(pg["uid"], 1),
        gid=integer(pg["gid"]),
        env_executable=str(absolute(pg["env_executable"], host=False)),
        psql_executable=str(absolute(pg["psql_executable"], host=False)),
        socket_directory=str(absolute(pg["socket_directory"], host=False)),
        port=port,
        auth=cast(Literal["peer", "trust"], pg["auth"]),
    )
    limits = mapping(root["limits"], set(InputLimits.__dataclass_fields__))
    return Toolchain(
        git=_executable(executables["git"]),
        docker=_executable(executables["docker"]),
        compose=_executable(executables["compose"]),
        postgres=endpoint,
        limits=InputLimits(**{key: integer(value, 1) for key, value in limits.items()}),
    )
