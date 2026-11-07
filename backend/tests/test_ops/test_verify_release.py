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


def fake_docker(*, wrong_label=False, fail_worker=False, timeout=False):
    calls = []

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
        if args[:2] == ["docker", "run"]:
            service = "worker" if IDS["worker"] in args else "backend"
            if timeout:
                raise subprocess.TimeoutExpired(args, 1)
            if fail_worker and service == "worker":
                raise subprocess.CalledProcessError(1, args, "", "synthetic confidential traceback")
            user = args[args.index("--user") + 1]
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
        assert args[:3] == ["docker", "rm", "-f"]
        return subprocess.CompletedProcess(args, 0, "", "")

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
    for args in [c for c in calls if c[:2] == ["docker", "run"]]:
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


def test_revision_mismatch_fails_before_starting_probe(release, monkeypatch):
    module = load_gate()
    run, calls = fake_docker(wrong_label=True)
    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(ValueError, match="revision"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
    assert not any(c[:2] == ["docker", "run"] for c in calls)


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
    started = {c[c.index("--name") + 1] for c in calls if c[:2] == ["docker", "run"]}
    removed = {c[3] for c in calls if c[:3] == ["docker", "rm", "-f"]}
    assert started == removed
    assert all(name.startswith("finanse-release-probe-") for name in started)


@pytest.mark.parametrize("image", ["latest", "a:tag;evil", "--bad:flag"])
def test_unsafe_image_metadata_fails_before_docker(release, monkeypatch, image):
    module = load_gate()
    meta = json.loads((release / "release.json").read_text())
    meta["backend"] = image
    (release / "release.json").write_text(json.dumps(meta))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Docker not allowed"))
    with pytest.raises(ValueError, match="image"):
        module.verify_release(release, backend_user="10001:10001", worker_user="10001:10001")
