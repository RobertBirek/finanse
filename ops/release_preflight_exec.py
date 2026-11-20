"""Pinned, bounded read-only command grammar. Never discovers tools using PATH."""

from __future__ import annotations

import os
import re
import selectors
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from release_preflight_policy import (
    IMAGE_ID,
    REVISION,
    SERVICES,
    SHA,
    PreflightInputError,
)
from release_preflight_trust import (
    HEX64,
    FilePin,
    Toolchain,
    absolute,
    json_value,
    mapping,
    require,
    token,
    verify_pinned_file,
)

NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
PG_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,62}")
PG_OPTIONS = "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC"
SQL = "SELECT version_num FROM alembic_version"
SOCKET = "unix:///var/run/docker.sock"
RETAINED_MIGRATORS = "retained_backend_migrators"
_FINISHED_AT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z"
)
_MIGRATOR_FORMAT = (
    "[{{json .Id}},{{json .Image}},{{json .State.Status}},{{json .State.Running}},"
    "{{json .State.Restarting}},{{json .State.ExitCode}},{{json .State.FinishedAt}},"
    '{{json (index .Config.Labels "com.docker.compose.project")}},'
    '{{json (index .Config.Labels "com.docker.compose.service")}},'
    '{{json (index .Config.Labels "com.docker.compose.oneoff")}}]'
)


@dataclass(frozen=True)
class RetainedMigrator:
    image_id: str
    finished_at: str


def retained_migrator_pins(
    inventory: dict[str, object], active_ids: set[str]
) -> dict[str, RetainedMigrator]:
    if RETAINED_MIGRATORS not in inventory:
        return {}
    raw = inventory[RETAINED_MIGRATORS]
    reason = "retained_migrators_invalid"
    if inventory.get("version") != 2 or not isinstance(raw, list) or len(raw) > 3:
        raise PreflightInputError(reason)
    pins: dict[str, RetainedMigrator] = {}
    for record in raw:
        require(
            isinstance(record, dict)
            and set(record) == {"container_id", "image_id", "finished_at"},
            reason,
        )
        identifier, image, finished = (
            record["container_id"],
            record["image_id"],
            record["finished_at"],
        )
        require(
            isinstance(identifier, str)
            and HEX64.fullmatch(identifier)
            and identifier not in pins
            and identifier not in active_ids
            and isinstance(image, str)
            and IMAGE_ID.fullmatch(image)
            and isinstance(finished, str)
            and _FINISHED_AT.fullmatch(finished),
            reason,
        )
        try:
            # Validate the calendar/clock, preserving the exact original nanoseconds.
            parsed = datetime.fromisoformat(finished)
            require(parsed.year > 1, reason)  # Docker's zero time is not completion.
        except ValueError:
            raise PreflightInputError(reason) from None
        pins[identifier] = RetainedMigrator(image, finished)
    return pins


