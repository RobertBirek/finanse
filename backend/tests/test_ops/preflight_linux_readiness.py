"""Explicit readiness gate for the pinned Compose binary and local Linux host."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import module
from tests.test_ops.test_release_preflight_isolation import renderer

COMPOSE_SHA = "9c0f3f21b463fbdd42afed3be203c1a65f0cd440c9b59c68785f35e78d2ebf6a"


def test_required_profile(tmp_path: Path) -> None:
    binary = os.environ.get("FINANSE_TEST_PINNED_COMPOSE")
    if not binary:
        pytest.fail("requires explicitly enabled Linux isolation tests")
    root = tmp_path / "root"
    root.mkdir()
    # As in snapshot capture, allow the dropped UID to traverse the
    # synthetic chroot even when the test driver uses a private umask.
    root.chmod(0o755)
    (root / "bin").mkdir()
    (root / "bin").chmod(0o755)
    shutil.copyfile(binary, root / "bin/compose")
    (root / "bin/compose").chmod(0o555)
    sample = root / "approved.txt"
    sample.write_text("synthetic")
    sample.chmod(0o444)
    outside = tmp_path / "host-only.txt"
    outside.write_text("synthetic")
    outside.chmod(0o444)
    probe = """
import ctypes
import errno
import os
import socket
import sys
from pathlib import Path

ops, root, outside, status, extra = sys.argv[1:]
sys.path.insert(0, ops)
from release_preflight_isolation import _child

def denied(action, expected):
    try:
        action()
    except OSError as exc:
        assert exc.errno == expected, (exc.errno, expected)
    else:
        raise AssertionError("expected denial")

def inspect(path, arguments, environment):
    assert path == "/bin/compose"
    assert os.getcwd() == "/"
    assert os.getresuid() == os.getresgid() == (65534,) * 3
    assert not os.getgroups()
    libc = ctypes.CDLL(None)
    header = (ctypes.c_uint32 * 2)(0x20080522, 0)
    data = (ctypes.c_uint32 * 6)()
    assert libc.capget(header, data) == 0 and not any(data)
    assert libc.prctl(39, 0, 0, 0, 0) == 1
    assert libc.prctl(21, 0, 0, 0, 0) == 2
    denied(lambda: os.fstat(int(extra)), errno.EBADF)
    denied(lambda: os.fstat(int(status)), errno.EBADF)
    assert Path("/approved.txt").read_text() == "synthetic"
    denied(lambda: os.open("/approved.txt", os.O_WRONLY), errno.EACCES)
    denied(lambda: os.open(outside, os.O_RDONLY), errno.ENOENT)
    for family in (socket.AF_INET, socket.AF_UNIX):
        denied(lambda: socket.socket(family, socket.SOCK_STREAM), errno.EPERM)
    os._exit(0)

