import importlib.util
from pathlib import Path

import pytest

PATCH_PATH = Path(__file__).resolve().parents[2] / "ops/stirling/patch_init.py"


def load_patch():
    spec = importlib.util.spec_from_file_location("stirling_patch", PATCH_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unknown_vendor_script_is_rejected():
    patch = load_patch()
    with pytest.raises(ValueError, match="checksum"):
        patch.patch_init(b"#!/bin/bash\nexit 0\n")


def test_bootstrap_temp_permissions_are_not_repaired(monkeypatch):
    import hashlib

    patch = load_patch()
    source = b"set -euo pipefail\n" + patch.TEMP_BLOCK + b"exec /scripts/init-without-ocr.sh\n"
    monkeypatch.setattr(patch, "BOOTSTRAP_SHA256", hashlib.sha256(source).hexdigest())
    assert (
        patch.patch_bootstrap(source)
        == b"set -euo pipefail\n# Temp paths validated by main init.\nexec /scripts/init-without-ocr.sh\n"
    )
    with pytest.raises(ValueError, match="checksum"):
        patch.patch_bootstrap(source + b"# drift")


def test_patch_changes_only_alias_blocks(monkeypatch):
    import hashlib

    patch = load_patch()
    source = (
        b"#!/bin/bash\nset -euo pipefail\n"
        + patch.DIAGNOSTIC_BLOCK
        + patch.AOT_BLOCK
        + patch.PERMISSIONS_BLOCK
        + b"trap cleanup SIGTERM\nstart_java\n"
    )
    monkeypatch.setattr(patch, "EXPECTED_SHA256", hashlib.sha256(source).hexdigest())
    assert patch.patch_init(source) == (
        b"#!/bin/bash\nset -euo pipefail\n"
        + patch.REPLACEMENT * 2
        + patch.PERMISSIONS_REPLACEMENT
        + b"trap cleanup SIGTERM\nstart_java\n"
    )


@pytest.mark.parametrize("repeat", [0, 2])
def test_missing_or_repeated_block_is_rejected(monkeypatch, repeat):
    import hashlib

    patch = load_patch()
    source = patch.DIAGNOSTIC_BLOCK * repeat + patch.AOT_BLOCK + patch.PERMISSIONS_BLOCK
    monkeypatch.setattr(patch, "EXPECTED_SHA256", hashlib.sha256(source).hexdigest())
    with pytest.raises(ValueError, match="exactly once"):
        patch.patch_init(source)


def load_validator():
    spec = importlib.util.spec_from_file_location(
        "runtime_paths", PATCH_PATH.with_name("validate_runtime_paths.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_path_validation_preserves_private_mode(tmp_path):
    import os

    validator = load_validator()
    tmp_path.chmod(0o700)
    validator.validate_directory(tmp_path, os.getuid(), os.getgid())
    assert tmp_path.stat().st_mode & 0o777 == 0o700
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failure", ["mode", "owner", "symlink"])
def test_runtime_path_validation_fails_without_permission_repair(tmp_path, failure):
    import os

    validator = load_validator()
    uid, gid = os.getuid(), os.getgid()
    path = tmp_path / "state"
    path.mkdir(mode=0o700)
    if failure == "mode":
        path.chmod(0o755)
    elif failure == "owner":
        uid += 1
    else:
        path = tmp_path / "link"
        path.symlink_to(tmp_path / "state", target_is_directory=True)
    before = (tmp_path / "state").stat()
    with pytest.raises(ValueError):
        validator.validate_directory(path, uid, gid)
    after = (tmp_path / "state").stat()
    assert (after.st_uid, after.st_gid, after.st_mode) == (
        before.st_uid,
        before.st_gid,
        before.st_mode,
    )
