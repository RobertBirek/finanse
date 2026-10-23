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


def test_patch_changes_only_alias_blocks(monkeypatch):
    import hashlib

    patch = load_patch()
    source = (
        b"#!/bin/bash\nset -euo pipefail\n"
        + patch.DIAGNOSTIC_BLOCK
        + patch.AOT_BLOCK
        + b"trap cleanup SIGTERM\nstart_java\n"
    )
    monkeypatch.setattr(patch, "EXPECTED_SHA256", hashlib.sha256(source).hexdigest())
    assert patch.patch_init(source) == (
        b"#!/bin/bash\nset -euo pipefail\n"
        + patch.REPLACEMENT * 2
        + b"trap cleanup SIGTERM\nstart_java\n"
    )


@pytest.mark.parametrize("repeat", [0, 2])
def test_missing_or_repeated_block_is_rejected(monkeypatch, repeat):
    import hashlib

    patch = load_patch()
    source = patch.DIAGNOSTIC_BLOCK * repeat + patch.AOT_BLOCK
    monkeypatch.setattr(patch, "EXPECTED_SHA256", hashlib.sha256(source).hexdigest())
    with pytest.raises(ValueError, match="exactly once"):
        patch.patch_init(source)
