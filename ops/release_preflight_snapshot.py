"""Private consumed-input snapshots, not production changes or inventory issuance."""

from __future__ import annotations

import importlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from release_preflight_policy import PreflightInputError
from release_preflight_trust import (
    FilePin,
    InputLimits,
    absolute,
    identity,
    mapping,
    read_regular,
    require,
    strict_json,
    token,
)

TOP = frozenset(
    {"version", "name", "services", "networks", "volumes", "configs", "secrets"}
)
SERVICE = frozenset(
    {
        "image",
        "build",
        "container_name",
        "restart",
        "env_file",
        "environment",
        "labels",
        "ports",
        "expose",
        "volumes",
        "networks",
        "network_mode",
        "depends_on",
        "healthcheck",
        "command",
        "entrypoint",
        "working_dir",
        "user",
        "read_only",
        "tmpfs",
        "security_opt",
        "cap_drop",
        "cap_add",
        "logging",
        "deploy",
        "stop_grace_period",
        "stop_signal",
        "init",
        "profiles",
        "hostname",
        "domainname",
        "extra_hosts",
        "devices",
        "ulimits",
        "shm_size",
        "privileged",
        "configs",
        "secrets",
        "cpus",
        "mem_limit",
        "mem_reservation",
        "pids_limit",
        "oom_score_adj",
        "stdin_open",
        "tty",
        "runtime",
        "isolation",
        "pid",
        "ipc",
        "uts",
        "platform",
        "pull_policy",
        "scale",
    }
)
BUILD = frozenset(
    {
        "context",
        "dockerfile",
        "dockerfile_inline",
        "args",
        "target",
        "cache_from",
        "cache_to",
        "additional_contexts",
        "labels",
        "network",
        "extra_hosts",
        "platforms",
        "secrets",
        "privileged",
        "pull",
        "no_cache",
        "shm_size",
        "ulimits",
        "provenance",
        "sbom",
    }
)
SAFE_TAGS = frozenset(
    "tag:yaml.org,2002:" + value
    for value in (
        "str",
        "null",
        "bool",
        "int",
        "float",
        "timestamp",
        "binary",
        "set",
        "omap",
        "pairs",
        "merge",
        "map",
        "seq",
    )
) | {"!override", "!reset"}


@dataclass(frozen=True)
class EnvReference:
    start: int
    end: int


