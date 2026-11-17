"""Synthetic pinned tools with an exact argv boundary, never a daemon."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

OPS = Path(__file__).resolve().parents[3] / "ops"


def module(name: str) -> Any:
    if str(OPS) not in sys.path:
        sys.path.insert(0, str(OPS))
    return importlib.import_module(name)


class PinnedScenario:
    def __init__(self, root: Path) -> None:
        trust = module("release_preflight_trust")
        self.root = root
        root.chmod(0o700)
        self.repo = root / "repo"
        self.repo.mkdir(mode=0o700)
        self.bin = root / "bin"
        self.bin.mkdir(mode=0o700)
        self.journal = root / "calls.jsonl"
        self.responses_file = root / "responses.json"
        self.responses: dict[str, dict[str, Any]] = {}
        script = (
            f"#!{sys.executable}\n"
            "import json,os,sys,time\nfrom pathlib import Path\n"
            "role=Path(sys.argv[0]).name\n"
            f"with Path({str(self.journal)!r}).open('a') as f:\n"
            " f.write(json.dumps({'role':role,'argv':sys.argv[1:],'env':dict(os.environ)})+'\\n')\n"
            f"responses=json.loads(Path({str(self.responses_file)!r}).read_text())\n"
            "r=responses.get(json.dumps([role,*sys.argv[1:]]))\n"
            "if r is None: sys.exit(99)\n"
            "time.sleep(r.get('sleep',0))\n"
            "sys.stdout.write(r.get('stdout',''));sys.stderr.write(r.get('stderr',''))\n"
            "sys.exit(r.get('code',0))\n"
        )
        pins = {}
        for name in ("git", "docker", "compose"):
            path = self.bin / name
            path.write_text(script)
            path.chmod(0o700)
            pins[name] = trust.FilePin(
                path, hashlib.sha256(path.read_bytes()).hexdigest(), 0o700, os.geteuid()
            )
        self.tools = trust.Toolchain(
            **pins,
            postgres=trust.PgEndpoint(
                container_id="4" * 64,
                image_id="sha256:" + "d" * 64,
                uid=999,
                gid=999,
                env_executable="/usr/bin/env",
                psql_executable="/usr/lib/postgresql/16/bin/psql",
                socket_directory="/var/run/postgresql",
                port=5432,
                auth="peer",
            ),
            limits=trust.InputLimits(65536, 2048, 32, 131072),
        )
        self.inventory: dict[str, Any] = {
            "version": 1,
            "project": "synthetic",
            "services": {
                name: {
                    "container_id": str(i) * 64,
                    "image_id": "sha256:" + char * 64,
                    "revision": char * 40,
                }
                for i, (name, char) in enumerate(
                    zip(("backend", "worker", "frontend"), "abc", strict=True), 1
                )
            },
            "postgres": {
                "service": "postgres",
                "container_id": "4" * 64,
                "database": "synthetic_db",
                "role": "synthetic_finance",
            },
        }
        self.env_file = root / "env"
        self.env_file.write_text("SYNTHETIC_SECRET=private-canary\n")
        self.compose_file = root / "compose.yaml"
        self.compose_file.write_text("services: {}\n")
        self.compose_prefix = [
            "compose",
            "--project-name",
            "synthetic",
            "--project-directory",
            str(root),
            "--env-file",
            str(self.env_file),
            "-f",
            str(self.compose_file),
        ]
        self.git_prefix = [
            "git",
            "--no-pager",
            "--no-replace-objects",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.attributesFile=/dev/null",
            "-C",
            str(self.repo),
        ]
        self.pg_command = [
            "docker",
            "--host",
            "unix:///var/run/docker.sock",
            "exec",
            "--user",
            "999:999",
            "4" * 64,
            "/usr/bin/env",
            "-i",
            "HOME=/nonexistent",
            "PGPASSFILE=/dev/null",
            "PGCONNECT_TIMEOUT=5",
            "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC",
            "/usr/lib/postgresql/16/bin/psql",
            "-X",
            "--no-password",
            "--host",
            "/var/run/postgresql",
            "--port",
            "5432",
            "--username",
            "synthetic_finance",
            "--dbname",
            "synthetic_db",
            "--set=ON_ERROR_STOP=1",
            "--no-align",
            "--tuples-only",
            "--command",
            "SELECT version_num FROM alembic_version",
        ]
        self.pg_observation = {
            "Id": "4" * 64,
            "Image": "sha256:" + "d" * 64,
            "State": {"Running": True, "Restarting": False, "Status": "running"},
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "synthetic",
                    "com.docker.compose.service": "postgres",
                },
                "Env": [
                    "POSTGRES_USER=synthetic_finance",
                    "POSTGRES_DB=synthetic_db",
                    "PGHOST=other.invalid",
                    "PGSERVICE=foreign",
                    "PGPORT=6543",
                ],
            },
            "Mounts": [],
        }
        self.respond(self.pg_command, stdout="base\n")
        self.respond(
            ["docker", "--host", "unix:///var/run/docker.sock", "inspect", "4" * 64],
            stdout=json.dumps([self.pg_observation]),
        )
        self.respond(
            self.compose_prefix + ["ps", "--all", "--quiet", "postgres"], stdout="4" * 64 + "\n"
        )

    def respond(self, argv: list[str], **response: Any) -> None:
        self.responses[json.dumps(argv)] = response
        self.responses_file.write_text(json.dumps(self.responses))

    def runner(self) -> Any:
        trust = module("release_preflight_trust")
        runner = module("release_preflight_exec").ReadOnlyRunner(
            self.repo,
            self.tools,
            verifier=lambda pin: trust.verify_pinned_file(pin, owner_uid=pin.uid),
        )
        runner.bind(
            compose_files=(self.compose_file,),
            env_file=self.env_file,
            project_directory=self.root,
            project="synthetic",
            inventory=self.inventory,
        )
        return runner

    def calls(self) -> list[dict[str, Any]]:
        if not self.journal.exists():
            return []
        return [json.loads(line) for line in self.journal.read_text().splitlines()]
