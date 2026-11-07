import importlib.util
import io
import json
import os
import stat
import subprocess
import tarfile
from pathlib import Path
from uuid import uuid4

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "ops" / "prepare_release.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release_input(tmp_path, monkeypatch):
    module = load_module()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        for name in ("backend/app/main.py", "frontend/nginx.conf"):
            data = b"test source\n"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))

    def fake_git(repository, *args):
        if args[0] == "rev-parse":
            return ("a" * 40 + "\n").encode()
        if args[0] == "show":
            return b"fastapi==0.111.1\n"
        assert args[0] == "archive"
        return archive.getvalue()

    monkeypatch.setattr(module, "git", fake_git)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("verified production build")
    return module, {
        "repository": tmp_path,
        "revision": "main",
        "runtime_revision": "old",
        "output": tmp_path / "release",
        "frontend_dist": dist,
        "backend_runtime": "local/runtime-backend:old",
        "worker_runtime": "local/runtime-worker:old",
        "frontend_runtime": "local/runtime-frontend:old",
    }


def test_release_removes_code_binds_and_pins_all_images(release_input):
    module, args = release_input
    metadata = module.prepare_release(**args)
    output = args["output"]
    overlay = (output / "compose.release.yaml").read_text()
    assert overlay.count("volumes: !override") == 2
    assert overlay.count("target: /app/uploads") == 2
    assert "target: /app\n" not in overlay
    assert "environment:" not in overlay
    assert "secrets" not in overlay
    for service in ("backend", "worker", "frontend"):
        assert metadata[service] == f"local/finanse-{service}:{'a' * 40}"
        assert metadata[service] in overlay
        dockerfile = (output / f"Dockerfile.{service}").read_text()
        assert 'org.opencontainers.image.revision="' + "a" * 40 + '"' in dockerfile
    assert (output / "source/backend/app/main.py").is_file()
    assert (output / "frontend-dist/index.html").is_file()
    with pytest.raises(ValueError, match="new directory"):
        module.prepare_release(**args)