def validate_compose_nodes(
    raw: bytes,
    *,
    source: Path,
    project_directory: Path,
    approved_env: Path,
    limits: InputLimits,
) -> tuple[EnvReference, ...]:
    """Parse nodes/tokens only: never instantiate YAML constructors."""
    absolute(source)
    project_directory, approved_env = (
        absolute(project_directory),
        absolute(approved_env),
    )
    require(len(raw) <= limits.max_file_bytes, "input_size_limit")
    try:
        yaml = importlib.import_module("yaml")
    except ImportError:
        raise PreflightInputError("yaml_runtime_unavailable") from None
    try:
        text = raw.decode("utf-8")
        scalars: list[Any] = []
        depth, count = 0, 0
        for item in yaml.scan(text, Loader=yaml.SafeLoader):
            name = type(item).__name__
            if name in {
                "BlockMappingStartToken",
                "BlockSequenceStartToken",
                "FlowMappingStartToken",
                "FlowSequenceStartToken",
            }:
                depth += 1
                count += 1
            elif name in {
                "BlockEndToken",
                "FlowMappingEndToken",
                "FlowSequenceEndToken",
            }:
                depth -= 1
            elif name in {"ScalarToken", "AliasToken"}:
                count += 1
            require(
                depth <= limits.max_yaml_depth and count <= limits.max_yaml_nodes,
                "yaml_resource_limit",
            )
            if name == "ScalarToken":
                scalars.append(item)
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        require(root is not None, "unsupported_compose_input")
        visited: set[int] = set()
        active: set[int] = set()

        def walk(node: Any) -> None:
            require(id(node) not in active, "yaml_cycle")
            if id(node) in visited:
                return
            visited.add(id(node))
            active.add(id(node))
            require(node.tag in SAFE_TAGS, "yaml_tag_unsupported")
            if isinstance(node, yaml.MappingNode):
                keys: set[str] = set()
                for key, value in node.value:
                    require(
                        isinstance(key, yaml.ScalarNode), "unsupported_compose_input"
                    )
                    require(key.value not in keys, "yaml_duplicate_key")
                    keys.add(key.value)
                    walk(key)
                    walk(value)
            elif isinstance(node, yaml.SequenceNode):
                for value in node.value:
                    walk(value)
            active.remove(id(node))

        walk(root)
        cache: dict[int, dict[str, Any]] = {}

        def fields(node: Any) -> dict[str, Any]:
            require(isinstance(node, yaml.MappingNode), "unsupported_compose_input")
            if id(node) in cache:
                return cache[id(node)]
            inherited: dict[str, Any] = {}
            explicit: dict[str, Any] = {}
            for key, value in node.value:
                if key.tag == "tag:yaml.org,2002:merge":
                    sources = (
                        value.value if isinstance(value, yaml.SequenceNode) else [value]
                    )
                    for original in sources:
                        for name, val in fields(original).items():
                            inherited.setdefault(name, val)
                else:
                    explicit[key.value] = value
            inherited.update(explicit)
            cache[id(node)] = inherited
            return inherited

        def known(values: dict[str, Any], allowed: frozenset[str]) -> None:
            require(
                all(key in allowed or key.startswith("x-") for key in values),
                "unsupported_compose_input",
            )

        refs: set[EnvReference] = set()

        def env_ref(node: Any) -> None:
            require(
                isinstance(node, yaml.ScalarNode)
                and node.tag in {"tag:yaml.org,2002:str", "!override", "!reset"}
                and "$" not in node.value,
                "unsupported_compose_input",
            )
            path = Path(node.value)
            if not path.is_absolute():
                path = project_directory / path
            require(absolute(path) == approved_env, "unsupported_compose_input")
            matches = [
                scalar
                for scalar in scalars
                if scalar.end_mark.index == node.end_mark.index
                and scalar.start_mark.index >= node.start_mark.index
                and scalar.value == node.value
            ]
            require(len(matches) == 1, "yaml_token_unbound")
            scalar = matches[0]
            refs.add(EnvReference(scalar.start_mark.index, scalar.end_mark.index))

        top = fields(root)
        known(top, TOP)
        require("services" in top, "unsupported_compose_input")
        for service in fields(top["services"]).values():
            values = fields(service)
            known(values, SERVICE)
            if "build" in values and isinstance(values["build"], yaml.MappingNode):
                known(fields(values["build"]), BUILD)
            if "env_file" in values:
                value = values["env_file"]
                if isinstance(value, yaml.SequenceNode):
                    for item in value.value:
                        env_ref(item)
                else:
                    env_ref(value)
        for section in ("configs", "secrets"):
            if section in top:
                for definition in fields(top[section]).values():
                    known(
                        fields(definition),
                        frozenset({"external", "name", "content", "environment"}),
                    )
        return tuple(sorted(refs, key=lambda ref: ref.start))
    except PreflightInputError:
        raise
    except (
        yaml.YAMLError,
        ValueError,
        UnicodeError,
        TypeError,
        AttributeError,
        RecursionError,
    ):
        raise PreflightInputError("yaml_input_invalid") from None


@dataclass(frozen=True)
class _Captured:
    path: Path
    sha256: str
    state: tuple[int, ...]


