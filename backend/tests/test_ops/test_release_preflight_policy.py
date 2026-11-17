"""A false no_rollout or repeated backfill must be rejected without any I/O."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from tests.test_ops.preflight_fixtures import module


@pytest.fixture
def policy() -> Any:
    return module("release_preflight_policy")


@pytest.fixture
def facts(policy: Any) -> Any:
    return policy.ReleaseFacts(
        candidate="a" * 40,
        service_revisions={"backend": "b" * 40, "worker": "c" * 40, "frontend": "d" * 40},
        image_ids={name: "sha256:" + "e" * 64 for name in ("backend", "worker", "frontend")},
        changed_paths={
            "backend": ("docs/CHANGELOG.md", "backend/tests/test_example.py"),
            "worker": ("frontend/src/components/DocumentList.test.tsx",),
            "frontend": ("frontend/e2e/finance.spec.ts",),
        },
        schema_heads=("head",),
        lineage={"base": None, "middle": "base", "head": "middle"},
        compose_up_flags=frozenset({"--no-start", "--no-deps", "--no-build"}),
        ancestry_ok=True,
        historical_migration_changed=False,
    )


def test_docs_and_test_only_is_no_rollout(policy: Any, facts: Any) -> None:
    decision = policy.classify(facts)
    assert decision.action == "no_rollout"
    assert decision.pending_migrations == ()
    assert "verify_release" not in decision.required_gates
    assert "external_configuration_scope_review" in decision.required_gates


def test_backend_older_than_frontend_still_requires_app(policy: Any, facts: Any) -> None:
    paths = {**facts.changed_paths, "backend": ("backend/app/main.py",)}
    decision = policy.classify(replace(facts, changed_paths=paths))
    assert decision.action == "app_only"
    assert decision.pending_migrations == ()
    assert {"approval", "verify_release", "backup_restore", "runtime"} <= set(
        decision.required_gates
    )


def test_other_service_only_paths_do_not_force_rollout(policy: Any, facts: Any) -> None:
    paths = {**facts.changed_paths, "backend": ("frontend/src/App.tsx",)}
    assert policy.classify(replace(facts, changed_paths=paths)).action == "no_rollout"


def test_already_applied_head_never_repeats_migration(policy: Any, facts: Any) -> None:
    paths = {**facts.changed_paths, "backend": ("backend/migrations/versions/head.py",)}
    decision = policy.classify(replace(facts, changed_paths=paths))
    assert decision.action == "app_only"
    assert decision.pending_migrations == ()


def test_missing_linear_revisions_are_ordered(policy: Any, facts: Any) -> None:
    decision = policy.classify(replace(facts, schema_heads=("base",)))
    assert decision.action == "migration_then_app"
    assert decision.pending_migrations == ("middle", "head")
    assert "exact_migration_approval" in decision.required_gates


@pytest.mark.parametrize(
    "change",
    [
        {"schema_heads": ()},
        {"schema_heads": ("base", "head")},
        {"schema_heads": ("unrecognised",)},
        {"lineage": {}},
        {"lineage": {"x": None, "y": None}},
        {"lineage": {"x": "missing"}},
        {"lineage": {"x": "y", "y": "x"}},
        {"lineage": {"base": None, "x": "base", "y": "base"}},
        {"ancestry_ok": False},
    ],
)
def test_unknown_multihead_branch_cycle_and_duplicate_block(
    policy: Any, facts: Any, change: dict[str, Any]
) -> None:
    assert policy.classify(replace(facts, **change)).action == "blocked"


def test_duplicate_revision_blocks_parser(policy: Any) -> None:
    with pytest.raises(policy.PreflightInputError):
        policy.parse_lineage(
            {
                "one.py": "revision = 'base'\ndown_revision = None",
                "two.py": "revision = 'base'\ndown_revision = None",
            }
        )


def test_edit_or_delete_historical_migration_blocks(policy: Any, facts: Any) -> None:
    decision = policy.classify(replace(facts, historical_migration_changed=True))
    assert decision.action == "blocked"
    assert decision.reason_codes == ("historical_migration_changed",)


def test_lineage_ast_never_executes_source(policy: Any, tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    source = (
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "revision: str = 'base'\ndown_revision: str | None = None\n"
    )
    assert policy.parse_lineage({"base.py": source}) == {"base": None}
    assert not marker.exists()
    with pytest.raises(policy.PreflightInputError):
        policy.parse_lineage({"bad.py": "revision = str(1)\ndown_revision = None"})


@pytest.mark.parametrize(
    "source",
    [
        "revision = 'a'\ndown_revision = ('b', 'c')",
        "revision = 'a'\nrevision = 'b'\ndown_revision = None",
        "revision = 'a'\ndown_revision = None\nif True:\n revision = 'b'",
        "revision = ''\ndown_revision = None",
        "revision = 'a'\ndown_revision = 'missing'",
    ],
)
def test_unsupported_or_inconsistent_ast_blocks(policy: Any, source: str) -> None:
    with pytest.raises(policy.PreflightInputError):
        policy.parse_lineage({"bad.py": source})


@pytest.mark.parametrize(
    ("paths", "action"),
    [
        (("frontend/src/a.test.tsx", "frontend/src/a.tsx"), "app_only"),
        (("docs/readme.md", ".github/workflows/test.yml"), "blocked"),
        (("ops/prepare_release.py",), "blocked"),
        ((".dockerignore",), "app_only"),
        (("frontend/src/../a.test.tsx",), "blocked"),
        (("/docs/readme.md",), "blocked"),
    ],
)
def test_rename_test_to_runtime_and_unknown_paths_never_skip(
    policy: Any, facts: Any, paths: tuple[str, ...], action: str
) -> None:
    changed = {**facts.changed_paths, "frontend": paths}
    assert policy.classify(replace(facts, changed_paths=changed)).action == action


@pytest.mark.parametrize("missing", ["--no-start", "--no-deps", "--no-build"])
def test_missing_compose_stage_flags_blocks_app_actions(
    policy: Any, facts: Any, missing: str
) -> None:
    changed = {**facts.changed_paths, "backend": ("backend/app/main.py",)}
    decision = policy.classify(
        replace(
            facts,
            changed_paths=changed,
            compose_up_flags=facts.compose_up_flags - {missing},
        )
    )
    assert decision.action == "blocked"
    assert decision.reason_codes == ("compose_capability_missing",)


def test_backend_dependencies_require_new_runtime_gate(policy: Any, facts: Any) -> None:
    paths = {**facts.changed_paths, "backend": ("backend/requirements.txt",)}
    decision = policy.classify(replace(facts, changed_paths=paths))
    assert decision.action == "app_only"
    assert "rebuild_and_verify_runtime" in decision.required_gates


@pytest.mark.parametrize(
    "change",
    [
        {"candidate": "HEAD"},
        {"candidate": "a" * 40 + "\n"},
        {"service_revisions": {"backend": "b" * 40}},
        {"image_ids": {"backend": "local/mutable:latest"}},
        {"changed_paths": {"backend": ("docs/ok.md",)}},
        {"historical_migration_changed": None},
        {"ancestry_ok": 1},
    ],
)
def test_malformed_facts_cannot_classify_as_no_rollout(
    policy: Any, facts: Any, change: dict[str, Any]
) -> None:
    assert policy.classify(replace(facts, **change)).action == "blocked"
