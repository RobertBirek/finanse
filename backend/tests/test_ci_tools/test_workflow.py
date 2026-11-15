"""Semantic regression of the committed workflow, not a host-only audit."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]  # Existing runtime parser has no bundled stubs.
from packaging.requirements import Requirement


@pytest.fixture
def workflow() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    return yaml.safe_load((root / ".github/workflows/ci.yml").read_text())


def test_workflow_preserves_required_check_and_owned_migration_environment(
    workflow: dict[str, Any],
) -> None:
    from tests.test_ci_tools.workflow_assertions import assert_backend_workflow

    assert_backend_workflow(workflow)


def test_yaml_parser_is_required_by_existing_dependency() -> None:
    backend = Path(__file__).resolve().parents[2]
    required = [
        Requirement(line)
        for line in (backend / "requirements.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert any(r.name == "uvicorn" and "standard" in r.extras for r in required)


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("sudo -- unshare --net", "unshare --user --map-root-user --net"),
        ("--net", ""),
        ('--reuid="$(id -u)"', "--reuid=0"),
        ('--regid="$(id -g)"', "--regid=0"),
        ("--no-new-privs", ""),
        ("env -i", "env"),
        ("--timeout-seconds 40", "--timeout-seconds 400"),
    ],
)
def test_inventory_rejects_unsafe_namespace_or_credentials(
    workflow: dict[str, Any], original: str, replacement: str
) -> None:
    from tests.test_ci_tools.workflow_assertions import assert_backend_workflow

    config = copy.deepcopy(workflow)
    collect = next(
        s
        for s in config["jobs"]["backend_static"]["steps"]
        if "ci_tools.runner collect" in s.get("run", "")
    )
    assert original in collect["run"]
    collect["run"] = collect["run"].replace(original, replacement)
    with pytest.raises(AssertionError):
        assert_backend_workflow(config)


@pytest.mark.parametrize(
    "mutation",
    [
        "check_name",
        "missing_need",
        "gate_condition",
        "matrix_missing",
        "matrix_duplicate",
        "matrix_cancel",
        "host_port",
        "wrong_role",
        "missing_optin",
        "migration_dsn",
        "upload_condition",
        "artifact_name",
        "ignore_missing",
        "no_needs",
        "timeout",
        "history",
    ],
)
def test_workflow_contract_rejects_unsafe_configuration(
    workflow: dict[str, Any], mutation: str
) -> None:
    from tests.test_ci_tools.workflow_assertions import assert_backend_workflow

    config = copy.deepcopy(workflow)
    gate = config["jobs"]["backend"]
    tests = config["jobs"]["backend_tests"]
    upload = next(s for s in tests["steps"] if s.get("uses") == "actions/upload-artifact@v4")
    if mutation == "check_name":
        gate["name"] = "Backend green regardless"
    elif mutation == "missing_need":
        gate["needs"] = ["backend_static"]
    elif mutation == "gate_condition":
        gate["if"] = "success()"
    elif mutation == "matrix_missing":
        tests["strategy"]["matrix"]["group"].pop()
    elif mutation == "matrix_duplicate":
        tests["strategy"]["matrix"]["group"].append("legacy")
    elif mutation == "matrix_cancel":
        tests["strategy"]["fail-fast"] = True
    elif mutation == "host_port":
        tests["services"]["postgres"]["ports"] = ["5432:5432"]
    elif mutation == "wrong_role":
        tests["services"]["postgres"]["env"]["POSTGRES_USER"] = "production"
    elif mutation == "missing_optin":
        tests["env"].pop("BANK_IMPORT_MIGRATIONS_ALLOWED")
    elif mutation == "migration_dsn":
        tests["env"]["BANK_IMPORT_MIGRATION_DATABASE_URL"] = "postgresql+asyncpg://bad:bad@other/db"
    elif mutation == "upload_condition":
        upload["if"] = "success()"
    elif mutation == "artifact_name":
        upload["with"]["name"] = "shared-name"
    elif mutation == "ignore_missing":
        upload["with"]["if-no-files-found"] = "warn"
    elif mutation == "no_needs":
        step = next(s for s in gate["steps"] if "--needs" in s.get("run", ""))
        step["run"] = step["run"].replace('--needs "$RUNNER_TEMP/needs.json"', "")
    elif mutation == "timeout":
        tests["timeout-minutes"] = 40
    else:
        step = next(s for s in tests["steps"] if s.get("uses") == "actions/checkout@v4")
        step["with"]["fetch-depth"] = 1
    with pytest.raises(AssertionError):
        assert_backend_workflow(config)
