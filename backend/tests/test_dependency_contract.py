"""Offline dependency and developer-command contracts; no service fixtures."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = {"openai": "2.54.0", "pytest": "9.1.1", "ruff": "0.17.1", "mypy": "2.4.0"}
METADATA = """\
[project]
requires-python = ">=3.12"
dependencies = ["openai>=2.54.0"]
[project.optional-dependencies]
dev = ["pytest>=9.1.1,<10", "ruff>=0.17.1", "mypy>=2.4.0"]
"""


def load_preflight() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "dev_environment", ROOT / "ops/dev_environment.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "synthetic repo with spaces"
    (root / "backend").mkdir(parents=True)
    (root / "backend/pyproject.toml").write_text(METADATA)
    (root / "backend/requirements.txt").write_text("openai==2.54.0\n")
    return root


def test_sdk_floor_matches_existing_pin() -> None:
    project = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]
    sdk = next(
        Requirement(value)
        for value in project["dependencies"]
        if Requirement(value).name == "openai"
    )
    assert not sdk.specifier.contains("1.51.2")
    assert sdk.specifier.contains("2.54.0")
    assert "openai==2.54.0" in (ROOT / "backend/requirements.txt").read_text().splitlines()


@pytest.mark.parametrize("check", ["test", "lint", "typecheck"])
def test_valid_environment(project: Path, check: str) -> None:
    load_preflight().validate_environment(project, check, VERSIONS, "3.12.3")


@pytest.mark.parametrize(
    ("check", "package", "version"),
    [
        ("test", "openai", None),
        ("test", "openai", "1.51.2"),
        ("test", "pytest", "8.3.3"),
        ("lint", "ruff", "0.16.2"),
        ("typecheck", "mypy", "2.3.0"),
    ],
)
def test_environment_refuses_missing_or_stale_dependency(
    project: Path, check: str, package: str, version: str | None
) -> None:
    versions = dict(VERSIONS)
    if version is None:
        versions.pop(package)
    else:
        versions[package] = version
    with pytest.raises(ValueError, match=package):
        load_preflight().validate_environment(project, check, versions, "3.12.3")


def test_environment_refuses_unknown_check_and_python(project: Path) -> None:
    helper = load_preflight()
    with pytest.raises(ValueError, match="check"):
        helper.validate_environment(project, "deploy", VERSIONS, "3.12.3")
    with pytest.raises(ValueError, match="Python"):
        helper.validate_environment(project, "test", VERSIONS, "3.11.9")


def test_requirement_pins_markers_and_names(project: Path) -> None:
    requirements = project / "backend/requirements.txt"
    requirements.write_text(
        '# comment\nOpenAI==2.54.0 # pin\nabsent-package==1; python_version < "3.0"\n'
    )
    helper = load_preflight()
    helper.validate_environment(project, "test", VERSIONS, "3.12.3")
    requirements.write_text("openai==2.55.0\n")
    with pytest.raises(ValueError, match="openai"):
        helper.validate_environment(project, "test", VERSIONS, "3.12.3")
    requirements.write_text("-r other.txt\n")
    with pytest.raises(ValueError):
        helper.validate_environment(project, "test", VERSIONS, "3.12.3")


def test_preflight_cli_root_and_no_application_import(project: Path) -> None:
    (project / "ops").mkdir()
    script = project / "ops/dev_environment.py"
    shutil.copyfile(ROOT / "ops/dev_environment.py", script)
    (project / "frontend").mkdir()
    (project / "frontend/package.json").write_text("{}\n")
    (project / "backend/app").mkdir()
    (project / "backend/app/__init__.py").write_text('raise AssertionError("app imported")\n')
    (project / ".env").write_text("INVALID ENV CONTENT, NOT PYTHON\n")
    # Success uses only packages present in backend requirements CI, never Ruff/mypy.
    (project / "backend/pyproject.toml").write_text(
        METADATA.replace('dependencies = ["openai>=2.54.0"]', "dependencies = []")
    )
    (project / "backend/requirements.txt").write_text("")
    command = [sys.executable, "-I", "-B", str(script), "--check", "test", "--root"]
    result = subprocess.run(command + [str(project)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["root"] == str(project.resolve())
    assert json.loads(result.stdout)["check"] == "test"
    result = subprocess.run(
        command + [str(project.parent)], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    (project / "backend/requirements.txt").unlink()
    result = subprocess.run(command + [str(project)], capture_output=True, text=True, check=False)
    assert result.returncode != 0


def command_block(check: str) -> str:
    prompt = (ROOT / f".opencode/command/{check}.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", prompt, re.DOTALL)
    assert len(blocks) == 1, "Each command needs one complete Bash block"
    assert "/opt/finanse" not in blocks[0]
    assert "!" not in prompt, "No permission-bypassing OpenCode shell substitution"
    return blocks[0]


def executable(path: Path, body: str) -> Path:
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o700)
    return path


@pytest.fixture
def command_project(project: Path) -> Path:
    (project / "bin").mkdir()
    (project / "ops").mkdir()
    (project / "frontend").mkdir()
    (project / "backend/tests").mkdir()
    (project / "frontend/package.json").write_text("{}\n")
    shutil.copyfile(ROOT / "ops/dev_environment.py", project / "ops/dev_environment.py")
    (project / "backend/pyproject.toml").write_text(
        METADATA.replace('dependencies = ["openai>=2.54.0"]', "dependencies = []")
        + "\n[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\naddopts = "-m \'not proxy\'"\n'
        'markers = ["integration", "migration", "proxy"]\n'
    )
    (project / "backend/requirements.txt").write_text("")
    executable(
        project / "python",
        f"""\
