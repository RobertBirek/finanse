import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_ops.preflight_fixtures import module

OLD = "db062d222951e110af176ebf605291683ba32757"
NEW = "d284e80f5731dff7803b827da51fe553f91ee26c"


def runtime(root: Path, revision: str, *, legacy: bool = False) -> Path:
    target = root / f"restore-runtime-{revision[: 7 if legacy else 12]}"
    script = target / "ops/restore-verify.sh"
    script.parent.mkdir(parents=True)
    script.write_text("exit 1\n")
    script.chmod(0o700)
    return target


def test_atomic_switch_and_replay(tmp_path: Path) -> None:
    ptr = module("restore_runtime_pointer")
    uid = os.getuid()
    old, target = runtime(tmp_path, OLD, legacy=True), runtime(tmp_path, NEW)
    ptr.activate_pointer(
        tmp_path, expected_current=None, target=old, approved_revision=OLD, owner_uid=uid
    )
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid) == old
    ptr.activate_pointer(
        tmp_path, expected_current=old, target=target, approved_revision=NEW, owner_uid=uid
    )
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid) == target
    assert old.is_dir()
    assert (tmp_path / "restore-runtime-current").readlink() == Path(target.name)
    with pytest.raises(ptr.PointerError, match="current_changed"):
        ptr.activate_pointer(
            tmp_path, expected_current=old, target=old, approved_revision=OLD, owner_uid=uid
        )
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid) == target


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "dangling",
        "outside",
        "writable",
        "owner",
        "alias",
        "root_writable",
        "ancestor_writable",
        "ops_writable",
        "script_writable",
        "script_nonexecuting",
    ],
)
def test_untrusted_pointer_is_refused(tmp_path: Path, fault: str) -> None:
    ptr = module("restore_runtime_pointer")
    root = tmp_path / "runtime"
    root.mkdir()
    uid = os.getuid()
    target = runtime(root, NEW)
    link = root / "restore-runtime-current"
    if fault != "missing":
        link.symlink_to(
            "../" + target.name if fault == "outside" else target.name,
        )
    if fault == "dangling":
        link.unlink()
        link.symlink_to("restore-runtime-aaaaaaaaaaaa")
    if fault == "writable":
        target.chmod(0o775)
    if fault == "root_writable":
        root.chmod(0o775)
    if fault == "ancestor_writable":
        tmp_path.chmod(0o775)
    if fault == "ops_writable":
        (target / "ops").chmod(0o775)
    if fault == "script_writable":
        (target / "ops/restore-verify.sh").chmod(0o770)
    if fault == "script_nonexecuting":
        (target / "ops/restore-verify.sh").chmod(0o600)
    if fault == "alias":
        target.rename(root / "other")
        target.symlink_to("other")
    if fault == "owner":
        uid += 1
    with pytest.raises(ptr.PointerError):
        ptr.inspect_pointer(root, owner_uid=uid)


def test_wrong_revision_or_interrupted_rename_preserves_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ptr = module("restore_runtime_pointer")
    old, target = runtime(tmp_path, OLD, legacy=True), runtime(tmp_path, NEW)
    (tmp_path / "restore-runtime-current").symlink_to(old.name)
    uid = os.getuid()
    with pytest.raises(ptr.PointerError, match="revision_mismatch"):
        ptr.activate_pointer(
            tmp_path, expected_current=old, target=target, approved_revision=OLD, owner_uid=uid
        )

    def interrupted(*args: object, **kwargs: object) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(ptr.os, "replace", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        ptr.activate_pointer(
            tmp_path, expected_current=old, target=target, approved_revision=NEW, owner_uid=uid
        )
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid) == old
    assert {f.name for f in tmp_path.iterdir()} == {
        old.name,
        target.name,
        "restore-runtime-current",
    }


def test_release_restore_decision_is_driven_by_schema_not_application_rollback() -> None:
    ptr = module("restore_runtime_pointer")
    old, new = "e5a46dc32772", "5f1d54d40a2e"
    assert ptr.pointer_action(old, old, old, None) == "keep"
    assert ptr.pointer_action(old, old, new, None) == "stop"
    assert ptr.pointer_action(old, old, new, new) == "migrate_then_activate"
    assert ptr.pointer_action(new, new, new, None) == "keep"
    assert ptr.pointer_action(old, new, new, new) == "activate"
    assert ptr.pointer_action(new, old, old, old) == "activate"
    assert ptr.pointer_action("unknown", old, new, new) == "stop"


def test_interrupted_migration_blocks_scheduled_restore_until_explicit_clear(
    tmp_path: Path,
) -> None:
    ptr = module("restore_runtime_pointer")
    uid = os.getuid()
    old, target = runtime(tmp_path, OLD, legacy=True), runtime(tmp_path, NEW)
    ptr.activate_pointer(
        tmp_path, expected_current=None, target=old, approved_revision=OLD, owner_uid=uid
    )
    ptr.inhibit_restore(tmp_path, owner_uid=uid)
    with pytest.raises(ptr.PointerError, match="restore_inhibited"):
        ptr.inspect_pointer(tmp_path, owner_uid=uid)
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid, allow_inhibited=True) == old
    ptr.activate_pointer(
        tmp_path, expected_current=old, target=target, approved_revision=NEW, owner_uid=uid
    )
    with pytest.raises(ptr.PointerError, match="restore_inhibited"):
        ptr.inspect_pointer(tmp_path, owner_uid=uid)
    ptr.clear_restore_inhibition(tmp_path, expected_current=target, owner_uid=uid)
    assert ptr.inspect_pointer(tmp_path, owner_uid=uid) == target


def test_deploy_checks_restore_before_build() -> None:
    root = Path(__file__).resolve().parents[3]
    command = (root / ".opencode/command/deploy.md").read_text()
    assert command.index("Stałe wskazanie narzędzia odtwarzania") < command.index(
        "`ops/prepare_release.py`"
    )


def test_scheduled_restore_refuses_execution_after_lock_owner_exit(tmp_path: Path) -> None:
    ptr = module("restore_runtime_pointer")
    target = runtime(tmp_path, NEW)
    script = target / "ops/restore-verify.sh"
    log = tmp_path / "executed"
    script.write_text(f"touch '{log}'\n")
    uid = os.getuid()
    ptr.activate_pointer(
        tmp_path, expected_current=None, target=target, approved_revision=NEW, owner_uid=uid
    )
    bootstrap = (
        "import os,runpy,sys; tool=sys.argv.pop(1); "
        'raise SystemExit(runpy.run_path(tool)["main"](owner_uid=os.getuid()))'
    )
    operation = (
        f"runtime=$('{sys.executable}' -I -S -B -c '{bootstrap}' '{ptr.__file__}' --root '{tmp_path}') || exit $?; "
        '/bin/bash "$runtime/ops/restore-verify.sh"'
    )

    def scheduled() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/usr/bin/flock", str(tmp_path / "backup-restore.lock"), "/bin/sh", "-c", operation],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    ptr.inhibit_restore(tmp_path, owner_uid=uid)
    assert scheduled().returncode == 2
    assert not log.exists()
    ptr.clear_restore_inhibition(tmp_path, expected_current=target, owner_uid=uid)
    assert scheduled().returncode == 0
    assert log.is_file()
