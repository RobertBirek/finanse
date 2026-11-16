"""Read-only checks for an explicitly selected developer Python; never imports app."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tomllib
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

TOOLS = {"test": "pytest", "lint": "ruff", "typecheck": "mypy"}


def validate_environment(
    root: Path, check: str, installed: Mapping[str, str], python_version: str
) -> None:
    """Validate direct metadata, pins and the selected tool, without running it."""
    if check not in TOOLS:
        raise ValueError("Unknown check")
    project = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]
    if not SpecifierSet(project["requires-python"]).contains(python_version):
        raise ValueError(
            f"Python {python_version} does not satisfy project requires-python"
        )
    requirements = [Requirement(value) for value in project["dependencies"]]
    dev = [Requirement(value) for value in project["optional-dependencies"]["dev"]]
    tool = [value for value in dev if canonicalize_name(value.name) == TOOLS[check]]
    if len(tool) != 1:
        raise ValueError(f"Missing or ambiguous check requirement: {TOOLS[check]}")
    requirements.extend(tool)
    for line in (root / "backend/requirements.txt").read_text().splitlines():
        value = line.split(" #", 1)[0].strip()
        if value and not value.startswith("#"):
            requirement = Requirement(value)
            if requirement.url:
                raise ValueError("URL dependencies are not supported by preflight")
            requirements.append(requirement)
    versions = {canonicalize_name(name): version for name, version in installed.items()}
    environment = {key: str(value) for key, value in default_environment().items()}
    environment.update(
        python_full_version=python_version,
        python_version=".".join(python_version.split(".")[:2]),
    )
    for requirement in requirements:
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        version = versions.get(canonicalize_name(requirement.name))
        if version is None or not requirement.specifier.contains(version):
            raise ValueError(
                f"{requirement.name}: installed {version or 'MISSING'}, requires {requirement.specifier}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", choices=TOOLS, required=True)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        if not args.root.is_absolute() or root != Path(__file__).resolve().parents[1]:
            raise ValueError(
                "root must be the absolute repository root containing this helper"
            )
        if not (root / "frontend/package.json").is_file():
            raise ValueError("Incomplete repository layout")
        versions = {
            distribution.metadata["Name"]: distribution.version
            for distribution in metadata.distributions()
            if distribution.metadata["Name"]
        }
        validate_environment(root, args.check, versions, platform.python_version())
    except (ValueError, KeyError, OSError) as exc:
        print(f"Developer preflight refused: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps({"root": str(root), "python": sys.executable, "check": args.check})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