import json, os, sys
from pathlib import Path
root = Path({str(project)!r})
args = sys.argv[1:]
with (root / "python.jsonl").open("a") as stream:
    stream.write(json.dumps(args) + "\\n")
preflight = len(args) > 2 and args[2].endswith("/ops/dev_environment.py")
failure = root / ("fail-preflight" if preflight else "fail-backend")
if failure.exists():
    raise SystemExit(17)
if (root / "real-python").exists():
    os.execv({sys.executable!r}, [{sys.executable!r}, *args])
""",
    )
    executable(
        project / "bin/npm",
        f"""\
import json, os, sys
from pathlib import Path
Path({str(project / "npm.json")!r}).write_text(
    json.dumps({{"cwd": os.getcwd(), "args": sys.argv[1:]}})
)
""",
    )
    executable(
        project / "bin/sudo",
        f"""\
import json, os, sys
from pathlib import Path
root = Path({str(project)!r})
a = sys.argv[1:]
(root / "sudo.json").write_text(json.dumps(a))
assert a[:5] == ["-n", "--", "unshare", "--net", "setpriv"], a
assert a[5:11] == [
    "--reuid", str(os.getuid()), "--regid", str(os.getgid()),
    "--init-groups", "--no-new-privs"
], a
assert a[11:13] == ["env", "-i"], a
if (root / "deny-namespace").exists():
    raise SystemExit(23)
