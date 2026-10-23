import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.proxy
def test_hardening_compose_enforces_limits_and_nonroot(tmp_path):
    profile = Path(__file__).resolve().parents[2] / "ops/document-hardening.compose.yaml"
    base = tmp_path / "compose.yaml"
    base.write_text(
        "services:\n  backend:\n    image: example/backend:test\n    privileged: true\n    user: '0'\n"
        "  worker:\n    image: example/worker:test\n"
        "  stirling-pdf:\n    image: example/stirling:test\n"
    )
    env = os.environ | {
        "ADVISOR_UID": "10001",
        "ADVISOR_GID": "10001",
        "STIRLING_UID": "10002",
        "STIRLING_GID": "10002",
    }
    result = subprocess.run(
        ["docker", "compose", "-f", str(base), "-f", str(profile), "config", "--format", "json"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for service in services.values():
        assert service["user"] in {"10001:10001", "10002:10002"}
        assert 0 < int(service["mem_limit"]) <= 2 * 1024**3
        assert 0 < float(service["cpus"]) <= 2
        assert 0 < int(service["pids_limit"]) <= 256
        assert service["read_only"] is True
        assert service.get("privileged", False) is False
        assert "ALL" in service["cap_drop"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert not service.get("ports")
        assert not any("docker.sock" in str(mount) for mount in service.get("volumes", []))


@pytest.mark.proxy
def test_hardening_requires_explicit_runtime_user(tmp_path):
    profile = Path(__file__).resolve().parents[2] / "ops/document-hardening.compose.yaml"
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ADVISOR_UID", "ADVISOR_GID", "STIRLING_UID", "STIRLING_GID"}
    }
    result = subprocess.run(
        ["docker", "compose", "-f", str(profile), "config"],
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert b"ADVISOR_UID" in result.stderr or b"STIRLING_UID" in result.stderr
