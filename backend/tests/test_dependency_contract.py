"""Offline dependency and developer-command contracts; no service fixtures."""

from __future__ import annotations

import importlib.util
import json
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
