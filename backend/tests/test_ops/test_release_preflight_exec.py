"""Pinned argv execution and schema evidence must not inherit ambient settings."""

import json
from dataclasses import replace

import pytest

from tests.test_ops.preflight_fixtures import PinnedScenario, module


@pytest.fixture
def scenario(tmp_path):
    return PinnedScenario(tmp_path)


@pytest.mark.parametrize("kind", ["git", "docker"])
def test_inherited_path_cannot_substitute_git_or_docker(scenario, monkeypatch, kind):
    execute = module("release_preflight_exec")
    evil = scenario.root / "evil"
    evil.mkdir()
    marker = scenario.root / "executed"
    binary = evil / kind
    binary.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    binary.chmod(0o700)
    monkeypatch.setenv("PATH", str(evil))
    monkeypatch.setenv("DOCKER_HOST", "tcp://foreign.invalid")
    monkeypatch.setenv("GIT_DIR", "/foreign")
    runner = scenario.runner()
    if kind == "git":
        command = scenario.git_prefix + ["rev-parse", "--show-toplevel"]
        scenario.respond(command, stdout="synthetic-ok\n")
    else:
        command = ["docker", "inspect", "4" * 64]
        scenario.respond(
            ["docker", "--host", "unix:///var/run/docker.sock", "inspect", "4" * 64],
            stdout="synthetic-ok\n",
        )
    assert runner.run(command) == "synthetic-ok\n"
    assert not marker.exists()
    assert scenario.calls()[0]["env"].get("GIT_DIR") is None
    assert "foreign.invalid" not in json.dumps(scenario.calls())
    with pytest.raises(execute.PreflightInputError):
        runner.run(["git", "push"])


def test_compose_plugin_search_is_not_used(scenario, monkeypatch):
    module("release_preflight_exec")
    monkeypatch.setenv("DOCKER_CONFIG", "/foreign/plugins")
    monkeypatch.setenv("DOCKER_CLI_PLUGIN_EXTRA_DIRS", "/foreign/plugins")
    scenario.respond(scenario.compose_prefix + ["up", "--help"], stdout="--no-build\n")
    assert scenario.runner().run(scenario.compose_prefix + ["up", "--help"]) == "--no-build\n"
    call = scenario.calls()[0]
    assert call["role"] == "compose"
    assert call["env"]["DOCKER_HOST"] == "unix:///var/run/docker.sock"
    assert call["env"]["DOCKER_CONFIG"] == "/nonexistent"
    assert "DOCKER_CLI_PLUGIN_EXTRA_DIRS" not in call["env"]


def test_pg_endpoint_is_explicit_and_inherited_libpq_is_erased(scenario, monkeypatch):
    module("release_preflight_exec")
    monkeypatch.setenv("PGHOST", "host-canary.invalid")
    monkeypatch.setenv("PGSERVICE", "host-service-canary")
    assert scenario.runner().schema_heads() == ("base",)
    calls = scenario.calls()
    query_calls = [c for c in calls if "exec" in c["argv"]]
    assert len(query_calls) == 1
    assert ["docker", *query_calls[0]["argv"]] == scenario.pg_command
    assert "PGHOST" not in query_calls[0]["env"]
    assert "PGSERVICE" not in query_calls[0]["env"]


def test_pg_os_identity_and_database_role_are_distinct(scenario):
    execute = module("release_preflight_exec")
    scenario.respond(scenario.pg_command, code=2, stderr="private-password-canary")
    with pytest.raises(execute.PreflightInputError) as error:
        scenario.runner().schema_heads()
    assert "private-password-canary" not in str(error.value)
    query_calls = [c for c in scenario.calls() if "exec" in c["argv"]]
    assert len(query_calls) == 1
    assert ["docker", *query_calls[0]["argv"]] == scenario.pg_command
    assert "999:999" in query_calls[0]["argv"]
    assert "synthetic_finance" in query_calls[0]["argv"]


@pytest.mark.parametrize("kind", ["image", "bind_socket", "volume_socket", "role", "project"])
def test_pg_target_mismatch_blocks_before_exec(scenario, kind):
    execute = module("release_preflight_exec")
    observation = scenario.pg_observation
    if kind == "image":
        observation["Image"] = "sha256:" + "f" * 64
    elif kind in {"bind_socket", "volume_socket"}:
        observation["Mounts"] = [
            {
                "Type": "bind" if kind == "bind_socket" else "volume",
                "Destination": "/var/run",
            }
        ]
    elif kind == "role":
        observation["Config"]["Env"][0] = "POSTGRES_USER=foreign"
    else:
        observation["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
    scenario.respond(
        ["docker", "--host", "unix:///var/run/docker.sock", "inspect", "4" * 64],
        stdout=json.dumps([observation]),
    )
    with pytest.raises(execute.PreflightInputError):
        scenario.runner().schema_heads()
    assert not [c for c in scenario.calls() if "exec" in c["argv"]]


@pytest.mark.parametrize(
    "command",
    [
        ["docker", "restart", "4" * 64],
        ["docker", "exec", "4" * 64, "psql", "-c", "DELETE FROM users"],
        ["compose", "up", "-d"],
        ["git", "fetch"],
        [],
    ],
)
def test_mutating_and_arbitrary_sql_argv_are_rejected(scenario, command):
    execute = module("release_preflight_exec")
    with pytest.raises(execute.PreflightInputError):
        scenario.runner().run(command)
    assert scenario.calls() == []


def test_changed_binary_after_bind_never_executes(scenario):
    execute = module("release_preflight_exec")
    runner = scenario.runner()
    marker = scenario.root / "executed"
    scenario.tools.git.path.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
    with pytest.raises(execute.PreflightInputError):
        runner.run(scenario.git_prefix + ["rev-parse", "--show-toplevel"])
    assert not marker.exists()


def test_output_limit_blocks_without_leaking_stderr(scenario):
    execute = module("release_preflight_exec")
    scenario.tools = replace(
        scenario.tools, limits=replace(scenario.tools.limits, max_output_bytes=128)
    )
    scenario.respond(
        scenario.git_prefix + ["rev-parse", "--show-toplevel"],
        stderr="private-canary" * 1000,
    )
    with pytest.raises(execute.PreflightInputError) as error:
        scenario.runner().run(scenario.git_prefix + ["rev-parse", "--show-toplevel"])
    assert error.value.code == "tool_output_limit"
    assert "private-canary" not in str(error.value)


def test_timeout_is_bounded_and_redacted(scenario):
    execute = module("release_preflight_exec")
    scenario.respond(
        scenario.git_prefix + ["rev-parse", "--show-toplevel"],
        sleep=11,
        stderr="private-canary",
    )
    with pytest.raises(execute.PreflightInputError) as error:
        scenario.runner().run(scenario.git_prefix + ["rev-parse", "--show-toplevel"])
    assert error.value.code == "tool_timeout"
    assert "private-canary" not in str(error.value)
