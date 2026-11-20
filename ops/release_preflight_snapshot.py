"""Private consumed-input snapshots, not production changes or inventory issuance."""

from __future__ import annotations

import importlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass, replace
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
    verify_pinned_file,
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


@dataclass(frozen=True)
class _ComposeInspection:
    env: tuple[EnvReference, ...]
    services: frozenset[str]
    extends: dict[str, tuple[Path, str]]


def validate_compose_nodes(
    raw: bytes,
    *,
    source: Path,
    project_directory: Path,
    approved_env: Path,
    limits: InputLimits,
) -> tuple[EnvReference, ...]:
    return _inspect_compose(
        raw,
        source=source,
        project_directory=project_directory,
        approved_env=approved_env,
        limits=limits,
        allow_extends=False,
    ).env


def _inspect_compose(
    raw: bytes,
    *,
    source: Path,
    project_directory: Path,
    approved_env: Path,
    limits: InputLimits,
    allow_extends: bool,
) -> _ComposeInspection:
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
        aliases: set[tuple[int, int]] = set()

        # Load PyYAML only after the launcher has verified the bundled runtime.
        class TrackingLoader(yaml.SafeLoader):  # type: ignore[name-defined]
            def compose_node(self, parent: Any, index: Any) -> Any:
                if self.check_event(yaml.AliasEvent):
                    aliases.add((id(parent), id(index)))
                return super().compose_node(parent, index)

        root = yaml.compose(text, Loader=TrackingLoader)
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
        services_node = top["services"]
        services = fields(services_node)
        edges: dict[str, tuple[Path, str]] = {}

        def direct(node: Any, name: str) -> bool:
            return any(
                key.value == name and (id(node), id(key)) not in aliases
                for key, _ in node.value
            )

        for name, service in services.items():
            values = fields(service)
            known(values, SERVICE | {"extends"} if allow_extends else SERVICE)
            if "extends" in values:
                spec = values["extends"]
                ext = fields(spec)
                require(
                    allow_extends
                    and direct(root, "services")
                    and direct(services_node, name)
                    and direct(service, "extends")
                    and set(ext) == {"file", "service"}
                    and all(
                        direct(spec, field)
                        and isinstance(value, yaml.ScalarNode)
                        and value.tag == "tag:yaml.org,2002:str"
                        and "$" not in value.value
                        for field, value in ext.items()
                    )
                    and len(spec.value) == 2
                    and bool(ext["service"].value),
                    "unsupported_compose_input",
                )
                edges[name] = (_graph_path(ext["file"].value), ext["service"].value)
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
        return _ComposeInspection(
            tuple(sorted(refs, key=lambda ref: ref.start)), frozenset(services), edges
        )
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


def _graph_path(value: object) -> Path:
    path = absolute(value, host=False)
    require(
        all(part not in {"", ".", ".."} for part in str(value)[1:].split("/"))
        and "$" not in str(value),
        "trust_path_invalid",
    )
    return path


def compose_graph_pins(
    roots: object, dependencies: object
) -> tuple[dict[Path, str], dict[Path, str]]:
    if not isinstance(roots, list) or len(roots) < 2:
        raise PreflightInputError("snapshot_compose_invalid")
    if not isinstance(dependencies, list) or len(dependencies) > 32:
        raise PreflightInputError("compose_dependency_limit")
    seen: set[Path] = set()

    def pins(records: list[Any]) -> dict[Path, str]:
        result: dict[Path, str] = {}
        for entry in records:
            record = mapping(entry, {"path", "sha256"})
            path = _graph_path(record["path"])
            require(path not in seen, "snapshot_compose_invalid")
            seen.add(path)
            result[path] = token(record["sha256"])
        return result

    return pins(roots), pins(dependencies)


