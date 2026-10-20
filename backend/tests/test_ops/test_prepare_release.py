import importlib.util
import io
import tarfile
from pathlib import Path

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
