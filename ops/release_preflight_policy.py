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
CHECKER_SOURCE_PATHS = frozenset(
    {
        "ops/release_preflight.py",
        "ops/release_preflight_policy.py",
        "ops/release_preflight_trust.py",
        "ops/release_preflight_exec.py",
        "ops/release_preflight_snapshot.py",
        "ops/release_preflight_review.py",
        "ops/preflight_launcher.py",
        "ops/prepare_preflight_bundle.py",
        "ops/preflight-requirements.txt",
    }
)
NODE_CI_PATH = ".github/workflows/ci.yml"
# PR #11 changed only the frontend runner's Node pin: 22 → 24.22.3.
# This witness makes that transition eligible for review, not trusted by default.
REVIEWED_NODE_CI_TRANSITION = (
    "14501064d0b671310fb713ed67f2db0490e43da2",
    "15a67462ad13053766cc1359dc11142fc40a245c",
    "0ed9e79f0ab37b7163481e0fa1db1c99a6a3c9ef2f20214c18b7544bfda71ebe",
)
TOOLING_PATHS = CHECKER_SOURCE_PATHS | {".opencode/command/deploy.md", NODE_CI_PATH}
DIGEST = re.compile(r"[0-9a-f]{64}")
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
class SourceChange:
    service: str
    path: str
    before_mode: str | None
    before_blob: str | None
    after_mode: str | None
    after_blob: str | None
    after_sha256: str | None


@dataclass(frozen=True)
class VerifiedToolingScope:
    proof_sha256: str
    changes: tuple[SourceChange, ...]
    candidate: str
    service_revisions: tuple[tuple[str, str], ...]
    checker_bundle_sha256: str


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
    tooling_scope: VerifiedToolingScope | None = None
    checker_bundle_sha256: str | None = None


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
            if (
                isinstance(target, ast.Name)
                and target.id in {"branch_labels", "depends_on"}
                and (not isinstance(value, ast.Constant) or value.value is not None)
            ):
                raise PreflightInputError("migration_ast_invalid")
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


def valid_tooling_change(value: object) -> bool:
    if (
        not isinstance(value, SourceChange)
        or not isinstance(value.service, str)
        or value.service not in SERVICES
        or not isinstance(value.path, str)
        or value.path not in TOOLING_PATHS
    ):
        return False
    if value.path == NODE_CI_PATH:
        return (
            value.before_mode == value.after_mode == "100644"
            and (value.before_blob, value.after_blob, value.after_sha256)
            == REVIEWED_NODE_CI_TRANSITION
        )
    for mode, blob in (
        (value.before_mode, value.before_blob),
        (value.after_mode, value.after_blob),
    ):
        if mode is None:
            if blob is not None:
                return False
        elif (
            not isinstance(mode, str)
            or mode not in {"100644", "100755"}
            or not isinstance(blob, str)
            or not SHA.fullmatch(blob)
        ):
            return False
    if value.before_blob is None and value.after_blob is None:
        return False
    return (value.after_blob is None and value.after_sha256 is None) or (
        value.after_blob is not None
        and isinstance(value.after_sha256, str)
        and DIGEST.fullmatch(value.after_sha256) is not None
    )


def _reviewed_pairs(facts: ReleaseFacts) -> set[tuple[str, str]]:
    scope = facts.tooling_scope
    if scope is None:
        return set()
    if (
        not isinstance(scope, VerifiedToolingScope)
        or not isinstance(scope.proof_sha256, str)
        or not DIGEST.fullmatch(scope.proof_sha256)
        or scope.candidate != facts.candidate
        or scope.service_revisions != tuple(sorted(facts.service_revisions.items()))
        or not isinstance(facts.checker_bundle_sha256, str)
        or not DIGEST.fullmatch(facts.checker_bundle_sha256)
        or scope.checker_bundle_sha256 != facts.checker_bundle_sha256
        or not isinstance(scope.changes, tuple)
    ):
        raise PreflightInputError("tooling_scope_mismatch")
    actual: set[tuple[str, str]] = set()
    for service, paths in facts.changed_paths.items():
        for path in paths:
            try:
                _runtime_scope(path)
            except PreflightInputError:
                actual.add((service, path))
    reviewed: set[tuple[str, str]] = set()
    for item in scope.changes:
        if (
            not isinstance(item, SourceChange)
            or not isinstance(item.path, str)
            or item.path not in TOOLING_PATHS
        ):
            raise PreflightInputError("unknown_change_scope")
        if not valid_tooling_change(item):
            raise PreflightInputError("tooling_scope_mismatch")
        pair = (item.service, item.path)
        if pair in reviewed:
            raise PreflightInputError("tooling_scope_mismatch")
        reviewed.add(pair)
    if not reviewed or reviewed != actual:
        raise PreflightInputError("tooling_scope_mismatch")
    return reviewed


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
    for paths in facts.changed_paths.values():
        if not isinstance(paths, tuple) or not all(
            isinstance(path, str) for path in paths
        ):
            raise PreflightInputError("facts_invalid")
    reviewed = _reviewed_pairs(facts)
    config_gates = CONFIG_GATE + (("approved_tooling_review",) if reviewed else ())
    for service, paths in facts.changed_paths.items():
        if not isinstance(paths, tuple) or not all(
            isinstance(path, str) for path in paths
        ):
            raise PreflightInputError("facts_invalid")
        for path in paths:
            try:
                scope = _runtime_scope(path)
            except PreflightInputError:
                if (service, path) not in reviewed:
                    raise
                scope = "reviewed_tooling"
            relevant = scope == "all" or scope == (
                "frontend" if service == "frontend" else "backend"
            )
            runtime_change |= relevant
            dependencies_changed |= relevant and path in {
                "backend/requirements.txt",
                "backend/pyproject.toml",
            }
    if not pending and not runtime_change:
        return PreflightDecision("no_rollout", (), (), config_gates)
    if not STAGE_FLAGS <= facts.compose_up_flags:
        raise PreflightInputError("compose_capability_missing")
    gates: tuple[str, ...] = config_gates + APP_GATES
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
