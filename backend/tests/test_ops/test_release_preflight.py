"""Run the real CLI with real synthetic Git and an argv-strict fake Docker."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "ops/release_preflight.py"
SERVICES = ("backend", "worker", "frontend")
PG_OPTIONS = (
    "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000 -c timezone=UTC"
)
PG_COMMAND = (
    'exec psql -X --no-password -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
    "--set=ON_ERROR_STOP=1 --no-align --tuples-only "
    '--command="SELECT version_num FROM alembic_version"'
)
CANARY = "private-canary-must-not-appear"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Scenario:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.chmod(0o700)
        self.repo = root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.write("backend/app/main.py", "original")
        self.write("frontend/src/App.tsx", "original")
        self.write("docs/readme.md", "original")
        self.write("backend/migrations/versions/base.py", "revision='base'\ndown_revision=None\n")
        self.base = self.commit()
        self.candidate = self.advance("docs/readme.md", "new docs")
        self.bin = root / "bin"
        self.bin.mkdir()
        self.responses_file = root / "responses.json"
        self.journal = root / "argv.jsonl"
        docker = self.bin / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            "import json,sys,time\nfrom pathlib import Path\n"
            f"with Path({str(self.journal)!r}).open('a') as out:\n"
            " out.write(json.dumps(sys.argv[1:])+'\\n')\n"
            f"responses=json.loads(Path({str(self.responses_file)!r}).read_text())\n"
            "response=responses.get(json.dumps(sys.argv[1:]))\n"
            "if response is None: sys.exit(99)\n"
            "time.sleep(response.get('sleep',0))\n"
            "sys.stdout.write(response.get('stdout',''))\n"
            "sys.stderr.write(response.get('stderr',''))\n"
            "sys.exit(response.get('code',0))\n"
        )
        docker.chmod(0o700)
        self.active_file = root / "active.json"
        self.inventory_file = root / "inventory.json"
        self.compose_files = [root / "compose.yaml", root / "compose.release.yaml"]
        for file in self.compose_files:
            file.write_text("services: {}\n")
        self.env_file = root / ".env"
        self.env_file.write_text(f"SYNTHETIC_SECRET={CANARY}\n")
        self.ids = {name: str(index) * 64 for index, name in enumerate(SERVICES, start=1)}
        self.images = {
            name: "sha256:" + char * 64 for name, char in zip(SERVICES, "abc", strict=True)
        }
        self.pg_id = "4" * 64
        self.compose = [
            "compose",
            "--project-name",
            "synthetic",
            "--env-file",
            str(self.env_file),
        ]
        for file in self.compose_files:
            self.compose.extend(["-f", str(file)])
        self.exec = ["exec", "--env", PG_OPTIONS, self.pg_id, "sh", "-c", PG_COMMAND]
        self.responses: dict[str, dict[str, Any]] = {}
        config = {
            "name": "synthetic",
            "services": {
                **{name: {"image": f"local/synthetic:{name}"} for name in SERVICES},
                "postgres": {"image": "postgres:16"},
            },
            "secrets": {"synthetic": CANARY},
        }
        self.respond(self.compose + ["config", "--format", "json"], config)
        self.respond(
            self.compose + ["up", "--help"], "--no-start\n--no-deps\n--no-build\n", raw=True
        )
        for service in (*SERVICES, "postgres"):
            container_id = self.pg_id if service == "postgres" else self.ids[service]
            self.respond(self.compose + ["ps", "--all", "--quiet", service], container_id, raw=True)
            labels = {
                "com.docker.compose.project": "synthetic",
                "com.docker.compose.service": service,
                "org.opencontainers.image.revision": self.base,
            }
            self.respond(
                ["inspect", container_id],
                [
                    {
                        "Id": container_id,
                        "Image": self.images.get(service, "sha256:" + "d" * 64),
                        "State": {"Running": True, "Restarting": False, "Status": "running"},
                        "Config": {
                            "Image": f"local/synthetic:{service}",
                            "Labels": labels,
                            "Env": [
                                "POSTGRES_USER=synthetic",
                                "POSTGRES_DB=synthetic",
                                f"SECRET={CANARY}",
                            ],
                        },
                    }
                ],
            )
            if service in self.images:
                self.respond(
                    ["inspect", self.images[service]],
                    [{"Id": self.images[service], "Config": {"Labels": labels}}],
                )
        self.respond(self.exec, "base\n", raw=True)
        self.active = {
            "release_status": "verified-live",
            "service_revisions": dict.fromkeys(SERVICES, self.base),
            "application_images": {name: {"id": self.images[name]} for name in SERVICES},
            "compose_override": str(self.compose_files[-1]),
            "git_tip": self.candidate,
        }
        self.inventory = {
            "version": 1,
            "project": "synthetic",
            "active_release_sha256": "",
            "compose_files": [
                {"path": str(file), "sha256": digest(file)} for file in self.compose_files
            ],
            "env_file": {"path": str(self.env_file), "sha256": digest(self.env_file)},
            "services": {
                name: {
                    "container_id": self.ids[name],
                    "image_id": self.images[name],
                    "revision": self.base,
                }
                for name in SERVICES
            },
            "postgres": {
                "service": "postgres",
                "container_id": self.pg_id,
                "database": "synthetic",
                "role": "synthetic",
            },
        }
        self.approve()

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    def write(self, name: str, content: str) -> None:
        file = self.repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)

    def commit(self) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic")
        return self.git("rev-parse", "HEAD")

    def advance(self, name: str, content: str) -> str:
        self.write(name, content)
        self.candidate = self.commit()
        return self.candidate

    def respond(self, argv: list[str], value: Any, *, raw: bool = False) -> None:
        self.responses[json.dumps(argv)] = {"stdout": value if raw else json.dumps(value)}

    def observation(self, container_id: str) -> Any:
        return json.loads(self.responses[json.dumps(["inspect", container_id])]["stdout"])[0]

    def approve(self) -> None:
        self.active_file.write_text(json.dumps(self.active))
        self.inventory["active_release_sha256"] = digest(self.active_file)
        self.inventory_file.write_text(json.dumps(self.inventory))
        self.inventory_file.chmod(0o600)
        self.inventory_digest = digest(self.inventory_file)

    def args(self) -> list[str]:
        args = [
            "--check",
            "--repository",
            str(self.repo),
            "--candidate",
            self.candidate,
            "--active-release",
            str(self.active_file),
            "--approved-inventory",
            str(self.inventory_file),
            "--inventory-sha256",
            self.inventory_digest,
            "--project",
            "synthetic",
            "--env-file",
            str(self.env_file),
            "--postgres-service",
            "postgres",
        ]
        for file in self.compose_files:
            args.extend(["--compose-file", str(file)])
        return args

    def run(
        self, extra: tuple[str, ...] = (), *, optimized: bool = False, args: list[str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.responses_file.write_text(json.dumps(self.responses))
        env = {
            **os.environ,
            "PATH": str(self.bin) + ":/usr/bin:/bin",
            "GIT_DIR": "/must-not-be-used",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.pager",
            "GIT_CONFIG_VALUE_0": CANARY,
            "SECRET_ENV": CANARY,
        }
        return subprocess.run(
            [
                sys.executable,
                "-B",
                *(["-O"] if optimized else []),
                str(SCRIPT),
                *(self.args() if args is None else args),
                *extra,
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        if not self.journal.exists():
            return []
        return [json.loads(line) for line in self.journal.read_text().splitlines()]


@pytest.fixture
def scenario(tmp_path: Path) -> Scenario:
    return Scenario(tmp_path)


def report(result: subprocess.CompletedProcess[str], action: str) -> dict[str, Any]:
    assert result.returncode == (2 if action == "blocked" else 0), result.stderr + result.stdout
    value = json.loads(result.stdout)
    assert value["action"] == action
    assert value["authorized"] is False
    assert value["production_ready"] is False
    assert value["content_provenance_verified"] is False
    assert value["external_configuration_reviewed"] is False
    assert CANARY not in result.stdout + result.stderr
    assert result.stderr == ""
    return value


@pytest.mark.parametrize("action", ["no_rollout", "app_only", "migration_then_app"])
def test_check_cli_uses_only_read_allowlist(scenario: Scenario, action: str) -> None:
    if action == "app_only":
        scenario.advance("backend/app/main.py", "new runtime")
    elif action == "migration_then_app":
        scenario.advance(
            "backend/migrations/versions/head.py", "revision='head'\ndown_revision='base'\n"
        )
    result = report(scenario.run(), action)
    assert result["candidate"] == scenario.candidate
    assert result["service_revisions"] == dict.fromkeys(SERVICES, scenario.base)
    assert result["image_ids"] == scenario.images
    assert result["pending_migrations"] == (["head"] if action == "migration_then_app" else [])
    calls = scenario.calls()
    assert scenario.exec in calls
    assert all(json.dumps(call) in scenario.responses for call in calls)
    assert not any(
        token in {"create", "stop", "start", "rm", "build", "restart"} for c in calls for token in c
    )


def test_candidate_reads_git_not_dirty_worktree(scenario: Scenario) -> None:
    scenario.write("backend/migrations/versions/base.py", "invalid not committed Python")
    report(scenario.run(), "no_rollout")


def test_already_migrated_schema_requires_app_without_backfill(scenario: Scenario) -> None:
    scenario.advance(
        "backend/migrations/versions/head.py", "revision='head'\ndown_revision='base'\n"
    )
    scenario.respond(scenario.exec, "head\n", raw=True)
    assert report(scenario.run(), "app_only")["pending_migrations"] == []


def test_editing_existing_migration_blocks(scenario: Scenario) -> None:
    scenario.advance(
        "backend/migrations/versions/base.py", "revision='base'\ndown_revision=None\n#edit"
    )
    report(scenario.run(), "blocked")


@pytest.mark.parametrize("kind", ["symlink", "gitlink", "missing_commit", "divergent", "older"])
def test_git_modes_and_ancestry_are_checked(scenario: Scenario, kind: str) -> None:
    if kind == "symlink":
        file = scenario.repo / "docs/readme.md"
        file.unlink()
        file.symlink_to("/outside")
        scenario.candidate = scenario.commit()
    elif kind == "gitlink":
        scenario.git("update-index", "--add", "--cacheinfo", f"160000,{scenario.base},docs/module")
        scenario.git("commit", "-qm", "synthetic gitlink")
        scenario.candidate = scenario.git("rev-parse", "HEAD")
    elif kind == "missing_commit":
        scenario.candidate = "f" * 40
    else:
        scenario.active["service_revisions"]["frontend"] = scenario.candidate
        scenario.inventory["services"]["frontend"]["revision"] = scenario.candidate
        scenario.approve()
        if kind == "older":
            scenario.candidate = scenario.base
        else:
            scenario.git("checkout", "-q", "--detach", scenario.base)
            scenario.advance("docs/branch.md", "divergent")
    report(scenario.run(), "blocked")


@pytest.mark.parametrize("field", ["Id", "project", "service", "running", "database", "role"])
def test_schema_read_targets_inspected_pg_id_readonly(scenario: Scenario, field: str) -> None:
    observed = scenario.observation(scenario.pg_id)
    if field == "Id":
        observed["Id"] = "9" * 64
    elif field in {"project", "service"}:
        observed["Config"]["Labels"][f"com.docker.compose.{field}"] = "foreign"
    elif field == "running":
        observed["State"]["Running"] = False
    else:
        observed["Config"]["Env"][0 if field == "role" else 1] += "_foreign"
    scenario.respond(["inspect", scenario.pg_id], [observed])
    report(scenario.run(), "blocked")
    assert scenario.exec not in scenario.calls()


@pytest.mark.parametrize("field", ["image", "revision", "project", "service", "running", "two_ps"])
def test_metadata_and_running_image_drift_blocks(scenario: Scenario, field: str) -> None:
    observed = scenario.observation(scenario.ids["backend"])
    if field == "image":
        observed["Image"] = "sha256:" + "f" * 64
    elif field == "revision":
        observed["Config"]["Labels"]["org.opencontainers.image.revision"] = "f" * 40
    elif field in {"project", "service"}:
        observed["Config"]["Labels"][f"com.docker.compose.{field}"] = "foreign"
    elif field == "running":
        observed["State"]["Running"] = False
    else:
        scenario.respond(
            scenario.compose + ["ps", "--all", "--quiet", "backend"],
            scenario.ids["backend"] + "\n" + "9" * 64,
            raw=True,
        )
    scenario.respond(["inspect", scenario.ids["backend"]], [observed])
    report(scenario.run(), "blocked")


@pytest.mark.parametrize(
    "kind",
    ["digest", "mode", "parent_mode", "symlink", "extra_key", "missing_key", "duplicate_key"],
)
def test_unapproved_or_changed_inventory_blocks_before_tools(scenario: Scenario, kind: str) -> None:
    if kind == "digest":
        scenario.inventory_digest = "f" * 64
    elif kind == "mode":
        scenario.inventory_file.chmod(0o644)
    elif kind == "parent_mode":
        scenario.root.chmod(0o755)
    elif kind == "symlink":
        original = scenario.root / "inventory-original.json"
        scenario.inventory_file.rename(original)
        scenario.inventory_file.symlink_to(original)
    elif kind == "extra_key":
        scenario.inventory["extra"] = CANARY
        scenario.approve()
    elif kind == "missing_key":
        del scenario.inventory["postgres"]
        scenario.approve()
    else:
        text = scenario.inventory_file.read_text()
        scenario.inventory_file.write_text(text[:-1] + ',"version":1}')
        scenario.inventory_digest = digest(scenario.inventory_file)
    report(scenario.run(), "blocked")
    assert scenario.calls() == []


@pytest.mark.parametrize("kind", ["order", "override", "compose_hash", "env_hash", "active_hash"])
def test_compose_role_and_target_are_inventory_bound(scenario: Scenario, kind: str) -> None:
    if kind == "order":
        scenario.compose_files.reverse()
    elif kind == "override":
        scenario.active["compose_override"] = str(scenario.compose_files[0])
        scenario.approve()
    elif kind == "compose_hash":
        scenario.compose_files[0].write_text("changed")
    elif kind == "env_hash":
        scenario.env_file.write_text("changed")
    else:
        scenario.active_file.write_text("{}")
    report(scenario.run(), "blocked")
    assert scenario.calls() == []


@pytest.mark.parametrize("extra", [("--apply",), ("--sql", CANARY), ("--cand", CANARY)])
def test_no_apply_and_no_arbitrary_sql(scenario: Scenario, extra: tuple[str, ...]) -> None:
    report(scenario.run(extra), "blocked")
    assert scenario.calls() == []


def test_help_is_local_and_explains_non_authorization(scenario: Scenario) -> None:
    result = scenario.run(args=["--help"])
    assert result.returncode == 0
    assert "not authorization" in result.stdout
    assert scenario.calls() == []


@pytest.mark.parametrize(
    "kind", ["nonzero", "invalid_json", "duplicate_json", "incomplete", "timeout"]
)
def test_secrets_timeouts_and_invalid_json_are_redacted(scenario: Scenario, kind: str) -> None:
    key = json.dumps(scenario.compose + ["config", "--format", "json"])
    if kind == "nonzero":
        scenario.responses[key] = {"code": 1, "stdout": CANARY, "stderr": CANARY}
    elif kind == "timeout":
        scenario.responses[key] = {"sleep": 11, "stderr": CANARY}
    else:
        scenario.responses[key] = {
            "stdout": {
                "invalid_json": CANARY,
                "duplicate_json": '{"name":"synthetic","name":"' + CANARY + '"}',
                "incomplete": "{}",
            }[kind]
        }
    value = report(scenario.run(), "blocked")
    assert value["candidate"] is None
    assert value["schema_from"] is None
    assert value["service_revisions"] is None
    assert value["reason_codes"]


def test_check_works_with_python_optimized(scenario: Scenario) -> None:
    report(scenario.run(optimized=True), "no_rollout")
    scenario.inventory_digest = "f" * 64
    report(scenario.run(optimized=True), "blocked")


def test_migration_dependencies_cannot_be_misclassified_as_linear(scenario: Scenario) -> None:
    scenario.advance(
        "backend/migrations/versions/head.py",
        "revision='head'\ndown_revision='base'\ndepends_on='another_branch'\n",
    )
    report(scenario.run(), "blocked")
    assert scenario.calls() == []


def test_nested_migration_cannot_disappear_from_candidate_graph(scenario: Scenario) -> None:
    scenario.advance(
        "backend/migrations/versions/nested/head.py",
        "revision='head'\ndown_revision='base'\n",
    )
    report(scenario.run(), "blocked")
    assert scenario.calls() == []


@pytest.mark.parametrize("field", ["release_status", "service_revisions", "application_images"])
def test_missing_active_fields_never_fall_back_to_git_tip(scenario: Scenario, field: str) -> None:
    del scenario.active[field]
    scenario.approve()
    report(scenario.run(), "blocked")
    assert scenario.calls() == []


def test_mixed_service_revisions_are_observed_independently(scenario: Scenario) -> None:
    scenario.advance("backend/app/main.py", "new backend")
    scenario.active["service_revisions"]["frontend"] = scenario.candidate
    scenario.inventory["services"]["frontend"]["revision"] = scenario.candidate
    for identifier in (scenario.ids["frontend"], scenario.images["frontend"]):
        observed = scenario.observation(identifier)
        observed["Config"]["Labels"]["org.opencontainers.image.revision"] = scenario.candidate
        scenario.respond(["inspect", identifier], [observed])
    scenario.approve()
    value = report(scenario.run(), "app_only")
    assert value["service_revisions"]["backend"] == scenario.base
    assert value["service_revisions"]["frontend"] == scenario.candidate


def test_cli_without_python_B_never_writes_bytecode(scenario: Scenario) -> None:
    scripts = scenario.root / "scripts"
    scripts.mkdir()
    for name in ("release_preflight.py", "release_preflight_policy.py"):
        shutil.copyfile(SCRIPT.parent / name, scripts / name)
    result = subprocess.run(
        [sys.executable, str(scripts / "release_preflight.py"), "--help"],
        env={"PATH": "/usr/bin:/bin", "HOME": str(scenario.root)},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert not (scripts / "__pycache__").exists()
    assert scenario.calls() == []
