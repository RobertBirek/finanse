"""Offline contracts for the restore runtime compatibility gate."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import module


def migration(revision: str, parent: str | None) -> str:
    return f"revision = {revision!r}\ndown_revision = {parent!r}\n"


def chain() -> dict[str, str]:
    return {
        "a.py": migration("a", None),
        "b.py": migration("b", "a"),
        "c.py": migration("c", "b"),
    }


@pytest.mark.parametrize("snapshot", ["a", "c"])
def test_connected_snapshot_at_expected_head(snapshot: str) -> None:
    module("restore_runtime_preflight").check_lineage(chain(), snapshot, "c")


@pytest.mark.parametrize(
    ("snapshot", "head", "code"),
    [("z", "c", "snapshot_revision_unknown"), ("a", "b", "runtime_head_mismatch")],
)
def test_reject_unknown_snapshot_or_wrong_head(snapshot: str, head: str, code: str) -> None:
    check = module("restore_runtime_preflight")
    with pytest.raises(check.PreflightInputError, match=f"^{code}$"):
        check.check_lineage(chain(), snapshot, head)


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"d.py": migration("d", "a")}, "migration_graph_invalid"),
        ({"dup.py": migration("a", None)}, "migration_graph_invalid"),
        ({"a.py": migration("a", "c")}, "migration_graph_invalid"),
        ({"c.py": migration("c", "b") + "depends_on = 'another'\n"}, "migration_ast_invalid"),
    ],
    ids=["branch", "duplicate", "cycle", "dependency"],
)
def test_reject_unsupported_graph(extra: dict[str, str], code: str) -> None:
    check = module("restore_runtime_preflight")
    with pytest.raises(check.PreflightInputError, match=f"^{code}$"):
        check.check_lineage(chain() | extra, "a", "c")


VERSIONS = "backend/migrations/versions"
CONFIG = "backend/alembic.ini"
MEMBERS = {
    "ops/restore-verify.sh": "# not executed\n",
    CONFIG: "[alembic]\nscript_location = migrations\nprepend_sys_path = .\n",
    "backend/migrations/env.py": "raise AssertionError('env must not execute')\n",
    "backend/.venv/bin/alembic": "# not executed\n",
    **{
        f"{VERSIONS}/{name}": text + "raise AssertionError('must not execute')\n"
        for name, text in chain().items()
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Scenario:
    def __init__(self, root: Path) -> None:
        self.runtime = root / "runtime"
        for name, text in MEMBERS.items():
            member = self.runtime / name
            member.parent.mkdir(parents=True, exist_ok=True)
            member.write_text(text)
        self.runtime_manifest = root / "runtime.json"
        self.snapshot_manifest = root / "snapshot.json"
        self.snapshot_manifest.write_text('{"alembic_revision":"a"}')
        self.pin_runtime()
        self.pins = {
            "runtime-manifest-sha256": digest(self.runtime_manifest),
            "snapshot-manifest-sha256": digest(self.snapshot_manifest),
        }

    def pin_runtime(self, *, phase: str = "rehearsal") -> None:
        self.runtime_manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "runtime_revision": "d" * 40,
                    "runtime_root": str(self.runtime),
                    "scope": {
                        "phase": phase,
                        "candidate": "a" * 40,
                        "expected_head": "c",
                        "snapshot_id": "b" * 64,
                        "snapshot_manifest_sha256": digest(self.snapshot_manifest),
                    },
                    "files": [
                        {"path": path, "sha256": digest(self.runtime / path)} for path in MEMBERS
                    ],
                }
            )
        )

    def invoke(self, **overrides: str) -> int:
        flags = {
            "phase": "rehearsal",
            "candidate": "a" * 40,
            "runtime-root": str(self.runtime),
            "runtime-manifest": str(self.runtime_manifest),
            "snapshot-id": "b" * 64,
            "snapshot-manifest": str(self.snapshot_manifest),
            "expected-head": "c",
            **self.pins,
            **overrides,
        }
        argv = [arg for k, v in flags.items() for arg in (f"--{k}", v)]
        return int(module("restore_runtime_preflight").main(argv))


def assert_blocked(scene: Scenario, capsys: pytest.CaptureFixture[str], **flags: str) -> str:
    assert scene.invoke(**flags) == 2
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert set(report) == {"version", "compatible", "authorized", "reason_code"}
    assert report["version"] == 1
    assert report["compatible"] is False and report["authorized"] is False
    assert str(scene.runtime) not in captured.out and not captured.err
    return str(report["reason_code"])


@pytest.mark.parametrize("phase", ["rehearsal", "after_rollout"])
def test_snapshot_head_compatibility_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], phase: str
) -> None:
    scene = Scenario(tmp_path)
    scene.pin_runtime(phase=phase)
    scene.pins["runtime-manifest-sha256"] = digest(scene.runtime_manifest)
    assert scene.invoke(phase=phase) == 0
    assert json.loads(capsys.readouterr().out) == {
        "version": 1,
        "compatible": True,
        "authorized": False,
        "phase": phase,
        "candidate": "a" * 40,
        "snapshot_id": "b" * 64,
        "snapshot_manifest_sha256": digest(scene.snapshot_manifest),
        "runtime_revision": "d" * 40,
        "runtime_manifest_sha256": digest(scene.runtime_manifest),
        "snapshot_revision": "a",
        "expected_head": "c",
    }


@pytest.mark.parametrize("change", ["bytes", "extra", "nested", "missing"])
def test_drift_blocks_even_with_same_revisions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str
) -> None:
    scene = Scenario(tmp_path)
    versions = scene.runtime / VERSIONS
    if change == "bytes":
        p = versions / "a.py"
        p.write_text(p.read_text() + "# new bytes\n")
    elif change == "extra":
        (versions / "extra.py").write_text(migration("extra", "c"))
    elif change == "nested":
        (versions / "nested").mkdir()
        (versions / "nested/extra.py").write_text(migration("extra", "c"))
    else:
        (versions / "a.py").unlink()
    assert_blocked(scene, capsys)


@pytest.mark.parametrize(
    "change",
    ["different-location", "version-locations", "default", "dir", "file", "cache", "writable"],
)
def test_unsupported_restore_layout_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str
) -> None:
    scene = Scenario(tmp_path)
    versions = scene.runtime / VERSIONS
    config = scene.runtime / CONFIG
    if change == "dir":
        moved = tmp_path / "versions"
        versions.rename(moved)
        versions.symlink_to(moved, target_is_directory=True)
    elif change == "file":
        original = versions / "a.py"
        moved = tmp_path / "a.py"
        original.rename(moved)
        original.symlink_to(moved)
    elif change == "cache":
        (versions / "__pycache__").symlink_to(tmp_path, target_is_directory=True)
    elif change == "writable":
        versions.chmod(0o777)
    else:
        config.write_text(
            {
                "different-location": "[alembic]\nscript_location = elsewhere\n",
                "version-locations": config.read_text() + "version_locations = alternate\n",
                "default": "[DEFAULT]\nsourceless = true\n" + config.read_text(),
            }[change]
        )
        scene.pin_runtime()
        scene.pins["runtime-manifest-sha256"] = digest(scene.runtime_manifest)
    assert_blocked(scene, capsys)


def test_regular_pycache_is_ignored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scene = Scenario(tmp_path)
    cache = scene.runtime / VERSIONS / "__pycache__"
    cache.mkdir()
    (cache / "ignored.pyc").write_bytes(b"not read")
    assert scene.invoke() == 0
    assert json.loads(capsys.readouterr().out)["compatible"] is True


@pytest.mark.parametrize("snapshot", ["latest", "abcdef01"])
def test_invalid_snapshot_binding_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], snapshot: str
) -> None:
    scene = Scenario(tmp_path)
    assert_blocked(scene, capsys, **{"snapshot-id": snapshot})


def test_snapshot_manifest_digest_and_schema_are_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scene = Scenario(tmp_path)
    scene.snapshot_manifest.write_text('{"alembic_revision":"a_future_snapshot"}')
    assert_blocked(scene, capsys)
    scene.pin_runtime()
    scene.pins["runtime-manifest-sha256"] = digest(scene.runtime_manifest)
    assert (
        assert_blocked(
            scene, capsys, **{"snapshot-manifest-sha256": digest(scene.snapshot_manifest)}
        )
        == "snapshot_revision_unknown"
    )


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("candidate", "e" * 40),
        ("phase", "after_rollout"),
        ("expected-head", "b"),
        ("snapshot-id", "f" * 64),
    ],
)
def test_exact_scope_cannot_be_relabeled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str, value: str
) -> None:
    scene = Scenario(tmp_path)
    assert assert_blocked(scene, capsys, **{flag: value}) == "scope_mismatch"


def test_approved_scope_cannot_be_used_for_another_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scene = Scenario(tmp_path)
    scene.snapshot_manifest.write_text('{"alembic_revision":"c"}')
    assert (
        assert_blocked(
            scene, capsys, **{"snapshot-manifest-sha256": digest(scene.snapshot_manifest)}
        )
        == "scope_mismatch"
    )


@pytest.mark.parametrize("change", ["malformed", "duplicate", "missing", "fifo", "oversize"])
def test_input_failures_do_not_echo_contents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], change: str
) -> None:
    scene = Scenario(tmp_path)
    p = scene.snapshot_manifest
    if change in {"missing", "fifo"}:
        p.unlink()
        if change == "fifo":
            os.mkfifo(p)
    else:
        meta = {
            "malformed": "private-canary invalid json",
            "duplicate": '{"alembic_revision":"private-canary","alembic_revision":"a"}',
            "oversize": " " * (1024 * 1024) + '{"alembic_revision":"a"}',
        }
        p.write_text(meta[change])
        scene.pin_runtime()
        scene.pins["runtime-manifest-sha256"] = digest(scene.runtime_manifest)
        scene.pins["snapshot-manifest-sha256"] = digest(p)
    assert "private-canary" not in assert_blocked(scene, capsys)