os.execv("/usr/bin/env", a[11:])
""",
    )
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(project),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@invalid",
            "commit",
            "-qm",
            "synthetic collection checkout",
        ],
        check=True,
    )
    return project


def run_command(
    project: Path, check: str, overrides: dict[str, str | None] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{project / 'bin'}:/usr/bin:/bin",
        "HOME": str(project),
        "TMPDIR": str(project.parent),
        "ADVISOR_DEV_PYTHON": str(project / "python"),
        "HOST_ONLY_SECRET": "synthetic-must-not-reach-collection",
        "PYTHONPATH": "/this/path/must/not/reach/python",
    }
    for key, value in (overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        ["/bin/bash", "-c", command_block(check)],
        cwd=project / "backend/tests",
        env=env,
        capture_output=True,
        text=True,
        timeout=12,
        check=False,
    )


@pytest.mark.parametrize("check", ["test", "lint", "typecheck"])
@pytest.mark.parametrize("python", [None, "", "relative/python", "/nonexistent/python"])
def test_command_requires_absolute_explicit_python(
    command_project: Path, check: str, python: str | None
) -> None:
    result = run_command(command_project, check, {"ADVISOR_DEV_PYTHON": python})
    assert result.returncode != 0
    assert not (command_project / "python.jsonl").exists()
    assert not (command_project / "npm.json").exists()


@pytest.mark.parametrize("check", ["test", "lint", "typecheck"])
@pytest.mark.parametrize("failure", ["fail-preflight", "fail-backend"])
def test_preflight_and_backend_failure_stop_frontend(
    command_project: Path, check: str, failure: str
) -> None:
    (command_project / failure).touch()
    result = run_command(command_project, check)
    assert result.returncode == 17, result.stdout + result.stderr
    assert not (command_project / "npm.json").exists()
    calls = (command_project / "python.jsonl").read_text().splitlines()
    assert len(calls) == (1 if failure == "fail-preflight" else 2)


@pytest.mark.parametrize("check", ["test", "lint", "typecheck"])
def test_git_environment_cannot_redirect_root(command_project: Path, check: str) -> None:
    foreign = command_project.parent / "foreign"
    subprocess.run(["git", "init", "-q", str(foreign)], check=True)
    (command_project / ".gitconfig").write_text(f"[core]\n worktree = {foreign}\n")
    result = run_command(
        command_project,
        check,
        {
            "GIT_DIR": str(foreign / ".git"),
            "GIT_COMMON_DIR": str(foreign / ".git"),
            "GIT_WORK_TREE": str(foreign),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": str(foreign),
            "GIT_CONFIG_SYSTEM": str(command_project / ".gitconfig"),
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [
        json.loads(line) for line in (command_project / "python.jsonl").read_text().splitlines()
    ]
    assert calls[0] == [
        "-I",
        "-B",
        str(command_project / "ops/dev_environment.py"),
        "--root",
        str(command_project),
        "--check",
        check,
    ]
    npm = json.loads((command_project / "npm.json").read_text())
    assert npm["cwd"] == str(command_project / "frontend")
    assert npm["args"] == (["test"] if check == "test" else ["run", check])
    # Inspect exact clean-environment argv and execute the same Git, not a replacement.
    block = command_block(check)
    assert "GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null" in block
    assert "env -i PATH=/usr/bin:/bin" in block
    if check == "test":
        args = calls[1]
        commit = subprocess.check_output(
            ["git", "-C", str(command_project), "rev-parse", "HEAD"], text=True
        ).strip()
        assert args[args.index("--commit") + 1] == commit


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (
            "lint",
            [
                "-I",
                "-B",
                "-m",
                "ruff",
                "check",
                "app",
                "tests",
                "ci_tools",
                "../ops/dev_environment.py",
            ],
        ),
        ("typecheck", ["-I", "-B", "-m", "mypy", "app", "ci_tools", "../ops/dev_environment.py"]),
    ],
)
def test_local_checks_keep_ci_tools_in_scope(
    command_project: Path, check: str, expected: list[str]
) -> None:
    result = run_command(command_project, check)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [
        json.loads(line) for line in (command_project / "python.jsonl").read_text().splitlines()
    ]
    assert calls[1] == expected


def test_collection_namespace_denied_stops_before_frontend(command_project: Path) -> None:
    (command_project / "deny-namespace").touch()
    result = run_command(command_project, "test")
    assert result.returncode == 23, result.stdout + result.stderr
    assert len((command_project / "python.jsonl").read_text().splitlines()) == 1
    assert not (command_project / "npm.json").exists()


def test_collection_real_runner_without_fixture_or_body(command_project: Path) -> None:
    shutil.copytree(ROOT / "backend/ci_tools", command_project / "backend/ci_tools")
    (command_project / "real-python").touch()
    (command_project / "backend/tests/conftest.py").write_text(
        """\
import os
from pathlib import Path
import pytest
assert "HOST_ONLY_SECRET" not in os.environ
assert "PYTHONPATH" not in os.environ
assert os.environ["TEST_DATABASE_URL"].endswith("@127.0.0.1:9/finanse_test")
assert os.environ["REDIS_URL"] == "redis://127.0.0.1:9/0"
assert os.environ["OPENAI_API_KEY"] == ""
assert os.environ["PYTHONNOUSERSITE"] == "1"
assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"
assert os.environ["GIT_CONFIG_GLOBAL"] == "/dev/null"
@pytest.fixture(autouse=True)
def danger():
    Path("FIXTURE_EXECUTED").touch()
"""
    )
    # Existing runner rejects empty groups: six ordinary, one legacy, one proxy.
    for filename, marker in [
        *((f"test_probe_{index}.py", "integration") for index in range(6)),
        ("test_legacy.py", "migration"),
        ("test_documents/test_proxy_upload.py", "proxy"),
    ]:
        path = command_project / "backend/tests" / filename
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            f"import pytest\nfrom pathlib import Path\n@pytest.mark.{marker}\n"
            'def test_probe():\n    Path("BODY_EXECUTED").touch()\n'
        )
    result = run_command(command_project, "test")
    manifests = list(command_project.parent.glob("advisor-checks.*/manifest.json"))
    logs = list(command_project.parent.glob("advisor-checks.*/collection/run.log"))
    assert result.returncode == 0, (
        result.stdout + result.stderr + "".join(path.read_text() for path in logs)
    )
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    commit = subprocess.check_output(
        ["git", "-C", str(command_project), "rev-parse", "HEAD"], text=True
    ).strip()
    assert manifest["commit"] == commit
    assert len(manifest["inventory"]) == 8
    assert len(manifest["groups"]) == 8
    assert all(len(nodes) == 1 for nodes in manifest["groups"].values())
    assert not (command_project / "backend/FIXTURE_EXECUTED").exists()
    assert not (command_project / "backend/BODY_EXECUTED").exists()
    assert json.loads((manifests[0].parent / "collection/process.json").read_text())["exit"] == 0
    assert (command_project / "npm.json").exists()