class ReadOnlyRunner:
    def __init__(
        self,
        repository: Path,
        toolchain: Toolchain,
        *,
        verifier: Callable[[FilePin], bytes] = verify_pinned_file,
    ) -> None:
        self.repository = absolute(repository)
        require(self.repository.is_dir(), "repository_invalid")
        self.toolchain = toolchain
        self.verifier = verifier
        self.git_prefix = [
            "git",
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "-C",
            str(self.repository),
        ]
        self.compose_prefix: list[str] = []
        self.pg_argv: list[str] = []
        self.inspect_ids: set[str] = set()
        self.service_names: set[str] = set()
        self.project = ""
        self.pg: dict[str, Any] = {}
        self.isolated = False
        self.container_ids: dict[str, str] = {}
        self.retained_migrators: dict[str, RetainedMigrator] = {}

    def bind(
        self,
        compose_files: tuple[Path, ...],
        env_file: Path,
        project_directory: Path,
        project: str,
        inventory: dict[str, object],
    ) -> None:
        self.project = token(project, NAME)
        self.isolated = inventory.get("version") == 2
        self.pg = mapping(
            inventory["postgres"], {"service", "container_id", "database", "role"}
        )
        token(self.pg["service"], NAME)
        token(self.pg["database"], PG_NAME)
        token(self.pg["role"], PG_NAME)
        endpoint = self.toolchain.postgres
        require(
            self.pg["container_id"] == endpoint.container_id, "postgres_target_mismatch"
        )
        require(
            endpoint.uid > 0 and endpoint.auth in {"peer", "trust"},
            "pg_endpoint_invalid",
        )
        services = mapping(inventory["services"], set(SERVICES))
        self.inspect_ids = {endpoint.container_id}
        self.container_ids = {self.pg["service"]: endpoint.container_id}
        for name, record in services.items():
            value = mapping(record, {"container_id", "image_id", "revision"})
            self.inspect_ids.update((value["container_id"], value["image_id"]))
            self.container_ids[name] = token(value["container_id"])
        self.retained_migrators = retained_migrator_pins(
            inventory, set(self.container_ids.values())
        )
        self.service_names = set(SERVICES) | {self.pg["service"]}
        self.compose_prefix = [
            "compose",
            "--project-name",
            self.project,
            "--project-directory",
            str(absolute(project_directory)),
            "--env-file",
            str(absolute(env_file)),
        ]
        for path in compose_files:
            self.compose_prefix += ["-f", str(absolute(path))]
        require(bool(compose_files), "compose_files_invalid")
        self.pg_argv = [
            "docker",
            "exec",
            "--user",
            f"{endpoint.uid}:{endpoint.gid}",
            endpoint.container_id,
            endpoint.env_executable,
            "-i",
            "HOME=/nonexistent",
            "PGPASSFILE=/dev/null",
            "PGCONNECT_TIMEOUT=5",
            PG_OPTIONS,
            endpoint.psql_executable,
            "-X",
            "--no-password",
            "--host",
            endpoint.socket_directory,
            "--port",
            str(endpoint.port),
            "--username",
            self.pg["role"],
            "--dbname",
            self.pg["database"],
            "--set=ON_ERROR_STOP=1",
            "--no-align",
            "--tuples-only",
            "--command",
            SQL,
        ]

    def _container_list(self, service: str) -> list[str]:
        return [
            "docker",
            "ps",
            "--all",
            "--no-trunc",
            "--filter",
            f"label=com.docker.compose.project={self.project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.ID}}",
        ]

    def container_id_for_service(self, service: str) -> str:
        require(service in self.container_ids, "command_not_allowed")
        expected = self.container_ids[service]
        if self.isolated:
            actual = self.run(self._container_list(service)).splitlines()
            retained = self.retained_migrators if service == "backend" else {}
            wanted = {expected, *retained}
            require(
                len(actual) == len(wanted) and set(actual) == wanted,
                "compose_container_mismatch",
            )
            for identifier, pin in retained.items():
                self._verify_retained_migrator(identifier, pin)
        else:
            output = self.run(self.compose_prefix + ["ps", "--all", "--quiet", service])
            require(output.strip() == expected, "compose_container_mismatch")
        return expected

    def _verify_retained_migrator(self, identifier: str, pin: RetainedMigrator) -> None:
        value = json_value(
            self.run(
                [
                    "docker",
                    "container",
                    "inspect",
                    "--format",
                    _MIGRATOR_FORMAT,
                    identifier,
                ]
            )
        )
        require(
            isinstance(value, list)
            and len(value) == 10
            and value[:3] == [identifier, pin.image_id, "exited"]
            and value[3] is False
            and value[4] is False
            and type(value[5]) is int
            and value[5] == 0
            and value[6:9] == [pin.finished_at, self.project, "backend"]
            and value[9] in ("True", "true"),
            "retained_migrator_mismatch",
        )

    def _allowed(self, argv: list[str]) -> bool:
        if not argv:
            return False
        if self.pg_argv and argv == self.pg_argv:
            return True
        if len(argv) == 3 and argv[:2] == ["docker", "inspect"]:
            return argv[2] in self.inspect_ids
        if (
            self.isolated
            and len(argv) == 6
            and argv[:5]
            == ["docker", "container", "inspect", "--format", _MIGRATOR_FORMAT]
        ):
            return argv[5] in self.retained_migrators
        if self.isolated and argv[:2] == ["docker", "ps"]:
            return any(
                argv == self._container_list(service) for service in self.container_ids
            )
        if (
            not self.isolated
            and self.compose_prefix
            and argv[: len(self.compose_prefix)] == self.compose_prefix
        ):
            tail = argv[len(self.compose_prefix) :]
            return tail in (["config", "--format", "json"], ["up", "--help"]) or (
                len(tail) == 4
                and tail[:3] == ["ps", "--all", "--quiet"]
                and tail[3] in self.service_names
            )
        if argv[: len(self.git_prefix)] != self.git_prefix:
            return False
        tail = argv[len(self.git_prefix) :]
        if tail == ["rev-parse", "--show-toplevel"]:
            return True
        if len(tail) == 3 and tail[:2] == ["rev-parse", "--verify"]:
            return re.fullmatch(r"[0-9a-f]{40}\^\{commit\}", tail[2]) is not None
        if len(tail) == 4 and tail[:2] == ["merge-base", "--is-ancestor"]:
            return all(SHA.fullmatch(value) for value in tail[2:])
        if len(tail) == 5 and tail[:3] == ["ls-tree", "-r", "-z"]:
            return SHA.fullmatch(tail[3]) is not None and tail[4] == "--"
        if len(tail) == 3 and tail[:2] == ["cat-file", "blob"]:
            return SHA.fullmatch(tail[2]) is not None
        return (
            len(tail) == 9
            and tail[:6]
            == [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-only",
                "-z",
            ]
            and all(SHA.fullmatch(value) for value in tail[6:8])
            and tail[8] == "--"
        )

    def run(self, argv: list[str]) -> str:
        require(self._allowed(argv), "command_not_allowed")
        pin = {
            "git": self.toolchain.git,
            "docker": self.toolchain.docker,
            "compose": self.toolchain.compose,
        }[argv[0]]
        self.verifier(pin)
        command = [str(pin.path), *argv[1:]]
        if argv[0] == "docker":
            command[1:1] = ["--host", SOCKET]
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LC_ALL": "C.UTF-8",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "DOCKER_HOST": SOCKET,
            "DOCKER_CONFIG": "/nonexistent",
        }
        output = self._capture(command, env)
        self.verifier(pin)
        return output

    def _capture(self, command: list[str], env: dict[str, str]) -> str:
        return capture_process(
            command,
            env,
            cwd=self.repository,
            max_output_bytes=self.toolchain.limits.max_output_bytes,
        )

    def _inspect_pg(self) -> dict[str, Any]:
        endpoint = self.toolchain.postgres
        self.container_id_for_service(self.pg["service"])
        records = json_value(self.run(["docker", "inspect", endpoint.container_id]))
        require(isinstance(records, list) and len(records) == 1, "inspect_ambiguous")
        record = mapping(records[0])
        require(
            record.get("Id") == endpoint.container_id
            and record.get("Image") == endpoint.image_id,
            "postgres_target_mismatch",
        )
        state = mapping(record.get("State"))
        require(
            state.get("Running") is True
            and state.get("Restarting") is False
            and state.get("Status") == "running",
            "container_not_running",
        )
        config = mapping(record.get("Config"))
        labels = mapping(config.get("Labels"))
        require(
            labels.get("com.docker.compose.project") == self.project
            and labels.get("com.docker.compose.service") == self.pg["service"],
            "container_project_mismatch",
        )
        entries = config.get("Env")
        if not isinstance(entries, list):
            raise PreflightInputError("postgres_environment_invalid")
        environment: dict[str, str] = {}
        for entry in entries:
            require(isinstance(entry, str), "postgres_environment_invalid")
            name, separator, value = entry.partition("=")
            require(
                separator and name and name not in environment,
                "postgres_environment_invalid",
            )
            environment[name] = value
        require(
            environment.get("POSTGRES_USER") == self.pg["role"]
            and environment.get("POSTGRES_DB") == self.pg["database"],
            "postgres_target_mismatch",
        )
        mounts = record.get("Mounts")
        if not isinstance(mounts, list):
            raise PreflightInputError("pg_socket_unbound")
        socket = absolute(endpoint.socket_directory, host=False)
        for raw in mounts:
            mount = mapping(raw)
            destination = absolute(mount.get("Destination"), host=False)
            if socket.is_relative_to(destination) or destination.is_relative_to(socket):
                require(mount.get("Type") == "tmpfs", "pg_socket_unbound")
        return record

    def schema_heads(self) -> tuple[str, ...]:
        require(bool(self.pg_argv), "runner_not_bound")
        self._inspect_pg()
        heads = tuple(self.run(self.pg_argv).splitlines())
        require(
            heads and all(REVISION.fullmatch(head) for head in heads),
            "schema_head_invalid",
        )
        return heads


def capture_process(
    command: list[str],
    env: dict[str, str],
    *,
    cwd: Path,
    max_output_bytes: int,
) -> str:
    """Bounded I/O primitive; callers must validate their own closed argv grammar."""
    require(
        type(max_output_bytes) is int and max_output_bytes > 0, "tool_limit_invalid"
    )
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise PreflightInputError("tool_failed")
        deadline = time.monotonic() + 10
        chunks: list[bytes] = []
        count = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                require(remaining > 0, "tool_timeout")
                for key, _ in selector.select(remaining):
                    block = os.read(key.fd, min(65536, max_output_bytes + 1))
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    count += len(block)
                    require(count <= max_output_bytes, "tool_output_limit")
                    if key.data == "stdout":
                        chunks.append(block)
        remaining = deadline - time.monotonic()
        require(remaining > 0, "tool_timeout")
        require(process.wait(timeout=remaining) == 0, "tool_failed")
        return b"".join(chunks).decode("utf-8")
    except subprocess.TimeoutExpired:
        raise PreflightInputError("tool_timeout") from None
    except (OSError, UnicodeError):
        raise PreflightInputError("tool_unavailable") from None
    finally:
        if process is not None:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                raise PreflightInputError("tool_cleanup_failed") from None