def _digest(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _capture(
    path: Path,
    digest: str,
    limits: InputLimits,
    *,
    private: bool = False,
) -> tuple[_Captured, bytes]:
    token(digest)
    path = absolute(path)
    before = identity(path.lstat())
    content = read_regular(path, private=private, max_bytes=limits.max_file_bytes)
    require(
        identity(path.lstat()) == before and _digest(content) == digest,
        "snapshot_input_changed",
    )
    return _Captured(path, digest, before), content


def _cleanup(
    root: Path, root_identity: tuple[int, int], created: dict[Path, tuple[int, int]]
) -> None:
    try:
        info = root.lstat()
        require(
            stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == root_identity,
            "snapshot_cleanup_failed",
        )
        for path, expected in created.items():
            info = path.lstat()
            require(
                stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == expected,
                "snapshot_cleanup_failed",
            )
            path.unlink()
        root.rmdir()
    except (OSError, PreflightInputError):
        raise PreflightInputError("snapshot_cleanup_failed") from None


class InputSnapshot:
    def __init__(
        self,
        *,
        root: Path,
        root_identity: tuple[int, int],
        created: dict[Path, tuple[int, int]],
        originals: tuple[_Captured, ...],
        copies: tuple[_Captured, ...],
        project_directory: Path,
        limits: InputLimits,
    ) -> None:
        self._root = root
        self._root_identity = root_identity
        self._created = created
        self._originals = originals
        self._copies = copies
        self._limits = limits
        self.env_file = copies[0].path
        self.compose_files = tuple(item.path for item in copies[1:])
        self.project_directory = project_directory

    def __enter__(self) -> Self:
        return self

    def verify_originals(self) -> None:
        try:
            for item in (*self._originals, *self._copies):
                require(
                    identity(item.path.lstat()) == item.state, "snapshot_input_changed"
                )
                _capture(item.path, item.sha256, self._limits)
        except OSError:
            raise PreflightInputError("snapshot_input_changed") from None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.verify_originals()
        finally:
            _cleanup(self._root, self._root_identity, self._created)


def capture_inputs(
    inventory: dict[str, object],
    *,
    inventory_pin: FilePin,
    active_pin: FilePin,
    scratch: Path,
    limits: InputLimits,
) -> InputSnapshot:
    root: Path | None = None
    root_identity = (0, 0)
    created: dict[Path, tuple[int, int]] = {}
    try:
        scratch = absolute(scratch)
        info = scratch.stat()
        require(
            stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid in {0, os.geteuid()}
            and "$" not in str(scratch)
            and not any(scratch.iterdir()),
            "snapshot_scratch_invalid",
        )
        for pin in (inventory_pin, active_pin):
            current = absolute(pin.path).lstat()
            require(
                type(pin.mode) is int
                and type(pin.uid) is int
                and stat.S_IMODE(current.st_mode) == pin.mode
                and current.st_uid == pin.uid,
                "snapshot_pin_mismatch",
            )
        first, raw_inventory = _capture(
            inventory_pin.path, inventory_pin.sha256, limits, private=True
        )
        require(strict_json(raw_inventory) == inventory, "snapshot_inventory_mismatch")
        require(
            inventory.get("active_release_sha256") == active_pin.sha256,
            "snapshot_active_mismatch",
        )
        second, _ = _capture(active_pin.path, active_pin.sha256, limits)
        originals = [first, second]
        env = mapping(inventory["env_file"], {"path", "sha256"})
        captured, raw_env = _capture(
            absolute(env["path"]), token(env["sha256"]), limits
        )
        originals.append(captured)
        env_path = captured.path
        records = inventory["compose_files"]
        if not isinstance(records, list) or len(records) < 2:
            raise PreflightInputError("snapshot_compose_invalid")
        composes: list[tuple[bytes, tuple[EnvReference, ...]]] = []
        paths: list[Path] = []
        for entry in records:
            record = mapping(entry, {"path", "sha256"})
            path = absolute(record["path"])
            paths.append(path)
            require(len(set(paths)) == len(paths), "snapshot_compose_invalid")
            captured, raw = _capture(path, token(record["sha256"]), limits)
            originals.append(captured)
            references = validate_compose_nodes(
                raw,
                source=path,
                project_directory=paths[0].parent,
                approved_env=env_path,
                limits=limits,
            )
            composes.append((raw, references))
        root = Path(tempfile.mkdtemp(prefix="preflight-inputs-", dir=scratch))
        info = root.lstat()
        root_identity = (info.st_dev, info.st_ino)
        copies: list[_Captured] = []

        def write(name: str, content: bytes) -> Path:
            require(len(content) <= limits.max_file_bytes, "input_size_limit")
            path = root / name
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            info = os.fstat(fd)
            created[path] = (info.st_dev, info.st_ino)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            copies.append(_Captured(path, _digest(content), identity(path.lstat())))
            return path

        frozen_env = write("env", raw_env)
        for index, (raw, refs) in enumerate(composes):
            text = raw.decode("utf-8")
            for ref in reversed(refs):
                text = text[: ref.start] + json.dumps(str(frozen_env)) + text[ref.end :]
            write(f"compose-{index}.yaml", text.encode("utf-8"))
        return InputSnapshot(
            root=root,
            root_identity=root_identity,
            created=created,
            originals=tuple(originals),
            copies=tuple(copies),
            project_directory=paths[0].parent,
            limits=limits,
        )
    except BaseException as error:
        if root is not None:
            _cleanup(root, root_identity, created)
        if isinstance(error, PreflightInputError):
            raise
        if isinstance(
            error,
            (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError),
        ):
            raise PreflightInputError("snapshot_input_invalid") from None
        raise
