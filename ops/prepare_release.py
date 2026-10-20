#!/usr/bin/env python3
"""Prepare immutable application images/Compose overrides; never apply them.

The operator builds the emitted Dockerfiles and explicitly applies the override
alongside existing production Compose files. No secrets, DB or proxy settings
are copied into the release metadata. Requires Docker Compose !override support.
"""

import argparse
import io
import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

IMAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9./_-]*:[a-zA-Z0-9_.-]+")


def git(repository: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repository), *args])


def prepare_release(
    repository: Path,
    revision: str,
    runtime_revision: str,
    output: Path,
    frontend_dist: Path,
    backend_runtime: str,
    worker_runtime: str,
    frontend_runtime: str,
) -> dict[str, str]:
    runtimes = {
        "backend": backend_runtime,
        "worker": worker_runtime,
        "frontend": frontend_runtime,
    }
    if not all(IMAGE_PATTERN.fullmatch(value) for value in runtimes.values()):
        raise ValueError("Runtime images must be explicit local image:tag references")
    sha = (
        git(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")
        .decode()
        .strip()
    )
    base = (
        git(repository, "rev-parse", "--verify", f"{runtime_revision}^{{commit}}")
        .decode()
        .strip()
    )
    if git(repository, "show", f"{sha}:backend/requirements.txt") != git(
        repository, "show", f"{base}:backend/requirements.txt"
    ):
        raise ValueError(
            "Runtime dependencies changed: build and verify a new runtime first"
        )
    if not (frontend_dist / "index.html").is_file():
        raise ValueError("A verified production frontend build is required")
    if output.exists():
        raise ValueError("Release output must be a new directory")
    output.mkdir(mode=0o700)
    archive = git(
        repository, "archive", "--format=tar", sha, "backend", "frontend/nginx.conf"
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(output / "source", filter="data")
    shutil.copytree(frontend_dist, output / "frontend-dist")
    images = {service: f"local/finanse-{service}:{sha}" for service in runtimes}
    for service in ("backend", "worker"):
        (output / f"Dockerfile.{service}").write_text(
            f"FROM {runtimes[service]}\n"
            f'LABEL org.opencontainers.image.revision="{sha}"\n'
            "ENV PYTHONDONTWRITEBYTECODE=1\n"
            "WORKDIR /app\n"
            "RUN rm -rf /app/app /app/migrations /app/scripts /app/tests\n"
            "COPY source/backend/ /app/\n"
        )
    (output / "Dockerfile.frontend").write_text(
        f"FROM {frontend_runtime}\n"
        f'LABEL org.opencontainers.image.revision="{sha}"\n'
        "RUN rm -rf /usr/share/nginx/html/*\n"
        "COPY frontend-dist/ /usr/share/nginx/html/\n"
        "COPY source/frontend/nginx.conf /etc/nginx/conf.d/default.conf\n"
    )
    lines = [
        "# Apply with the original Compose files; --no-deps protects data services.",
        "services:",
    ]
    for service in runtimes:
        lines.extend(
            [
                f"  {service}:",
                f"    image: {images[service]}",
                "    build:",
                f"      context: {json.dumps(str(output.resolve()))}",
                f"      dockerfile: Dockerfile.{service}",
            ]
        )
        if service != "frontend":
            lines.extend(
                [
                    "    volumes: !override",
                    "      - type: bind",
                    "        source: /docker/finanse/data/uploads",
                    "        target: /app/uploads",
                ]
            )
    (output / "compose.release.yaml").write_text("\n".join(lines) + "\n")
    metadata = {"revision": sha, "runtime_revision": base, **images}
    (output / "release.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frontend-dist", type=Path, required=True)
    for service in ("backend", "worker", "frontend"):
        parser.add_argument(f"--{service}-runtime", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_release(**vars(args)), indent=2))


if __name__ == "__main__":
    main()
