"""The isolated renderer accepts only the two read-only operations."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_ops.preflight_fixtures import module

PREFIX = (
    "--project-name",
    "synthetic",
    "--project-directory",
    "/fixture",
    "--env-file",
    "/fixture/env",
    "-f",
    "/fixture/base.yaml",
    "-f",
    "/fixture/override.yaml",
)


def renderer():
    try:
        return module("release_preflight_isolation")
    except ModuleNotFoundError as exc:
        if exc.name != "release_preflight_isolation":
            raise
        pytest.fail("isolated Compose runner is not implemented")


def test_setup_failure_blocks(tmp_path: Path) -> None:
    runner = renderer()
    with pytest.raises(runner.PreflightInputError, match="renderer_setup_failed"):
        runner.run_isolated_compose(tmp_path, (*PREFIX, "up", "--help"), max_output_bytes=4096)


def test_mutating_command_is_not_allowed(tmp_path: Path) -> None:
    runner = renderer()
    with pytest.raises(runner.PreflightInputError, match="renderer_arguments_invalid"):
        runner.run_isolated_compose(tmp_path, (*PREFIX, "up", "-d"), max_output_bytes=4096)


def test_invalid_argument_type_is_rejected(tmp_path: Path) -> None:
    runner = renderer()
    with pytest.raises(runner.PreflightInputError, match="^renderer_arguments_invalid$"):
        runner.run_isolated_compose(
            tmp_path, (*PREFIX[:3], None, *PREFIX[4:], "up", "--help"), max_output_bytes=4096
        )


@pytest.fixture
def synthetic_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Exercise the parent's real pipes with a child that only emits test data."""
    runner = renderer()
    helper = tmp_path / "synthetic_child.py"
    monkeypatch.setattr(runner, "_HELPER", helper)
    monkeypatch.setattr(runner, "_trusted_binary", lambda _root: True)
    monkeypatch.setattr(runner.os, "geteuid", lambda: 0)
    processes = []
    popen = subprocess.Popen

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", capture)
    return runner, helper, processes


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("os.write(1, b'{}')", "renderer_setup_failed"),
        ("os.write(ready, b'X')", "renderer_setup_failed"),
        ("os.write(ready, b'RR')", "renderer_setup_failed"),
        ("os.write(ready, b'R'); os.write(1, b'\\xff')", "renderer_failed"),
        (
            "os.write(ready, b'R'); os.write(1, b'123456'); os.write(2, b'123456')",
            "renderer_output_limit",
        ),
    ],
)
def test_invalid_child_result_is_rejected(
    tmp_path: Path, synthetic_child, body: str, reason: str
) -> None:
    runner, helper, processes = synthetic_child
    helper.write_text(f"import os, sys\nready = int(sys.argv[2])\n{body}\n")
    with pytest.raises(runner.PreflightInputError, match=f"^{reason}$"):
        runner.run_isolated_compose(tmp_path, (*PREFIX, "up", "--help"), max_output_bytes=10)
    (process,) = processes
    assert process.returncode is not None
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))


def test_deadline_terminates_and_reaps_child(
    tmp_path: Path, synthetic_child, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, helper, processes = synthetic_child
    helper.write_text("import time\ntime.sleep(30)\n")
    ticks = iter((0, 11))
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    with pytest.raises(runner.PreflightInputError, match="^renderer_timeout$"):
        runner.run_isolated_compose(tmp_path, (*PREFIX, "up", "--help"), max_output_bytes=4096)
    (process,) = processes
    assert process.returncode == -9
    assert all(stream.closed for stream in (process.stdin, process.stdout, process.stderr))
