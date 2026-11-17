"""Pure, fail-closed source/schema classification. Never authorizes a release."""

import ast
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

SERVICES = frozenset({"backend", "worker", "frontend"})
SHA = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
REVISION = re.compile(r"[A-Za-z0-9_-]{1,128}")
TEST_PATH = re.compile(r"frontend/src/(?:[^/]+/)*[^/]+\.test\.tsx?")
STAGE_FLAGS = frozenset({"--no-start", "--no-deps", "--no-build"})
CONFIG_GATE = ("external_configuration_scope_review",)
APP_GATES = (
    "approval",
    "ci_build",
    "verify_release",
    "backup_restore",
    "fenced_retention",
    "rollback_compatibility",
    "runtime",
)


class PreflightInputError(ValueError):
    """Only a public, fixed reason code may cross the reporting boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReleaseFacts:
    candidate: str
    service_revisions: dict[str, str]
    image_ids: dict[str, str]
    changed_paths: dict[str, tuple[str, ...]]
    schema_heads: tuple[str, ...]
    lineage: dict[str, str | None]
    compose_up_flags: frozenset[str]
    ancestry_ok: bool
    historical_migration_changed: bool


@dataclass(frozen=True)
class PreflightDecision:
    action: Literal["no_rollout", "app_only", "migration_then_app", "blocked"]
    pending_migrations: tuple[str, ...]
    reason_codes: tuple[str, ...]
    required_gates: tuple[str, ...]


def blocked(code: str) -> PreflightDecision:
    return PreflightDecision("blocked", (), (code,), CONFIG_GATE)


def ordered_lineage(lineage: dict[str, str | None]) -> tuple[str, ...]:
    if not isinstance(lineage, dict) or not lineage:
        raise PreflightInputError("migration_graph_invalid")
    children: dict[str, str] = {}
    roots = []
    for revision, parent in lineage.items():
        if not isinstance(revision, str) or not REVISION.fullmatch(revision):
            raise PreflightInputError("migration_graph_invalid")
        if parent is None:
            roots.append(revision)
        elif (
            not isinstance(parent, str)
            or not REVISION.fullmatch(parent)
            or parent not in lineage
            or parent in children
        ):
            raise PreflightInputError("migration_graph_invalid")
        else:
            children[parent] = revision
    if len(roots) != 1:
        raise PreflightInputError("migration_graph_invalid")
    chain = [roots[0]]
    seen = {roots[0]}
    while chain[-1] in children:
        child = children[chain[-1]]
        if child in seen:
            raise PreflightInputError("migration_graph_invalid")
        chain.append(child)
        seen.add(child)
    if len(chain) != len(lineage):
        raise PreflightInputError("migration_graph_invalid")
    return tuple(chain)


def parse_lineage(sources: dict[str, str]) -> dict[str, str | None]:
    lineage: dict[str, str | None] = {}
    for source in sources.values():
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, TypeError, RecursionError):
            raise PreflightInputError("migration_ast_invalid") from None
        values: dict[str, str | None] = {}
        accepted: set[int] = set()
        for statement in tree.body:
            target = None
            value = None
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target, value = statement.targets[0], statement.value
            elif isinstance(statement, ast.AnnAssign):
                target, value = statement.target, statement.value
            if isinstance(target, ast.Name) and target.id in {
                "revision",
                "down_revision",
            }:
                if (
                    target.id in values
                    or not isinstance(value, ast.Constant)
                    or (value.value is not None and not isinstance(value.value, str))
                ):
                    raise PreflightInputError("migration_ast_invalid")
                values[target.id] = value.value
                accepted.add(id(target))
        # Nested/repeated/dynamic assignments cannot secretly replace the parsed constants.
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and node.id in {"revision", "down_revision"}
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and id(node) not in accepted
            ):
                raise PreflightInputError("migration_ast_invalid")
        revision = values.get("revision")
        if set(values) != {"revision", "down_revision"} or not isinstance(
            revision, str
        ):
            raise PreflightInputError("migration_ast_invalid")
        if revision in lineage:
            raise PreflightInputError("migration_graph_invalid")
        lineage[revision] = values["down_revision"]
    ordered_lineage(lineage)
    return lineage


def _valid_service_map(values: object, pattern: re.Pattern[str]) -> bool:
    return (
        isinstance(values, dict)
        and set(values) == SERVICES
        and all(
            isinstance(value, str) and pattern.fullmatch(value)
            for value in values.values()
        )
    )


def _runtime_scope(path: str) -> str:
    if (
        not path
        or path.startswith("/")
        or str(PurePosixPath(path)) != path
        or ".." in PurePosixPath(path).parts
        or any(ord(char) < 32 for char in path)
    ):
        raise PreflightInputError("unknown_change_scope")
    if path.startswith(
        ("docs/", "backend/tests/", "frontend/e2e/")
    ) or TEST_PATH.fullmatch(path):
        return "none"
    if path == ".dockerignore":
        return "all"
    if path.startswith("backend/"):
        return "backend"
    if path.startswith("frontend/"):
        return "frontend"
    raise PreflightInputError("unknown_change_scope")


def _classify(facts: ReleaseFacts) -> PreflightDecision:
    if (
        not isinstance(facts.candidate, str)
        or not SHA.fullmatch(facts.candidate)
        or not _valid_service_map(facts.service_revisions, SHA)
        or not _valid_service_map(facts.image_ids, IMAGE_ID)
        or not isinstance(facts.changed_paths, dict)
        or set(facts.changed_paths) != SERVICES
        or type(facts.ancestry_ok) is not bool
        or type(facts.historical_migration_changed) is not bool
        or not isinstance(facts.schema_heads, tuple)
        or not isinstance(facts.compose_up_flags, frozenset)
        or not all(isinstance(flag, str) for flag in facts.compose_up_flags)
    ):
        raise PreflightInputError("facts_invalid")
    if not facts.ancestry_ok:
        raise PreflightInputError("candidate_ancestry_invalid")
    if facts.historical_migration_changed:
        raise PreflightInputError("historical_migration_changed")
    chain = ordered_lineage(facts.lineage)
    if len(facts.schema_heads) != 1 or facts.schema_heads[0] not in chain:
        raise PreflightInputError("schema_head_invalid")
    pending = chain[chain.index(facts.schema_heads[0]) + 1 :]
    runtime_change = False
    dependencies_changed = False
    for service, paths in facts.changed_paths.items():
        if not isinstance(paths, tuple) or not all(
            isinstance(path, str) for path in paths
        ):
            raise PreflightInputError("facts_invalid")
        for path in paths:
            scope = _runtime_scope(path)
            relevant = scope == "all" or scope == (
                "frontend" if service == "frontend" else "backend"
            )
            runtime_change |= relevant
            dependencies_changed |= relevant and path in {
                "backend/requirements.txt",
                "backend/pyproject.toml",
            }
    if not pending and not runtime_change:
        return PreflightDecision("no_rollout", (), (), CONFIG_GATE)
    if not STAGE_FLAGS <= facts.compose_up_flags:
        raise PreflightInputError("compose_capability_missing")
    gates: tuple[str, ...] = CONFIG_GATE + APP_GATES
    if dependencies_changed:
        gates += ("rebuild_and_verify_runtime",)
    if pending:
        return PreflightDecision(
            "migration_then_app", pending, (), gates + ("exact_migration_approval",)
        )
    return PreflightDecision("app_only", (), (), gates)


def classify(facts: ReleaseFacts) -> PreflightDecision:
    if not isinstance(facts, ReleaseFacts):
        return blocked("facts_invalid")
    try:
        return _classify(facts)
    except PreflightInputError as exc:
        return blocked(exc.code)
