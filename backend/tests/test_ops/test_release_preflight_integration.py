"""Whole adapter flow with synthetic proof, actual Git and snapshot consumers."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import module
from tests.test_ops.test_release_preflight import Scenario, digest, report


@pytest.fixture
def scenario(tmp_path):
    return Scenario(tmp_path)


def exact_tooling_proof(scenario):
    """Synthetic review authority, only for tests, no production artifact."""
    trust = module("release_preflight_trust")
    raw = json.loads(scenario.context.read_text())
    pins = {
        name: trust.FilePin(Path(v["path"]), v["sha256"], v["mode"], v["uid"])
        for name, v in raw["executables"].items()
    }
    tools = trust.Toolchain(
        **pins,
        postgres=trust.PgEndpoint(**raw["postgres"]),
        limits=trust.InputLimits(**raw["limits"]),
    )
    runner = module("release_preflight_exec").ReadOnlyRunner(
        scenario.repo,
        tools,
        verifier=lambda pin: trust.verify_pinned_file(pin, owner_uid=pin.uid),
    )
    baselines = {s: v["revision"] for s, v in scenario.inventory["services"].items()}
    changes = module("release_preflight_review").collect_source_changes(
        runner,
        candidate=scenario.candidate,
        service_revisions=baselines,
    )
    review = scenario.root / "review.md"
    review.write_text("Synthetic accepted review; not operator approval.")
    review.chmod(0o600)
    proof = scenario.root / "scope.json"
    proof.write_text(
        json.dumps(
            {
                "version": 1,
                "candidate": scenario.candidate,
                "service_revisions": baselines,
                "checker_bundle_sha256": "e" * 64,
                "review_report_sha256": digest(review),
                "review_result": "accepted_no_open_critical_or_important",
                "changes": [asdict(c) for c in changes if c.path == "ops/release_preflight.py"],
            }
        )
    )
    proof.chmod(0o600)
    raw["review_scope_sha256"] = digest(proof)
    scenario.context.write_text(json.dumps(raw))
    return (
        "--review-scope",
        str(proof),
        "--review-scope-sha256",
        digest(proof),
        "--review-report",
        str(review),
    )


@pytest.mark.parametrize("action", ["no_rollout", "app_only", "migration_then_app"])
def test_cli_v2_full_readonly_flow_and_all_gates(scenario, action):
    worker_base = scenario.candidate
    scenario.inventory["services"]["worker"]["revision"] = worker_base
    scenario.active["service_revisions"]["worker"] = worker_base
    for identifier in (scenario.ids["worker"], scenario.images["worker"]):
        observation = scenario.observation(identifier)
        observation["Config"]["Labels"]["org.opencontainers.image.revision"] = worker_base
        scenario.respond(["inspect", identifier], [observation])
    scenario.approve()
    if action != "no_rollout":
        scenario.advance("backend/app/main.py", "changed runtime")
    if action == "migration_then_app":
        scenario.advance(
            "backend/migrations/versions/head.py", "revision='head'\ndown_revision='base'\n"
        )
    scenario.advance("ops/release_preflight.py", "# synthetic tooling change\n")
    value = report(scenario.run(exact_tooling_proof(scenario)), action)
    assert value["report_version"] == 2
    assert value["checker_bundle_sha256"] == "e" * 64
    assert value["toolchain_sha256"] == "f" * 64
    assert value["service_revisions"]["worker"] == worker_base
    assert len(value["reviewed_tooling_changes"]) == 3
    assert all(c["path"] == "ops/release_preflight.py" for c in value["reviewed_tooling_changes"])
    assert "approved_tooling_review" in value["required_gates"]
    if action != "no_rollout":
        assert {
            "approval",
            "ci_build",
            "backup_restore",
            "rollback_compatibility",
            "runtime",
        } <= set(value["required_gates"])
    if action == "migration_then_app":
        assert "exact_migration_approval" in value["required_gates"]
        assert value["pending_migrations"] == ["head"]
    assert len([c for c in scenario.calls() if c[0] == "exec"]) == 1
    assert scenario.exec in scenario.calls()
    assert list(scenario.scratch.iterdir()) == []
    raw_calls = [json.loads(row) for row in scenario.journal.read_text().splitlines()]
    assert all(
        Path(p).parent.parent == scenario.scratch for call in raw_calls for p, _ in call["consumed"]
    )


def test_tooling_only_proof_never_restarts_or_relabels_apps(scenario):
    scenario.advance("ops/release_preflight.py", "# reviewed tooling\n")
    before = scenario.active_file.read_bytes(), scenario.inventory_file.read_bytes()
    value = report(scenario.run(exact_tooling_proof(scenario)), "no_rollout")
    assert value["pending_migrations"] == []
    assert (scenario.active_file.read_bytes(), scenario.inventory_file.read_bytes()) == before
    assert all(c[0] in {"compose", "inspect", "exec"} for c in scenario.calls())
    assert all(
        "restart" not in c and ("up" not in c or c[-2:] == ["up", "--help"])
        for c in scenario.calls()
    )


def test_tooling_proof_after_migration_and_app_rollback_never_repeats_backfill(scenario):
    scenario.advance(
        "backend/migrations/versions/head.py", "revision='head'\ndown_revision='base'\n"
    )
    scenario.advance("ops/release_preflight.py", "# reviewed tooling\n")
    scenario.respond(scenario.exec, "head\n", raw=True)
    value = report(scenario.run(exact_tooling_proof(scenario)), "app_only")
    assert value["schema_from"] == value["schema_to"] == "head"
    assert value["pending_migrations"] == []
    assert "exact_migration_approval" not in value["required_gates"]
    assert all(c == scenario.exec for c in scenario.calls() if c[0] == "exec")


@pytest.mark.parametrize(
    "path",
    [
        "ops/prepare_release.py",
        ".github/workflows/ci.yml",
        "ops/new_operator.py",
        "compose.yaml",
    ],
)
def test_every_unknown_path_blocks_before_docker(scenario, path):
    scenario.advance(path, "unreviewed")
    assert report(scenario.run(), "blocked")["reason_codes"] == ["unknown_change_scope"]
    assert scenario.calls() == []


def test_dockerignore_still_requires_runtime_gates_not_tooling_exemption(scenario):
    scenario.advance(".dockerignore", "build context change")
    value = report(scenario.run(), "app_only")
    assert value["reviewed_tooling_changes"] == []
    assert "ci_build" in value["required_gates"]
    assert "approved_tooling_review" not in value["required_gates"]


@pytest.mark.parametrize("kind", ["timeout", "mutation", "cleanup"])
def test_timeout_mutation_cleanup_and_secret_canaries_do_not_emit_success(scenario, kind):
    response = scenario.responses[json.dumps(scenario.compose + ["config", "--format", "json"])]
    if kind == "timeout":
        response.update(sleep=11, stderr="private-canary-must-not-appear")
    elif kind == "mutation":
        response["mutate"] = str(scenario.env_file)
    else:
        response["cleanup_canary"] = True
    value = report(scenario.run(), "blocked")
    expected = {
        "timeout": "tool_timeout",
        "mutation": "snapshot_input_changed",
        "cleanup": "snapshot_cleanup_failed",
    }[kind]
    assert value["reason_codes"] == [expected]
    assert value["candidate"] is None
    if kind != "cleanup":
        assert list(scenario.scratch.iterdir()) == []