def test_release_rejects_changed_runtime_requirements(release_input, monkeypatch):
    module, args = release_input
    original = module.git

    def changed(repository, *parts):
        if parts[0] == "show":
            return b"changed" if parts[1].startswith("old:") else b"original"
        return original(repository, *parts)

    monkeypatch.setattr(module, "git", changed)
    args["runtime_revision"] = "old"

    # Simulate different resolved commits as well as requirements.
    def resolved(repository, *parts):
        if parts[0] == "rev-parse" and parts[-1].startswith("old"):
            return b"old\n"
        return changed(repository, *parts)

    monkeypatch.setattr(module, "git", resolved)
    with pytest.raises(ValueError, match="dependencies changed"):
        module.prepare_release(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("image", ["latest", "runtime:ok\nRUN echo bad", "runtime:tag;bad"])
def test_release_rejects_unpinned_or_unsafe_image_references(release_input, image):
    module, args = release_input
    args["backend_runtime"] = image
    with pytest.raises(ValueError, match="explicit local image"):
        module.prepare_release(**args)


@pytest.mark.parametrize("file_mode,directory_mode", [(0o600, 0o700), (0o777, 0o777)])
def test_public_dist_modes_normalized_without_changing_source_or_bytes(
    release_input: tuple, file_mode: int, directory_mode: int
) -> None:
    module, args = release_input
    source: Path = args["frontend_dist"]
    nested = source / "assets" / "fonty próbne"
    nested.mkdir(parents=True)
    (nested / "font name.woff2").write_bytes(b"font\x00bytes")
    (source / "assets" / "bundle.js").write_bytes(b"console.log('verified');\n")
    paths = [source, *source.rglob("*")]
    for path in paths:
        path.chmod(directory_mode if path.is_dir() else file_mode)
    original = {
        path.relative_to(source): (
            stat.S_IMODE(path.stat().st_mode),
            None if path.is_dir() else path.read_bytes(),
        )
        for path in paths
    }

    module.prepare_release(**args)

    target = args["output"] / "frontend-dist"
    assert stat.S_IMODE(args["output"].stat().st_mode) == 0o700
    for relative, (mode, data) in original.items():
        copied = target / relative
        assert stat.S_IMODE(copied.stat().st_mode) == (0o755 if data is None else 0o644)
        assert stat.S_IMODE((source / relative).stat().st_mode) == mode
        if data is not None:
            assert copied.read_bytes() == (source / relative).read_bytes() == data


def test_frontend_build_gate_checks_all_assets_as_nginx_without_changing_runtime_user(
    release_input: tuple,
) -> None:
    module, args = release_input
    module.prepare_release(**args)
    dockerfile = (args["output"] / "Dockerfile.frontend").read_text()
    assert "su -s /bin/sh nginx -c" in dockerfile
    assert "test -r /usr/share/nginx/html/index.html" in dockerfile
    assert "find /usr/share/nginx/html -type f -exec cat {} +" in dockerfile
    assert not any(line.startswith("USER ") for line in dockerfile.splitlines())


def test_backend_copy_modes_survive_private_umask_preserving_bytes_and_executables(
    release_input: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, args = release_input
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        for name, mode, content in [
            ("backend/app/main.py", 0o644, b"import app.worker\n"),
            ("backend/app/nested/module.py", 0o600, b"VALUE = 7\n"),
            ("backend/scripts/entry.sh", 0o700, b"#!/bin/sh\nexit 0\n"),
            ("frontend/nginx.conf", 0o644, b"# synthetic\n"),
        ]:
            info = tarfile.TarInfo(name)
            info.mode, info.size = mode, len(content)
            bundle.addfile(info, io.BytesIO(content))
    original_git = module.git
    monkeypatch.setattr(
        module,
        "git",
        lambda repo, *parts: (
            archive.getvalue() if parts[0] == "archive" else original_git(repo, *parts)
        ),
    )
    original_archive = archive.getvalue()
    previous_umask = os.umask(0o077)
    try:
        module.prepare_release(**args)
    finally:
        os.umask(previous_umask)
    copied = args["output"] / "source/backend"
    assert stat.S_IMODE(args["output"].stat().st_mode) == 0o700
    for path in [copied, copied / "app", copied / "app/nested", copied / "scripts"]:
        assert stat.S_IMODE(path.stat().st_mode) == 0o755
    for relative, mode, content in [
        ("app/main.py", 0o644, b"import app.worker\n"),
        ("app/nested/module.py", 0o644, b"VALUE = 7\n"),
        ("scripts/entry.sh", 0o755, b"#!/bin/sh\nexit 0\n"),
    ]:
        assert (copied / relative).read_bytes() == content
        assert stat.S_IMODE((copied / relative).stat().st_mode) == mode
    assert archive.getvalue() == original_archive
    assert (args["frontend_dist"] / "index.html").read_text() == "verified production build"


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_backend_normalization_refuses_archive_links(release_input: tuple, monkeypatch, kind):
    module, args = release_input
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        data = b"private archive bytes"
        info = tarfile.TarInfo("frontend/nginx.conf")
        info.size = len(data)
        bundle.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo("backend/app/link.py")
        info.type = kind
        info.linkname = (
            "../../frontend/nginx.conf" if kind == tarfile.SYMTYPE else "frontend/nginx.conf"
        )
        bundle.addfile(info)
    original_git = module.git
    monkeypatch.setattr(
        module,
        "git",
        lambda repo, *parts: (
            archive.getvalue() if parts[0] == "archive" else original_git(repo, *parts)
        ),
    )
    with pytest.raises(ValueError, match="links"):
        module.prepare_release(**args)
    assert not (args["output"] / "source/backend/app/link.py").exists()


@pytest.mark.proxy
@pytest.mark.parametrize("tamper_nested_asset", [False, True])
def test_generated_frontend_image_enforces_real_nginx_read_access(
    release_input: tuple, tamper_nested_asset: bool
) -> None:
    runtime = os.environ.get("TEST_RELEASE_FRONTEND_RUNTIME")
    if not runtime:
        pytest.skip("Set TEST_RELEASE_FRONTEND_RUNTIME to an existing local nginx image:tag")
    module, args = release_input
    # Inspect first: tests must never pull a runtime image or touch running services.
    subprocess.run(["docker", "image", "inspect", runtime], capture_output=True, check=True)
    args["frontend_runtime"] = runtime
    source: Path = args["frontend_dist"]
    source.chmod(0o700)
    (source / "index.html").chmod(0o600)
    (source / "assets").mkdir(mode=0o700)
    (source / "assets" / "nested file.js").write_text("synthetic asset")
    (source / "assets" / "nested file.js").chmod(0o600)
    module.prepare_release(**args)
    if tamper_nested_asset:
        (args["output"] / "frontend-dist/assets/nested file.js").chmod(0o600)
    image = f"local/finanse-release-permissions-test:{uuid4().hex}"
    built = False
    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--network=none",
                "--pull=false",
                "-f",
                str(args["output"] / "Dockerfile.frontend"),
                "-t",
                image,
                str(args["output"]),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        built = result.returncode == 0
        if tamper_nested_asset:
            assert result.returncode != 0, "Build accepted an asset unreadable to nginx"
            assert "Permission denied" in result.stdout + result.stderr
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--user",
                    "nginx",
                    "--entrypoint",
                    "sh",
                    image,
                    "-c",
                    (
                        "test -r /usr/share/nginx/html/index.html && "
                        "test -r '/usr/share/nginx/html/assets/nested file.js'"
                    ),
                ],
                capture_output=True,
                check=True,
            )
    finally:
        if built:
            subprocess.run(["docker", "image", "rm", image], capture_output=True, check=True)


