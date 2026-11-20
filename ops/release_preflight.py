"""Read-only source/schema classification; use the externally approved launcher."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

sys.dont_write_bytecode = True

from release_preflight_policy import (
    IMAGE_ID,
    SERVICES,
    SHA,
    PreflightDecision,
    PreflightInputError,
    ReleaseFacts,
    VerifiedToolingScope,
    blocked,
    classify,
    ordered_lineage,
    parse_lineage,
)

if TYPE_CHECKING:
    from release_preflight_exec import ReadOnlyRunner
    from release_preflight_trust import BootstrapContext

HEX64 = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
PG_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,62}")
MIGRATION = re.compile(r"backend/migrations/versions/[^/]+\.py")


def require(condition: object, code: str = "input_invalid") -> None:
    if not condition:
        raise PreflightInputError(code)


def object_value(value: Any, keys: set[str] | None = None) -> dict[str, Any]:
    require(isinstance(value, dict), "json_shape_invalid")
    require(keys is None or set(value) == keys, "json_shape_invalid")
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


def read_file(
    value: str, *, private: bool = False, max_bytes: int | None = None
) -> bytes:
    from release_preflight_trust import read_regular

    return read_regular(absolute_path(value), private=private, max_bytes=max_bytes)


def json_value(data: bytes | str) -> Any:
    from release_preflight_trust import json_value as parse

    return parse(data)


def _digest(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _checked_file(entry: Any, max_bytes: int) -> str:
    record = object_value(entry, {"path", "sha256"})
    name = record["path"]
    require(isinstance(name, str), "path_invalid")
    expected = token(record["sha256"], HEX64)
    require(
        _digest(read_file(name, max_bytes=max_bytes)) == expected,
        "approved_file_changed",
    )
    return str(name)


def _inventory(args: argparse.Namespace, max_bytes: int) -> dict[str, Any]:
    from release_preflight_exec import RETAINED_MIGRATORS, retained_migrator_pins

    content = read_file(args.approved_inventory, private=True, max_bytes=max_bytes)
    require(
        _digest(content) == token(args.inventory_sha256, HEX64),
        "inventory_digest_mismatch",
    )
    inventory = object_value(json_value(content))
    version = inventory.get("version")
    require(type(version) is int and version in {1, 2}, "inventory_version")
    keys = {
        "version",
        "project",
        "active_release_sha256",
        "compose_files",
        "env_file",
        "services",
        "postgres",
    }
    if version == 2:
        keys.add("compose_dependencies")
        if RETAINED_MIGRATORS in inventory:
            keys.add(RETAINED_MIGRATORS)
    inventory = object_value(inventory, keys)
    if version == 2:
        from release_preflight_snapshot import compose_graph_pins

        compose_graph_pins(
            inventory["compose_files"], inventory["compose_dependencies"]
        )
        require(args.isolated_compose, "isolated_preflight_not_enabled")
    else:
        require(not args.isolated_compose, "inventory_version")
    require(
        token(inventory["project"], NAME) == args.project, "inventory_target_mismatch"
    )
    records = inventory["compose_files"]
    require(
        isinstance(records, list) and len(records) >= 2, "inventory_compose_invalid"
    )
    files = [_checked_file(record, max_bytes) for record in records]
    require(
        files == args.compose_file and len(set(files)) == len(files),
        "inventory_target_mismatch",
    )
    require(
        _checked_file(inventory["env_file"], max_bytes) == args.env_file,
        "inventory_target_mismatch",
    )
    active_content = read_file(args.active_release, max_bytes=max_bytes)
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
    for service, raw in services.items():
        record = object_value(raw, {"container_id", "image_id", "revision"})
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
    retained_migrator_pins(inventory, {*ids, pg["container_id"]})
    return inventory


def _source_facts(
    args: argparse.Namespace,
    runner: ReadOnlyRunner,
    inventory: dict[str, Any],
    bootstrap: BootstrapContext,
) -> tuple[
    dict[str, tuple[str, ...]], dict[str, str | None], bool, VerifiedToolingScope | None
]:
    from release_preflight_review import (
        _tree,
        collect_source_changes,
        verify_review_scope,
    )

    require(
        runner.run(runner.git_prefix + ["rev-parse", "--show-toplevel"]).strip()
        == str(runner.repository),
        "repository_root_mismatch",
    )
    revisions = {
        name: record["revision"] for name, record in inventory["services"].items()
    }
    changes = collect_source_changes(
        runner, candidate=args.candidate, service_revisions=revisions
    )
    paths = {
        service: tuple(change.path for change in changes if change.service == service)
        for service in SERVICES
    }
    historical = any(
        change.service != "frontend"
        and MIGRATION.fullmatch(change.path)
        and change.before_blob is not None
        for change in changes
    )
    sources = {}
    for path, (mode, blob) in _tree(runner, args.candidate).items():
        if path.startswith("backend/migrations/versions/") and path.endswith(".py"):
            require(MIGRATION.fullmatch(path), "migration_layout_unsupported")
        if MIGRATION.fullmatch(path):
            require(mode in {"100644", "100755"}, "git_migration_type_invalid")
            sources[path] = runner.run(runner.git_prefix + ["cat-file", "blob", blob])
    lineage = parse_lineage(sources)
    scope = None
    if args.review_scope is not None:
        scope = verify_review_scope(
            absolute_path(args.review_scope),
            args.review_scope_sha256,
            candidate=args.candidate,
            service_revisions=revisions,
            checker_bundle_sha256=bootstrap.bundle_sha256,
            actual_changes=changes,
            review_report=absolute_path(args.review_report),
        )
    return paths, lineage, bool(historical), scope


def _inspect(runner: ReadOnlyRunner, identifier: str) -> dict[str, Any]:
    records = json_value(runner.run(["docker", "inspect", identifier]))
    require(isinstance(records, list) and len(records) == 1, "inspect_ambiguous")
    record = object_value(records[0])
    require(record.get("Id") == identifier, "inspect_id_mismatch")
    return record


def _container(
    runner: ReadOnlyRunner,
    service: str,
    identifier: str,
    project: str,
) -> dict[str, Any]:
    require(
        runner.container_id_for_service(service) == identifier,
        "compose_container_mismatch",
    )
    record = _inspect(runner, identifier)
    state = object_value(record.get("State"))
    require(
        state.get("Running") is True
        and state.get("Restarting") is False
        and state.get("Status") == "running",
        "container_not_running",
    )
    labels = object_value(object_value(record.get("Config")).get("Labels"))
    if service == "backend" and runner.isolated:
        require(
            labels.get("com.docker.compose.oneoff") in ("False", "false"),
            "compose_container_mismatch",
        )
    require(
        labels.get("com.docker.compose.project") == project
        and labels.get("com.docker.compose.service") == service,
        "container_project_mismatch",
    )
    return record


def _observe(
    runner: ReadOnlyRunner,
    inventory: dict[str, Any],
    *,
    isolated_root: Path | None = None,
) -> tuple[tuple[str, ...], frozenset[str]]:
    help_text = None
    if isolated_root is None:
        raw = runner.run(runner.compose_prefix + ["config", "--format", "json"])
    else:
        from release_preflight_isolation import run_isolated_compose

        prefix = tuple(runner.compose_prefix[1:])
        limit = runner.toolchain.limits.max_output_bytes
        raw = run_isolated_compose(
            isolated_root,
            (*prefix, "config", "--format", "json"),
            max_output_bytes=limit,
        )
        help_text = run_isolated_compose(
            isolated_root, (*prefix, "up", "--help"), max_output_bytes=limit
        )
    rendered = object_value(json_value(raw))
    require(rendered.get("name") == inventory["project"], "compose_project_mismatch")
    services = object_value(rendered.get("services"))
    require(
        set(SERVICES) | {inventory["postgres"]["service"]} <= set(services),
        "compose_services_missing",
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
            require(
                object_value(value.get("Labels")).get(
                    "org.opencontainers.image.revision"
                )
                == expected["revision"],
                "image_revision_mismatch",
            )
    heads = runner.schema_heads()
    if help_text is None:
        help_text = runner.run(runner.compose_prefix + ["up", "--help"])
    flags = frozenset(re.findall(r"(?<![\w-])--[a-z][a-z-]*(?![\w-])", help_text))
    return heads, flags


def collect_facts(
    args: argparse.Namespace, bootstrap: BootstrapContext
) -> ReleaseFacts:
    from release_preflight_exec import ReadOnlyRunner
    from release_preflight_snapshot import capture_inputs, capture_isolated_inputs
    from release_preflight_trust import FilePin

    token(args.candidate, SHA)
    if args.isolated_compose:
        from release_preflight_isolation import ISOLATED_COMPOSE_SHA256

        require(
            bootstrap.isolated_approval == (args.candidate, args.inventory_sha256),
            "isolated_approval_mismatch",
        )
        require(
            bootstrap.toolchain.compose.sha256 == ISOLATED_COMPOSE_SHA256,
            "isolated_compose_pin_mismatch",
        )
    repository = absolute_path(args.repository)
    require(repository.is_dir(), "repository_invalid")
    inventory = _inventory(args, bootstrap.toolchain.limits.max_file_bytes)
    runner = ReadOnlyRunner(repository, bootstrap.toolchain)
    paths, lineage, historical, scope = _source_facts(
        args, runner, inventory, bootstrap
    )
    provisional = ReleaseFacts(
        args.candidate,
        {name: record["revision"] for name, record in inventory["services"].items()},
        {name: record["image_id"] for name, record in inventory["services"].items()},
        paths,
        (ordered_lineage(lineage)[-1],),
        lineage,
        frozenset({"--no-start", "--no-deps", "--no-build"}),
        True,
        historical,
        tooling_scope=scope,
        checker_bundle_sha256=bootstrap.bundle_sha256,
    )
    decision = classify(provisional)
    require(
        decision.action != "blocked",
        decision.reason_codes[0] if decision.reason_codes else "facts_invalid",
    )

    def pin(path: str, sha256: str) -> FilePin:
        import stat

        info = absolute_path(path).lstat()
        return FilePin(Path(path), sha256, stat.S_IMODE(info.st_mode), info.st_uid)

    inventory_pin = pin(args.approved_inventory, args.inventory_sha256)
    active_pin = pin(args.active_release, inventory["active_release_sha256"])
    scratch = absolute_path(args.scratch_directory)
    limits = bootstrap.toolchain.limits
    isolated = (
        capture_isolated_inputs(
            inventory,
            inventory_pin=inventory_pin,
            active_pin=active_pin,
            scratch=scratch,
            limits=limits,
            compose_pin=bootstrap.toolchain.compose,
        )
        if inventory["version"] == 2
        else None
    )
    with (
        isolated
        if isolated is not None
        else capture_inputs(
            inventory,
            inventory_pin=inventory_pin,
            active_pin=active_pin,
            scratch=scratch,
            limits=limits,
        ) as snapshot
    ):
        if isolated is not None:
            isolated.verify_originals()
        runner.bind(
            snapshot.compose_files,
            snapshot.env_file,
            snapshot.project_directory,
            inventory["project"],
            inventory,
        )
        heads, flags = _observe(
            runner,
            inventory,
            isolated_root=isolated.root if isolated is not None else None,
        )
        facts = ReleaseFacts(
            args.candidate,
            provisional.service_revisions,
            provisional.image_ids,
            paths,
            heads,
            lineage,
            flags,
            True,
            historical,
            tooling_scope=scope,
            checker_bundle_sha256=bootstrap.bundle_sha256,
        )
    return facts


def build_report(
    facts: ReleaseFacts | None,
    decision: PreflightDecision,
    bootstrap: BootstrapContext | None = None,
) -> dict[str, object]:
    if decision.action == "blocked":
        facts = None
    scope = facts.tooling_scope if facts else None
    return {
        "report_version": 2,
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
        "checker_bundle_sha256": bootstrap.bundle_sha256
        if facts and bootstrap
        else None,
        "toolchain_sha256": bootstrap.toolchain_sha256 if facts and bootstrap else None,
        "review_scope_sha256": scope.proof_sha256 if scope else None,
        "reviewed_tooling_changes": [asdict(change) for change in scope.changes]
        if scope
        else [],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PreflightInputError("arguments_invalid")


def main(
    argv: list[str] | None = None, *, bootstrap: BootstrapContext | None = None
) -> int:
    parser = _Parser(
        description=__doc__,
        allow_abbrev=False,
        epilog="Source/schema classification only; not authorization. External configuration needs review.",
    )
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--isolated-compose", action="store_true")
    for name in (
        "repository",
        "candidate",
        "active-release",
        "project",
        "env-file",
        "postgres-service",
        "approved-inventory",
        "inventory-sha256",
        "scratch-directory",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--compose-file", action="append", required=True)
    for name in ("review-scope", "review-scope-sha256", "review-report"):
        parser.add_argument("--" + name)
    supplied = sys.argv[1:] if argv is None else argv
    if "--help" in supplied or "-h" in supplied:
        parser.parse_args(supplied)
    facts = None
    try:
        require(bootstrap is not None, "checker_not_bootstrapped")
        from release_preflight_trust import BootstrapContext as Context

        require(isinstance(bootstrap, Context), "checker_not_bootstrapped")
        if bootstrap is None:
            raise PreflightInputError("checker_not_bootstrapped")
        token(bootstrap.bundle_sha256, HEX64)
        token(bootstrap.toolchain_sha256, HEX64)
        args = parser.parse_args(supplied)
        provided = (args.review_scope, args.review_scope_sha256, args.review_report)
        require(
            all(item is None for item in provided)
            or all(item is not None for item in provided),
            "arguments_invalid",
        )
        require(
            args.review_scope_sha256 == bootstrap.review_scope_sha256,
            "review_scope_mismatch",
        )
        facts = collect_facts(args, bootstrap)
        decision = classify(facts)
    except PreflightInputError as error:
        decision = blocked(error.code)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        RecursionError,
        AttributeError,
        ImportError,
    ):
        decision = blocked("input_invalid")
    print(json.dumps(build_report(facts, decision, bootstrap), sort_keys=True))
    return 2 if decision.action == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
