"""Test-only semantic policy assertions, applied to real YAML and mutated copies."""

from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import urlsplit

from ci_tools.partition import GROUPS


def _action(job: dict[str, Any], action: str) -> dict[str, Any]:
    steps = [s for s in job["steps"] if s.get("uses") == action]
    assert len(steps) == 1
    return steps[0]


def _runner(job: dict[str, Any], mode: str) -> tuple[dict[str, Any], list[str]]:
    commands = []
    for step in job["steps"]:
        words = shlex.split(step.get("run", "").replace("\\\n", " "))
        if "ci_tools.runner" in words:
            index = words.index("ci_tools.runner")
            if words[index + 1] == mode:
                commands.append((step, words[index + 2 :]))
    assert len(commands) == 1
    return commands[0]


def _flag(words: list[str], flag: str) -> str:
    assert words.count(flag) == 1
    return words[words.index(flag) + 1]


def assert_backend_workflow(workflow: dict[str, Any]) -> None:
    jobs = workflow["jobs"]
    static, tests, gate = (jobs[name] for name in ("backend_static", "backend_tests", "backend"))
    assert gate["name"] == "Backend tests and static checks"
    assert set(gate["needs"]) == {"backend_static", "backend_tests"}
    assert gate["if"] in ("always()", "${{ always() }}")
    assert tests["needs"] == "backend_static"
    for job in (static, tests, gate):
        assert job["timeout-minutes"] == 20
        assert _action(job, "actions/checkout@v4")["with"]["fetch-depth"] == 0
    strategy = tests["strategy"]
    assert strategy["fail-fast"] is False
    assert 1 <= strategy["max-parallel"] <= 3
    groups = strategy["matrix"]["group"]
    assert len(groups) == len(GROUPS) and set(groups) == set(GROUPS)
    pg = tests["services"]["postgres"]
    assert pg["image"] == "postgres:16-alpine"
    assert pg["ports"] == ["127.0.0.1:5432:5432"]
    role = pg["env"]["POSTGRES_USER"]
    assert re.fullmatch(r"bank_import_task_[0-9a-f]+", role)
    assert pg["env"]["POSTGRES_DB"] == "finanse_test"
    assert tests["env"].get("BANK_IMPORT_MIGRATIONS_ALLOWED") == "owned_no_port_runner"
    for key in ("TEST_DATABASE_URL", "DATABASE_URL", "BANK_IMPORT_MIGRATION_DATABASE_URL"):
        url = urlsplit(tests["env"][key])
        assert url.scheme == "postgresql+asyncpg"
        assert url.hostname == "127.0.0.1" and url.port == 5432
        assert url.username == role and url.password == pg["env"]["POSTGRES_PASSWORD"]
        assert url.path == "/finanse_test"
    upload = _action(tests, "actions/upload-artifact@v4")
    assert upload["if"] in ("always()", "${{ always() }}")
    assert upload["with"]["name"] == "backend-result-${{ matrix.group }}"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["path"] == "${{ runner.temp }}/backend-artifacts/"
    downloads = [
        step["with"] for step in gate["steps"] if step.get("uses") == "actions/download-artifact@v4"
    ]
    assert {
        "pattern": "backend-result-*",
        "merge-multiple": True,
        "path": "${{ runner.temp }}/backend-results",
    } in downloads
    assert {"name": "backend-manifest", "path": "${{ runner.temp }}/ci-manifest"} in downloads
    _, run = _runner(tests, "run")
    assert _flag(run, "--group") == "${{ matrix.group }}"
    assert _flag(run, "--manifest") == "$RUNNER_TEMP/ci-manifest/manifest.json"
    assert _flag(run, "--output") == "$RUNNER_TEMP/backend-artifacts/${{ matrix.group }}"
    assert int(_flag(run, "--timeout-seconds")) == 720
    verify, arguments = _runner(gate, "verify")
    assert verify["env"]["CI_NEEDS"] == "${{ toJSON(needs) }}"
    assert _flag(arguments, "--needs") == "$RUNNER_TEMP/needs.json"
    assert _flag(arguments, "--results") == "$RUNNER_TEMP/backend-results"
    assert _flag(arguments, "--manifest") == "$RUNNER_TEMP/ci-manifest/manifest.json"
