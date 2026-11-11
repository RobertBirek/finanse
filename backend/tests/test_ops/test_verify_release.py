"""Import gate must verify exact built images without host secrets or services."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "ops/verify_release.py"
REV = "a" * 40
IDS = {"backend": "sha256:" + "b" * 64, "worker": "sha256:" + "c" * 64}


def load_gate():
    spec = importlib.util.spec_from_file_location("verify_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release(tmp_path):
    (tmp_path / "release.json").write_text(
        json.dumps(
            {
                "revision": REV,
                "backend": "local/test:backend",
                "worker": "local/test:worker",
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize("user", ["0:10001", "10001:0", "root", "alice:staff", "-1:1", "1:1\n", ""])
def test_root_named_or_invalid_user_fails_before_docker(release, monkeypatch, user):
    module = load_gate()

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid target user must not invoke Docker")

    monkeypatch.setattr(module.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="non-root.*UID:GID"):
        module.verify_release(release, backend_user=user, worker_user="10002:10002")


def fake_docker(
    *,
    wrong_label=False,
    fail_worker=False,
    timeout=False,
    foreign=False,
    stop_fails=False,
    remove_fails=False,
):
    calls = []
    containers = {}

    def run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["docker", "image", "inspect"]:
            service = args[3].rsplit(":", 1)[1]
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    [
                        {
                            "Id": IDS[service],
                            "Config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": "d" * 40
                                    if wrong_label
                                    else REV
                                }
                            },
                        }
                    ]
                ),
                "",
            )
        if args[:2] == ["docker", "create"]:
            service = "worker" if IDS["worker"] in args else "backend"
            name = args[args.index("--name") + 1]
            identity = ("e" if service == "backend" else "f") * 64
            containers[name] = {
                "Id": identity,
                "Name": "/" + name,
                "Image": IDS[service],
                "Config": {
                    "User": args[args.index("--user") + 1],
                    "Labels": {"advisor.release.probe": name},
                },
                "HostConfig": {"NetworkMode": "none", "PortBindings": {}},
                "Mounts": [],
                "State": {"Running": False, "ExitCode": 0},
            }
            return subprocess.CompletedProcess(args, 0, identity, "")
        if args[:2] == ["docker", "inspect"]:
            obj = containers.get(args[2])
            if obj is None:
                return subprocess.CompletedProcess(args, 1, "[]", "No such object: " + args[2])
            observed = json.loads(json.dumps(obj))
            if foreign:
                observed["Config"]["Labels"] = {}
            return subprocess.CompletedProcess(args, 0, json.dumps([observed]), "")
        if args[:2] == ["docker", "stop"]:
            if stop_fails:
                raise subprocess.CalledProcessError(1, args)
            obj = next(o for o in containers.values() if o["Id"] == args[-1])
            obj["State"]["Running"] = False
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["docker", "rm"]:
            assert len(args) == 3 and not args[2].startswith("-")
            if remove_fails:
                raise subprocess.CalledProcessError(1, args)
            name = next(n for n, o in containers.items() if o["Id"] == args[2])
            del containers[name]
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["docker", "start"]:
            obj = next(o for o in containers.values() if o["Id"] == args[-1])
            service = "worker" if obj["Image"] == IDS["worker"] else "backend"
            if timeout:
                obj["State"]["Running"] = True
            user = obj["Config"]["User"]
        elif args[:2] == ["docker", "run"]:  # legacy branch only for RED compatibility
            service = "worker" if IDS["worker"] in args else "backend"
            user = args[args.index("--user") + 1]
        else:
            pytest.fail(f"Unexpected Docker operation: {args[:2]}")
        if args[1] in {"start", "run"}:
            if timeout:
                raise subprocess.TimeoutExpired(args, 1)
            if fail_worker and service == "worker":
                raise subprocess.CalledProcessError(1, args, "", "synthetic confidential traceback")
            uid, gid = map(int, user.split(":"))
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "uid": uid,
                        "gid": gid,
                        "files_read": 3,
                        "module": "app.main" if service == "backend" else "app.worker",
                    }
                )
                + "\n",
                "",
            )

    return run, calls


def test_proof_is_for_exact_image_ids_and_explicit_runtime_users(release, monkeypatch):
    module = load_gate()
    run, calls = fake_docker()
    monkeypatch.setattr(module.subprocess, "run", run)
    proof = module.verify_release(release, backend_user="10001:10001", worker_user="20002:20002")
    assert proof["passed"] is True
    assert proof["revision"] == REV
    assert proof["services"]["backend"]["image_id"] == IDS["backend"]
    assert proof["services"]["worker"]["image_id"] == IDS["worker"]
    assert proof["services"]["worker"]["uid"] == 20002
    for args in [c for c in calls if c[:2] == ["docker", "create"]]:
        assert args[args.index("--network") + 1] == "none"
        assert args[args.index("--pull") + 1] == "never"
        assert args[args.index("--cap-drop") + 1] == "ALL"
        assert "--read-only" in args
        assert args[args.index("--security-opt") + 1] == "no-new-privileges"
        assert not set(args) & {
            "-v",
            "--volume",
            "--mount",
            "--env-file",
            "--env",
            "-e",
            "--privileged",
        }
        assert IDS["backend"] in args or IDS["worker"] in args


def test_probe_cleanup_never_uses_force_or_auto_remove(release, monkeypatch):
    module = load_gate()
    run, calls = fake_docker()
    monkeypatch.setattr(module.subprocess, "run", run)
    module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
    assert not any("-f" in call or "--force" in call or "--rm" in call for call in calls)
    assert any(call[:2] == ["docker", "create"] for call in calls)
    assert any(call[:2] == ["docker", "inspect"] for call in calls)


def test_revision_mismatch_fails_before_starting_probe(release, monkeypatch):
    module = load_gate()
    run, calls = fake_docker(wrong_label=True)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError, match="revision"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
    assert not any(c[:2] in [["docker", "run"], ["docker", "create"]] for c in calls)


@pytest.mark.parametrize("timeout", [False, True])
def test_failed_import_or_timeout_returns_no_pass_and_cleans_owned_probe(
    release, monkeypatch, timeout
):
    module = load_gate()
    run, calls = fake_docker(fail_worker=True, timeout=timeout)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="probe failed") as error:
        module.verify_release(
            release, backend_user="10001:10001", worker_user="10001:10001", timeout=1
        )
    assert "confidential" not in str(error.value)
    created = [c for c in calls if c[:2] == ["docker", "create"]]
    removed = [c[2] for c in calls if c[:2] == ["docker", "rm"]]
    assert len(created) == len(removed)
    assert all(c[c.index("--name") + 1].startswith("finanse-release-probe-") for c in created)
    assert not any("-f" in call or "--rm" in call for call in calls)
    if timeout:
        assert any(c[:2] == ["docker", "stop"] for c in calls)


def test_foreign_probe_identity_is_never_started_stopped_or_removed(release, monkeypatch):
    module = load_gate()
    run, calls = fake_docker(foreign=True)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="ownership"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
    assert not any(c[1] in {"start", "stop", "rm"} for c in calls)


@pytest.mark.parametrize(
    "message", ["Error: No such object: owned", "error: no such object: owned"]
)
def test_cleanup_recognizes_only_explicit_absence_regardless_of_cli_case(monkeypatch, message):
    module = load_gate()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "[]", message),
    )
    assert module.owned_probe("owned", IDS["backend"], "10001:10001", 1) is None


def test_inspect_failure_is_not_mistaken_for_absence(monkeypatch):
    module = load_gate()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "permission denied"),
    )
    with pytest.raises(RuntimeError, match="Cannot inspect"):
        module.owned_probe("owned", IDS["backend"], "10001:10001", 1)


@pytest.mark.parametrize("stop_fails", [False, True])
def test_cleanup_failure_prevents_pass_and_never_forces(release, monkeypatch, stop_fails):
    module = load_gate()
    run, calls = fake_docker(timeout=stop_fails, stop_fails=stop_fails, remove_fails=not stop_fails)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
    assert not any("-f" in c or "--force" in c for c in calls)
    if stop_fails:
        assert not any(c[1] == "rm" for c in calls)


@pytest.mark.parametrize("image", ["latest", "a:tag;evil", "--bad:flag"])
def test_unsafe_image_metadata_fails_before_docker(release, monkeypatch, image):
    module = load_gate()
    meta = json.loads((release / "release.json").read_text())
    meta["backend"] = image
    (release / "release.json").write_text(json.dumps(meta))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Docker not allowed"))
    with pytest.raises(ValueError, match="image"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
