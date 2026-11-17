#!/usr/bin/env python3
"""Read-only source/schema preflight; not authorization or a production readiness proof."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, NoReturn

from release_preflight_policy import (
    IMAGE_ID,
    REVISION,
    SERVICES,
    SHA,
    PreflightDecision,
    PreflightInputError,
    ReleaseFacts,
    blocked,
    classify,
    ordered_lineage,
    parse_lineage,
)

HEX64 = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
PG_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,62}")
MIGRATION = re.compile(r"backend/migrations/versions/[^/]+\.py")
PG_OPTIONS = "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC"
PG_COMMAND = (
    'exec psql -X --no-password -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
    "--set=ON_ERROR_STOP=1 --no-align --tuples-only "
    '--command="SELECT version_num FROM alembic_version"'
)


def require(condition: object, code: str = "input_invalid") -> None:
    if not condition:
        raise PreflightInputError(code)


def object_value(value: Any, keys: set[str] | None = None) -> dict[str, Any]:
    require(isinstance(value, dict), "json_shape_invalid")
    if keys is not None:
        require(set(value) == keys, "json_shape_invalid")
    return dict(value)


def token(value: Any, pattern: re.Pattern[str]) -> str:
    require(isinstance(value, str) and pattern.fullmatch(value), "token_invalid")
    return str(value)


def absolute_path(value: str) -> Path:
    path = Path(value)
    require(
        path.is_absolute() and str(path) == value and path.resolve() == path,
        "path_invalid",
    )
    return path


def read_file(value: str, *, private: bool = False) -> bytes:
    path = absolute_path(value)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "file_invalid")
        if private:
            parent = path.parent.stat()
            require(
                stat.S_IMODE(info.st_mode) == 0o600
                and stat.S_IMODE(parent.st_mode) == 0o700
                and info.st_uid in {0, os.geteuid()}
                and parent.st_uid in {0, os.geteuid()},
                "inventory_permissions_invalid",
            )
        return stream.read()


def json_value(data: str | bytes) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, "json_duplicate_key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise PreflightInputError("json_invalid")

    try:
        return json.loads(
            data, object_pairs_hook=unique, parse_constant=invalid_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise PreflightInputError("json_invalid") from None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _checked_file(entry: Any) -> tuple[str, bytes]:
    record = object_value(entry, {"path", "sha256"})
    name = record["path"]
    require(isinstance(name, str), "path_invalid")
    expected = token(record["sha256"], HEX64)
    content = read_file(name)
    require(_digest(content) == expected, "approved_file_changed")
    return name, content


class ToolRunner:
    """An unbound runner executes nothing; binding only enables exact read grammars."""

    def __init__(self) -> None:
        self.repository: Path | None = None
        self.git_prefix: list[str] = []
        self.compose_prefix: list[str] = []
        self.inspect_ids: set[str] = set()
        self.pg_argv: list[str] = []
        self.service_names: set[str] = set()

    def bind(
        self, repository: Path, compose: list[str], inventory: dict[str, Any]
    ) -> None:
        self.repository = repository
        self.git_prefix = [
            "git",
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "-C",
            str(repository),
        ]
        self.compose_prefix = compose
        self.inspect_ids = {
            *(record["container_id"] for record in inventory["services"].values()),
            *(record["image_id"] for record in inventory["services"].values()),
            inventory["postgres"]["container_id"],
        }
        self.pg_argv = [
            "docker",
            "exec",
            "--env",
            PG_OPTIONS,
            inventory["postgres"]["container_id"],
            "sh",
            "-c",
            PG_COMMAND,
        ]
        self.service_names = set(SERVICES) | {inventory["postgres"]["service"]}

    def _allowed(self, argv: list[str]) -> bool:
        if self.repository is None:
            return False
        if argv == self.pg_argv:
            return True
        if len(argv) == 3 and argv[:2] == ["docker", "inspect"]:
            return argv[2] in self.inspect_ids
        if argv[: len(self.compose_prefix)] == self.compose_prefix:
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
            return bool(re.fullmatch(r"[0-9a-f]{40}\^\{commit\}", tail[2]))
        if len(tail) == 4 and tail[:2] == ["merge-base", "--is-ancestor"]:
            return all(SHA.fullmatch(value) for value in tail[2:])
        if len(tail) == 5 and tail[:3] == ["ls-tree", "-r", "-z"]:
            return bool(SHA.fullmatch(tail[3])) and tail[4] == "--"
        if len(tail) == 3 and tail[:2] == ["cat-file", "blob"]:
            return bool(SHA.fullmatch(tail[2]))
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
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C.UTF-8",
        }
        try:
            result = subprocess.run(
                argv,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                stdin=subprocess.DEVNULL,
                env=env,
                cwd=self.repository,
            )
        except subprocess.TimeoutExpired:
            raise PreflightInputError("tool_timeout") from None
        except (OSError, UnicodeError):
            raise PreflightInputError("tool_unavailable") from None
        require(result.returncode == 0, "tool_failed")
        return result.stdout


def _inventory(args: argparse.Namespace) -> dict[str, Any]:
    content = read_file(args.approved_inventory, private=True)
    require(
        _digest(content) == token(args.inventory_sha256, HEX64),
        "inventory_digest_mismatch",
    )
    inventory = object_value(
        json_value(content),
        {
            "version",
            "project",
            "active_release_sha256",
            "compose_files",
            "env_file",
            "services",
            "postgres",
        },
    )
    require(
        type(inventory["version"]) is int and inventory["version"] == 1,
        "inventory_version",
    )
    project = token(inventory["project"], NAME)
    require(project == args.project, "inventory_target_mismatch")
    records = inventory["compose_files"]
    require(
        isinstance(records, list) and len(records) >= 2, "inventory_compose_invalid"
    )
    files = [_checked_file(record)[0] for record in records]
    require(
        files == args.compose_file and len(set(files)) == len(files),
        "inventory_target_mismatch",
    )
    env_file, _ = _checked_file(inventory["env_file"])
    require(env_file == args.env_file, "inventory_target_mismatch")
    active_content = read_file(args.active_release)
    require(
        _digest(active_content) == token(inventory["active_release_sha256"], HEX64),
        "active_metadata_changed",
    )
    active = object_value(json_value(active_content))
    require(active.get("release_status") == "verified-live", "active_metadata_invalid")
    require(active.get("compose_override") == files[-1], "active_override_mismatch")
    revisions = object_value(active.get("service_revisions"), set(SERVICES))
    images = object_value(active.get("application_images"), set(SERVICES))
    services = object_value(inventory["services"], set(SERVICES))
    ids = []
    for service, value in services.items():
        record = object_value(value, {"container_id", "image_id", "revision"})
        ids.append(token(record["container_id"], HEX64))
        token(record["revision"], SHA)
        token(record["image_id"], IMAGE_ID)
        require(
            revisions[service] == record["revision"]
            and object_value(images[service]).get("id") == record["image_id"],
            "active_metadata_mismatch",
        )
    pg = object_value(
        inventory["postgres"], {"service", "container_id", "database", "role"}
    )
    token(pg["service"], NAME)
    token(pg["container_id"], HEX64)
    token(pg["database"], PG_NAME)
    token(pg["role"], PG_NAME)
    require(
        pg["service"] == args.postgres_service and pg["service"] not in SERVICES,
        "inventory_target_mismatch",
    )
    require(len(set(ids + [pg["container_id"]])) == 4, "inventory_container_duplicate")
    return inventory


def _tree(runner: ToolRunner, revision: str) -> dict[str, tuple[str, str]]:
    output = runner.run(runner.git_prefix + ["ls-tree", "-r", "-z", revision, "--"])
    require(not output or output.endswith("\0"), "git_tree_invalid")
    entries = {}
    for line in output.split("\0")[:-1]:
        header, separator, path = line.partition("\t")
        require(separator and path and path not in entries, "git_tree_invalid")
        fields = header.split(" ")
        require(len(fields) == 3, "git_tree_invalid")
        mode, kind, object_id = fields
        require(
            mode in {"100644", "100755", "120000", "160000"}
            and kind == ("commit" if mode == "160000" else "blob")
            and SHA.fullmatch(object_id),
            "git_tree_invalid",
        )
        entries[path] = (mode, object_id)
    return entries


def _source_facts(
    args: argparse.Namespace, runner: ToolRunner, inventory: dict[str, Any]
) -> tuple[dict[str, tuple[str, ...]], dict[str, str | None], bool]:
    candidate = token(args.candidate, SHA)
    require(
        runner.run(runner.git_prefix + ["rev-parse", "--show-toplevel"]).strip()
        == str(runner.repository),
        "repository_root_mismatch",
    )
    revisions = {value["revision"] for value in inventory["services"].values()} | {
        candidate
    }
    for revision in sorted(revisions):
        actual = runner.run(
            runner.git_prefix + ["rev-parse", "--verify", revision + "^{commit}"]
        )
        require(actual.strip() == revision, "git_commit_invalid")
    trees = {revision: _tree(runner, revision) for revision in sorted(revisions)}
    target = trees[candidate]
    changed_paths = {}
    historical_changed = False
    for service in sorted(SERVICES):
        revision = inventory["services"][service]["revision"]
        runner.run(
            runner.git_prefix + ["merge-base", "--is-ancestor", revision, candidate]
        )
        output = runner.run(
            runner.git_prefix
            + [
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--name-only",
                "-z",
                revision,
                candidate,
                "--",
            ]
        )
        require(not output or output.endswith("\0"), "git_diff_invalid")
        paths = tuple(output.split("\0")[:-1])
        old = trees[revision]
        for path in paths:
            require(
                all(
                    entry is None or entry[0] in {"100644", "100755"}
                    for entry in (old.get(path), target.get(path))
                ),
                "git_entry_type_changed",
            )
            if service != "frontend" and MIGRATION.fullmatch(path) and path in old:
                historical_changed = True
        changed_paths[service] = paths
    sources = {}
    for path, (mode, object_id) in target.items():
        if path.startswith("backend/migrations/versions/") and path.endswith(".py"):
            require(MIGRATION.fullmatch(path), "migration_layout_unsupported")
        if MIGRATION.fullmatch(path):
            require(mode in {"100644", "100755"}, "git_migration_type_invalid")
            sources[path] = runner.run(
                runner.git_prefix + ["cat-file", "blob", object_id]
            )
    return changed_paths, parse_lineage(sources), historical_changed


def _inspect(runner: ToolRunner, identifier: str) -> dict[str, Any]:
    records = json_value(runner.run(["docker", "inspect", identifier]))
    require(isinstance(records, list) and len(records) == 1, "inspect_ambiguous")
    record = object_value(records[0])
    require(record.get("Id") == identifier, "inspect_id_mismatch")
    return record


def _container(
    runner: ToolRunner, service: str, identifier: str, project: str
) -> dict[str, Any]:
    actual = runner.run(runner.compose_prefix + ["ps", "--all", "--quiet", service])
    require(actual.strip() == identifier, "compose_container_mismatch")
    record = _inspect(runner, identifier)
    state = object_value(record.get("State"))
    require(
        state.get("Running") is True
        and state.get("Restarting") is False
        and state.get("Status") == "running",
        "container_not_running",
    )
    config = object_value(record.get("Config"))
    labels = object_value(config.get("Labels"))
    require(
        labels.get("com.docker.compose.project") == project
        and labels.get("com.docker.compose.service") == service,
        "container_project_mismatch",
    )
    return record


def _observe(
    runner: ToolRunner, inventory: dict[str, Any]
) -> tuple[tuple[str, ...], frozenset[str]]:
    rendered = object_value(
        json_value(runner.run(runner.compose_prefix + ["config", "--format", "json"]))
    )
    require(rendered.get("name") == inventory["project"], "compose_project_mismatch")
    services = object_value(rendered.get("services"))
    pg = inventory["postgres"]
    require(
        set(SERVICES) | {pg["service"]} <= set(services), "compose_services_missing"
    )
    for service in sorted(SERVICES):
        expected = inventory["services"][service]
        container = _container(
            runner, service, expected["container_id"], inventory["project"]
        )
        require(
            container.get("Image") == expected["image_id"], "container_image_mismatch"
        )
        config = object_value(container.get("Config"))
        rendered_service = object_value(services[service])
        require(
            isinstance(rendered_service.get("image"), str)
            and config.get("Image") == rendered_service["image"],
            "compose_image_mismatch",
        )
        image = _inspect(runner, expected["image_id"])
        for value in (config, object_value(image.get("Config"))):
            labels = object_value(value.get("Labels"))
            require(
                labels.get("org.opencontainers.image.revision") == expected["revision"],
                "image_revision_mismatch",
            )
    pg_container = _container(
        runner, pg["service"], pg["container_id"], inventory["project"]
    )
    pg_config = object_value(pg_container.get("Config"))
    raw_env = pg_config.get("Env")
    if not isinstance(raw_env, list):
        raise PreflightInputError("postgres_environment_invalid")
    env = {}
    for entry in raw_env:
        require(isinstance(entry, str), "postgres_environment_invalid")
        name, separator, value = entry.partition("=")
        require(separator and name and name not in env, "postgres_environment_invalid")
        env[name] = value
    require(
        env.get("POSTGRES_USER") == pg["role"]
        and env.get("POSTGRES_DB") == pg["database"],
        "postgres_target_mismatch",
    )
    heads_output = runner.run(runner.pg_argv)
    heads = tuple(heads_output.splitlines())
    require(
        heads and all(REVISION.fullmatch(head) for head in heads), "schema_head_invalid"
    )
    help_output = runner.run(runner.compose_prefix + ["up", "--help"])
    flags = frozenset(re.findall(r"(?<![\w-])--[a-z][a-z-]*(?![\w-])", help_output))
    return heads, flags


def collect_facts(args: argparse.Namespace, runner: ToolRunner) -> ReleaseFacts:
    token(args.candidate, SHA)
    repository = absolute_path(args.repository)
    require(repository.is_dir(), "repository_invalid")
    inventory = _inventory(args)
    compose = [
        "docker",
        "compose",
        "--project-name",
        inventory["project"],
        "--env-file",
        args.env_file,
    ]
    for file in args.compose_file:
        compose += ["-f", file]
    runner.bind(repository, compose, inventory)
    paths, lineage, historical_changed = _source_facts(args, runner, inventory)
    # Reject unsupported source changes before contacting Docker.
    provisional = ReleaseFacts(
        args.candidate,
        {name: record["revision"] for name, record in inventory["services"].items()},
        {name: record["image_id"] for name, record in inventory["services"].items()},
        paths,
        (ordered_lineage(lineage)[-1],),
        lineage,
        frozenset({"--no-start", "--no-deps", "--no-build"}),
        True,
        historical_changed,
    )
    decision = classify(provisional)
    require(
        decision.action != "blocked",
        decision.reason_codes[0] if decision.reason_codes else "facts_invalid",
    )
    heads, flags = _observe(runner, inventory)
    return ReleaseFacts(
        args.candidate,
        provisional.service_revisions,
        provisional.image_ids,
        paths,
        heads,
        lineage,
        flags,
        True,
        historical_changed,
    )


def build_report(
    facts: ReleaseFacts | None, decision: PreflightDecision
) -> dict[str, object]:
    if decision.action == "blocked":
        facts = None
    return {
        "report_version": 1,
        "authorized": False,
        "production_ready": False,
        "source_binding": "operator_approved_inventory",
        "content_provenance_verified": False,
        "external_configuration_reviewed": False,
        "candidate": facts.candidate if facts else None,
        "service_revisions": facts.service_revisions if facts else None,
        "image_ids": facts.image_ids if facts else None,
        "schema_from": facts.schema_heads[0] if facts else None,
        "schema_to": ordered_lineage(facts.lineage)[-1] if facts else None,
        "action": decision.action,
        "pending_migrations": list(decision.pending_migrations),
        "reason_codes": list(decision.reason_codes),
        "required_gates": list(decision.required_gates),
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PreflightInputError("arguments_invalid")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(
        description=__doc__,
        allow_abbrev=False,
        epilog="Source/schema classification only; not authorization. Review external configuration separately.",
    )
    parser.add_argument("--check", action="store_true", required=True)
    for name in (
        "repository",
        "candidate",
        "active-release",
        "project",
        "env-file",
        "postgres-service",
        "approved-inventory",
        "inventory-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    facts = None
    try:
        args = parser.parse_args(argv)
        facts = collect_facts(args, ToolRunner())
        decision = classify(facts)
    except PreflightInputError as exc:
        decision = blocked(exc.code)
    except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        decision = blocked("input_invalid")
    print(json.dumps(build_report(facts, decision), sort_keys=True))
    return 2 if decision.action == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