def capture_compose_graph(
    roots: object, dependencies: object, *, approved_env: Path, limits: InputLimits
) -> tuple[tuple[_Captured, bytes], ...]:
    """Return pinned root inputs in order, then reachable dependency inputs."""
    ordered, extra = compose_graph_pins(roots, dependencies)
    pins = ordered | extra
    require(approved_env not in pins, "snapshot_compose_invalid")
    project = next(iter(ordered)).parent
    captured: dict[Path, tuple[_Captured, bytes]] = {}
    inspections: dict[Path, _ComposeInspection] = {}
    pending = list(ordered)
    size = references = 0
    for path in pending:
        if path in captured:
            continue
        item, raw = _capture(path, pins[path], limits)
        size += len(raw)
        require(size <= 8 * 1024 * 1024, "compose_dependency_limit")
        parsed = _inspect_compose(
            raw,
            source=path,
            project_directory=project,
            approved_env=approved_env,
            limits=limits,
            allow_extends=True,
        )
        inspections[path] = parsed
        captured[path] = (item, raw)
        references += len(parsed.extends)
        require(references <= 256, "compose_dependency_limit")
        for target, _ in parsed.extends.values():
            require(target in pins, "compose_dependency_unapproved")
            pending.append(target)
    require(extra.keys() <= captured.keys(), "compose_dependency_unused")

    active: set[tuple[Path, str]] = set()
    depths: dict[tuple[Path, str], int] = {}

    def depth(vertex: tuple[Path, str]) -> int:
        if vertex in depths:
            return depths[vertex]
        require(vertex not in active, "compose_dependency_cycle")
        active.add(vertex)
        path, service = vertex
        parsed = inspections[path]
        require(service in parsed.services, "compose_dependency_service_missing")
        edge = parsed.extends.get(service)
        length = 0 if edge is None else 1 + depth(edge)
        require(length <= 32, "compose_dependency_limit")
        active.remove(vertex)
        depths[vertex] = length
        return length

    for path, parsed in inspections.items():
        for service in parsed.extends:
            depth((path, service))
    return tuple(captured.values())


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


@dataclass
class IsolatedSnapshot:
    root: Path
    compose_files: tuple[Path, ...]
    env_file: Path
    project_directory: Path
    _originals: list[_Captured]
    _copies: list[_Captured]
    _directories: dict[Path, tuple[int, int]]
    _files: dict[Path, tuple[int, int]]
    _limits: InputLimits

    def __enter__(self) -> Self:
        return self

    def verify_originals(self) -> None:
        try:
            for path, expected in self._directories.items():
                info = path.lstat()
                require(
                    stat.S_ISDIR(info.st_mode)
                    and (info.st_dev, info.st_ino) == expected
                    and info.st_uid == 0
                    and not info.st_mode & 0o022,
                    "snapshot_input_changed",
                )
                require(
                    all(
                        child in self._directories or child in self._files
                        for child in path.iterdir()
                    ),
                    "snapshot_input_changed",
                )
            for item in (*self._originals, *self._copies):
                limits = replace(
                    self._limits,
                    max_file_bytes=max(self._limits.max_file_bytes, item.state[2]),
                )
                current, _ = _capture(item.path, item.sha256, limits)
                require(current.state == item.state, "snapshot_input_changed")
        except OSError:
            raise PreflightInputError("snapshot_input_changed") from None

    def _cleanup(self) -> None:
        # Validate the owned directory chain before unlinking any descendants.
        try:
            for path, expected in self._directories.items():
                info = path.lstat()
                require(
                    stat.S_ISDIR(info.st_mode)
                    and (info.st_dev, info.st_ino) == expected,
                    "snapshot_cleanup_failed",
                )
            for path, expected in self._files.items():
                info = path.lstat()
                require(
                    stat.S_ISREG(info.st_mode)
                    and (info.st_dev, info.st_ino) == expected,
                    "snapshot_cleanup_failed",
                )
                path.unlink()
            for path in reversed(self._directories):
                path.rmdir()
        except OSError:
            raise PreflightInputError("snapshot_cleanup_failed") from None

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
            self._cleanup()