# Inspect the actual setup immediately before it would execute pinned Compose.
os.execve = inspect
libc = ctypes.CDLL(None)
assert libc.prctl(8, 1, 0, 0, 0) == 0  # Exercise inherited keep-caps state.
_child(Path(root), int(status), (
    "--project-name", "synthetic", "--project-directory", "/fixture",
    "--env-file", "/fixture/env", "-f", "/fixture/base.yaml",
    "-f", "/fixture/override.yaml", "up", "--help",
))
"""
    reader, writer = os.pipe()
    try:
        with outside.open("rb") as host_file:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    probe,
                    str(Path(renderer().__file__).parent),
                    str(root),
                    str(outside),
                    str(writer),
                    str(host_file.fileno()),
                ],
                pass_fds=(writer, host_file.fileno()),
                env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
                capture_output=True,
                timeout=10,
                check=False,
            )
        os.close(writer)
        writer = -1
        assert result.returncode == 0, result.stderr.decode()
        assert os.read(reader, 2) == b"R"
        assert os.read(reader, 1) == b""
    finally:
        os.close(reader)
        if writer != -1:
            os.close(writer)


def test_isolated_render_matches_reference(tmp_path: Path) -> None:
    path = os.environ.get("FINANSE_TEST_PINNED_COMPOSE")
    if path is None:
        pytest.fail("requires explicitly selected pinned Compose and Linux isolation")
    binary = Path(path)
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == COMPOSE_SHA
    tmp_path.chmod(0o700)
    fixture = tmp_path / "fixture"
    fixture.mkdir(mode=0o755)
    (fixture / "env").write_text("VALUE=synthetic\n")
    deps = [fixture / f"dep-{n}.yaml" for n in range(21)]

    def extends(path: Path) -> str:
        return f"    extends: {{file: {json.dumps(str(path))}, service: base}}\n"

    for dep, target in pairwise(deps):
        dep.write_text("services:\n  base:\n" + extends(target))
    deps[-1].write_text(
        "services:\n  base:\n    image: example.invalid/fixture:fixed\n"
        "    environment: {VALUE: '${VALUE}', PRIORITY: inherited}\n"
        "    volumes: ['./data:/fixture-data']\n    build: {context: ./build}\n"
    )
    (fixture / "base.yaml").write_text(
        "services:\n  app:\n" + extends(deps[0]) + "  auxiliary:\n" + extends(deps[10])
    )
    (fixture / "override.yaml").write_text(
        "services:\n  app:\n    environment: {PRIORITY: overlay}\n"
    )
    prefix = (
        "--project-name",
        "synthetic",
        "--project-directory",
        str(fixture),
        "--env-file",
        str(fixture / "env"),
        "-f",
        str(fixture / "base.yaml"),
        "-f",
        str(fixture / "override.yaml"),
    )
    command = (*prefix, "config", "--format", "json")
    reference = subprocess.run(
        [str(binary), *command],
        cwd=fixture,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LC_ALL": "C.UTF-8",
            "DOCKER_HOST": f"unix://{tmp_path}/no-daemon.sock",
            "DOCKER_CONFIG": "/nonexistent",
        },
        capture_output=True,
        check=True,
        timeout=10,
    )
    trust = module("release_preflight_trust")
    snapshot = module("release_preflight_snapshot")
    active = tmp_path / "active.json"
    active.write_text("{}")
    approved = tmp_path / "inventory.json"
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)

    def record(path: Path) -> dict[str, str]:
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def pin(path: Path):
        info = path.stat()
        return trust.FilePin(path, record(path)["sha256"], info.st_mode & 0o777, info.st_uid)

    inventory = {
        "version": 2,
        "active_release_sha256": record(active)["sha256"],
        "compose_files": [record(fixture / name) for name in ("base.yaml", "override.yaml")],
        "compose_dependencies": [record(dep) for dep in deps],
        "env_file": record(fixture / "env"),
    }
    approved.write_text(json.dumps(inventory))
    approved.chmod(0o600)
    runner = renderer()
    with snapshot.capture_isolated_inputs(
        inventory,
        inventory_pin=pin(approved),
        active_pin=pin(active),
        compose_pin=pin(binary),
        scratch=scratch,
        limits=trust.InputLimits(65536, 2048, 32, 131072),
    ) as frozen:
        assert frozen.compose_files == (fixture / "base.yaml", fixture / "override.yaml")
        assert frozen.env_file == fixture / "env"
        hidden = tmp_path / "hidden-original"
        fixture.rename(hidden)
        try:
            result = runner.run_isolated_compose(frozen.root, command, max_output_bytes=32768)
            outside_env = tmp_path / "outside.env"
            outside_env.write_text("VALUE=host-only-synthetic\n")
            outside_command = (*command[:5], str(outside_env), *command[6:])
            with pytest.raises(runner.PreflightInputError, match="^renderer_failed$"):
                runner.run_isolated_compose(frozen.root, outside_command, max_output_bytes=32768)
            with pytest.raises(runner.PreflightInputError, match="renderer_output_limit"):
                runner.run_isolated_compose(
                    frozen.root, (*prefix, "up", "--help"), max_output_bytes=16
                )
        finally:
            hidden.rename(fixture)
    assert not list(scratch.iterdir())
    model = json.loads(result)
    assert model == json.loads(reference.stdout)
    assert model["name"] == "synthetic"
    for name, priority in (("app", "overlay"), ("auxiliary", "inherited")):
        service = model["services"][name]
        assert service["environment"] == {"VALUE": "synthetic", "PRIORITY": priority}
        assert service["build"]["context"] == str(fixture / "build")
        assert service["volumes"][0]["source"] == str(fixture / "data")
