"""Semantic regression of the committed workflow, not a host-only audit."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
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


@pytest.mark.parametrize("failure", ["", "nginx:alpine", "python:3.12-alpine", "inspect"])
def test_proxy_preparation_populates_fresh_store_and_fails_closed(
    workflow: dict[str, Any], tmp_path: Path, failure: str
) -> None:
    """Run the workflow's actual shell; stub only the external Docker boundary."""
    steps = workflow["jobs"]["backend_tests"]["steps"]
    preparation = [s for s in steps if s.get("name") == "Prepare local proxy test images"]
    assert len(preparation) == 1, "A fresh hosted runner needs explicit image preparation"
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with Path('calls.jsonl').open('a') as log: log.write(json.dumps(args)+'\\n')\n"
        "store = Path('store.json')\n"
        "images = json.loads(store.read_text()) if store.exists() else []\n"
        "if args[:1] == ['pull']:\n"
        "    if args[1] == os.environ['FAILURE']: sys.exit(1)\n"
        "    images.append(args[1]); store.write_text(json.dumps(images))\n"
        "elif args[:2] == ['image', 'inspect']:\n"
        "    if os.environ['FAILURE'] == 'inspect': sys.exit(1)\n"
        "    assert all(image in images for image in args[2:])\n"
        "    print(json.dumps([{'Id':'sha256:'+str(i)} for i in args[2:]]))\n"
        "else: sys.exit(2)\n"
    )
    docker.chmod(0o700)
    process = subprocess.run(
        ["/bin/bash", "-eu", "-c", preparation[0]["run"]],
        check=False,
        cwd=tmp_path,
        env={"PATH": str(tmp_path) + os.pathsep + "/usr/bin:/bin", "FAILURE": failure},
        capture_output=True,
        text=True,
        timeout=5,
    )
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    expected = [["pull", "nginx:alpine"], ["pull", "python:3.12-alpine"]]
    if failure == "nginx:alpine":
        assert calls == expected[:1] and process.returncode == 1
    elif failure == "python:3.12-alpine":
        assert calls == expected and process.returncode == 1
    else:
        assert calls == expected + [["image", "inspect", "nginx:alpine", "python:3.12-alpine"]]
        assert process.returncode == (1 if failure else 0)
    if not failure:
        assert json.loads((tmp_path / "store.json").read_text()) == [
            "nginx:alpine",
            "python:3.12-alpine",
        ]


@pytest.mark.parametrize(
    "mutation", ["missing", "unconditional", "wrong_group", "timeout", "late", "missing_python"]
)
def test_proxy_preparation_contract_rejects_unsafe_configuration(
    workflow: dict[str, Any], mutation: str
) -> None:
    from tests.test_ci_tools.workflow_assertions import assert_backend_workflow

    config = copy.deepcopy(workflow)
    steps = config["jobs"]["backend_tests"]["steps"]
    images = next(s for s in steps if s.get("name") == "Prepare local proxy test images")
    if mutation == "missing":
        steps.remove(images)
    elif mutation == "unconditional":
        images["if"] = "always()"
    elif mutation == "wrong_group":
        images["if"] = "matrix.group == 'legacy'"
    elif mutation == "timeout":
        images["timeout-minutes"] = 20
    elif mutation == "late":
        steps.remove(images)
        steps.append(images)
    else:
        images["run"] = images["run"].replace("docker pull python:3.12-alpine\n", "")
    with pytest.raises(AssertionError):
        assert_backend_workflow(config)


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