def capture_isolated_inputs(
    inventory: dict[str, object],
    *,
    inventory_pin: FilePin,
    active_pin: FilePin,
    compose_pin: FilePin,
    scratch: Path,
    limits: InputLimits,
) -> IsolatedSnapshot:
    snapshot = None
    try:
        require(
            type(inventory.get("version")) is int and inventory["version"] == 2,
            "inventory_version",
        )
        scratch = absolute(scratch)
        info = scratch.stat()
        require(
            os.geteuid() == 0
            and stat.S_ISDIR(info.st_mode)
            and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o700
            and not any(scratch.iterdir()),
            "snapshot_scratch_invalid",
        )
        for pin in (inventory_pin, active_pin):
            info = absolute(pin.path).lstat()
            require(
                stat.S_IMODE(info.st_mode) == pin.mode and info.st_uid == pin.uid,
                "snapshot_pin_mismatch",
            )
        first, raw = _capture(
            inventory_pin.path, inventory_pin.sha256, limits, private=True
        )
        require(strict_json(raw) == inventory, "snapshot_inventory_mismatch")
        require(
            inventory["active_release_sha256"] == active_pin.sha256,
            "snapshot_active_mismatch",
        )
        active, _ = _capture(active_pin.path, active_pin.sha256, limits)
        env = mapping(inventory["env_file"], {"path", "sha256"})
        env_item, env_bytes = _capture(
            _graph_path(env["path"]), token(env["sha256"]), limits
        )
        roots, _ = compose_graph_pins(
            inventory["compose_files"], inventory["compose_dependencies"]
        )
        graph = capture_compose_graph(
            inventory["compose_files"],
            inventory["compose_dependencies"],
            approved_env=env_item.path,
            limits=limits,
        )
        reserved = Path("/bin/compose")
        require(
            all(
                item.path != reserved
                and not item.path.is_relative_to(reserved)
                and not reserved.is_relative_to(item.path)
                for item, _ in (*graph, (env_item, env_bytes))
            ),
            "snapshot_compose_invalid",
        )
        binary_limit = replace(limits, max_file_bytes=128 * 1024 * 1024)
        binary, binary_bytes = _capture(
            compose_pin.path, compose_pin.sha256, binary_limit
        )
        require(
            verify_pinned_file(compose_pin) == binary_bytes, "snapshot_input_changed"
        )
        root = Path(tempfile.mkdtemp(prefix="preflight-isolated-", dir=scratch))
        info = root.lstat()
        snapshot = IsolatedSnapshot(
            root,
            tuple(roots),
            env_item.path,
            next(iter(roots)).parent,
            [first, active, env_item, binary, *(item for item, _ in graph)],
            [],
            {root: (info.st_dev, info.st_ino)},
            {},
            limits,
        )

        def write(destination: Path, data: bytes, mode: int) -> None:
            path = root
            for part in destination.parts[1:-1]:
                path /= part
                if path not in snapshot._directories:
                    path.mkdir(mode=0o755)
                    info = path.lstat()
                    snapshot._directories[path] = (info.st_dev, info.st_ino)
                    path.chmod(0o755)
            path /= destination.name
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(fd, "wb") as stream:
                info = os.fstat(stream.fileno())
                snapshot._files[path] = (info.st_dev, info.st_ino)
                stream.write(data)
                os.fchmod(stream.fileno(), mode)
            snapshot._copies.append(
                _Captured(path, _digest(data), identity(path.lstat()))
            )

        write(reserved, binary_bytes, 0o555)
        write(env_item.path, env_bytes, 0o444)
        for item, data in graph:
            write(item.path, data, 0o444)
        root.chmod(0o755)
        snapshot.verify_originals()
        return snapshot
    except BaseException as error:
        if snapshot is not None:
            snapshot._cleanup()
        if isinstance(error, PreflightInputError):
            raise
        if isinstance(
            error, (OSError, ValueError, KeyError, TypeError, RecursionError)
        ):
            raise PreflightInputError("snapshot_input_invalid") from None
        raise


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