@pytest.mark.proxy
@pytest.mark.parametrize(
    "damage", ["none", "nested_unreadable", "worker_import", "entrypoint_missing"]
)
def test_offline_nonroot_gate_accepts_private_package_and_rejects_broken_images(
    release_input: tuple,
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    runtime = os.environ.get("TEST_RELEASE_BACKEND_RUNTIME")
    if not runtime:
        pytest.skip("Set TEST_RELEASE_BACKEND_RUNTIME to an existing local Python app image:tag")
    subprocess.run(["docker", "image", "inspect", runtime], capture_output=True, check=True)
    module, args = release_input
    gate_spec = importlib.util.spec_from_file_location(
        "verify_release", SCRIPT.with_name("verify_release.py")
    )
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)
    archive = io.BytesIO()
    main = b"""import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.nested.value import VALUE
class Settings(BaseSettings):
 model_config=SettingsConfigDict(env_file='.env')
 TOKEN: str=''
assert os.getuid() > 0 and os.getgid() > 0
assert 'SENSITIVE_TOKEN' not in os.environ
assert Settings().TOKEN == ''
assert VALUE == 7
app=object()
"""
    worker = b"""from app.nested.value import VALUE
assert VALUE == 7
class WorkerSettings: pass
"""
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        for name, content in [
            ("backend/app/main.py", main),
            ("backend/app/worker.py", worker),
            ("backend/app/__init__.py", b""),
            ("backend/app/nested/value.py", b"VALUE = 7\n"),
            ("backend/.env", b"TOKEN=must-not-be-read\n"),
            ("frontend/nginx.conf", b"# synthetic\n"),
        ]:
            info = tarfile.TarInfo(name)
            info.mode = 0o644
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))
    original_git = module.git
    monkeypatch.setattr(
        module,
        "git",
        lambda repo, *parts: (
            archive.getvalue() if parts[0] == "archive" else original_git(repo, *parts)
        ),
    )
    args["backend_runtime"] = args["worker_runtime"] = runtime
    previous_umask = os.umask(0o077)
    try:
        module.prepare_release(**args)
    finally:
        os.umask(previous_umask)
    copied = args["output"] / "source/backend/app"
    if damage == "nested_unreadable":
        (copied / "nested").chmod(0o700)
    if damage == "worker_import":
        (copied / "worker.py").write_text("raise RuntimeError('synthetic import failure')\n")
    if damage == "entrypoint_missing":
        (copied / "worker.py").write_text("# module imports but no WorkerSettings\n")
    # Override ONLY synthetic metadata to unique disposable tags, never production.
    image = "local/finanse-release-nonroot-test:" + uuid4().hex
    metadata = {"revision": "a" * 40, "backend": image, "worker": image}
    (args["output"] / "release.json").write_text(json.dumps(metadata))
    dockerfile = args["output"] / "Dockerfile.backend"
    dockerfile.write_text(dockerfile.read_text() + "ENV SENSITIVE_TOKEN=must-not-leak\n")
    built = False
    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--network=none",
                "--pull=false",
                "--no-cache",
                "-f",
                str(dockerfile),
                "-t",
                image,
                str(args["output"]),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        built = result.returncode == 0
        assert built, result.stdout + result.stderr
        if damage == "none":
            proof = gate.verify_release(
                args["output"], backend_user="10001:10001", worker_user="20002:20002"
            )
            assert proof["passed"] is True
            assert proof["services"]["backend"]["uid"] == 10001
            assert proof["services"]["worker"]["uid"] == 20002
            assert proof["services"]["worker"]["module"] == "app.worker"
        else:
            with pytest.raises(RuntimeError, match="probe failed"):
                gate.verify_release(
                    args["output"], backend_user="10001:10001", worker_user="20002:20002"
                )
        assert stat.S_IMODE(args["output"].stat().st_mode) == 0o700
    finally:
        if built:
            subprocess.run(["docker", "image", "rm", image], capture_output=True, check=True)
