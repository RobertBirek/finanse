"""Opt-in synthetic ACL/backup contract; no production paths are accepted."""

import hashlib
import json
import os
import stat
import subprocess
import uuid
from pathlib import Path

import pytest


def validate_fixture(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        mode = path.lstat().st_mode
        if "\n" in str(path) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError("Unsafe staging entry")


def fixture_inventory(root: Path) -> dict:
    validate_fixture(root)
    result = {}
    for path in [root, *root.rglob("*")]:
        info = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            info.st_uid,
            info.st_gid,
            info.st_mode,
            info.st_ino,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return result


def verify_rollback_preflight(root: Path, expected: dict) -> None:
    if fixture_inventory(root) != expected:
        raise ValueError("Staging inventory changed; abort rollback")


@pytest.fixture
def acl_stage(tmp_path):
    image = os.getenv("ACL_TEST_IMAGE")
    if not image:
        pytest.skip("Explicit ACL_TEST_IMAGE required (test-only image with acl tools)")
    assert image.startswith("sha256:")
    metadata = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
    labels = metadata["Config"].get("Labels") or {}
    assert labels.get("advisor.test-only") == "acl"
    assert "@sha256:" in labels.get("advisor.application-runtime", "")
    root = tmp_path / "uploads"
    root.mkdir(mode=0o755)
    content = b"synthetic original"
    digest = hashlib.sha256(content).hexdigest()
    shard = root / digest[:2]
    shard.mkdir(mode=0o755)
    original = shard / digest
    original.write_bytes(content)
    original.chmod(0o600)
    lock = root / ".backup.lock"
    lock.touch(mode=0o644)
    validate_fixture(root)
    name = "advisor-acl-" + uuid.uuid4().hex[:10]
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "-e",
            "PYTHONPATH=/app",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "--security-opt",
            "no-new-privileges:true",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=32m,mode=1777",
            "-v",
            f"{root}:/stage",
            "--entrypoint",
            "sleep",
            image,
            "300",
        ],
        check=True,
        capture_output=True,
    )

    def run(*args, uid="0", check=True):
        return subprocess.run(
            ["docker", "exec", "--user", f"{uid}:{uid}", "-w", "/stage", name, *args],
            check=check,
            capture_output=True,
            text=True,
        )

    def apply():
        validate_fixture(root)
        run("setfacl", "-m", "u:10001:rwx", ".", digest[:2])
        run("setfacl", "-m", "u:10001:r--", f"{digest[:2]}/{digest}")
        run("setfacl", "-m", "u:10001:rw-", ".backup.lock")

    try:
        backend = Path(__file__).resolve().parents[1]
        for relative in ("requirements.txt", "app/documents/service.py"):
            expected = hashlib.sha256((backend / relative).read_bytes()).hexdigest()
            assert run("sha256sum", f"/app/{relative}").stdout.split()[0] == expected
        yield root, original, lock, run, apply, name
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


@pytest.mark.proxy
def test_acl_read_atomic_write_backup_lock_and_no_inheritance(acl_stage):
    root, original, lock, run, apply, name = acl_stage
    relative = original.relative_to(root).as_posix()
    before = original.read_bytes()
    owner = original.stat().st_uid
    inode = lock.stat().st_ino
    assert run("cat", relative, uid="10001", check=False).returncode != 0
    apply()
    assert run("cat", relative, uid="10001").stdout.encode() == before
    assert run("cat", relative, uid="10002", check=False).returncode != 0
    assert "default:" not in run("getfacl", "-R", "-n", ".").stdout
    script = (
        "from pathlib import Path; from app.documents import service; "
        "service.UPLOAD_DIR=Path('/stage'); "
        "content=b'new original'; h=service.compute_sha256(content); "
        "service._write_document_content(h,content); service._write_document_content(h,content)"
    )
    # Real root backup lock blocks the application's non-root atomic publisher.
    holder = subprocess.Popen(
        [
            "docker",
            "exec",
            name,
            "python",
            "-c",
            (
                "import fcntl,time; f=open('/stage/.backup.lock','a+b'); "
                "fcntl.flock(f,fcntl.LOCK_EX); print('locked',flush=True); time.sleep(2)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout.readline().strip() == "locked"
    import time

    started = time.monotonic()
    run("python", "-c", script, uid="10001")
    assert time.monotonic() - started >= 1
    assert holder.wait(timeout=5) == 0
    assert lock.stat().st_ino == inode
    assert original.read_bytes() == before and original.stat().st_uid == owner
    new_hash = hashlib.sha256(b"new original").hexdigest()
    new = root / new_hash[:2] / new_hash
    assert new.stat().st_uid == 10001 and stat.S_IMODE(new.stat().st_mode) == 0o600
    assert run("cat", f"{new_hash[:2]}/{new_hash}", uid="10001").stdout == "new original"
    # A different writer gets no inherited permissions for app UID.
    run("sh", "-c", "umask 077; printf root > root-new")
    assert run("cat", "root-new", uid="10001", check=False).returncode != 0


@pytest.mark.proxy
def test_acl_snapshot_rollback_and_restore_reapplication(acl_stage):
    root, original, _lock, run, apply, _ = acl_stage
    relative = original.relative_to(root).as_posix()
    before = run("getfacl", "-R", "-p", "-n", ".").stdout
    inventory = {
        p.relative_to(root).as_posix(): (
            p.stat().st_uid,
            p.stat().st_gid,
            p.stat().st_mode,
            p.stat().st_ino,
        )
        for p in [root, *root.rglob("*")]
    }
    for line in before.splitlines():
        if line.startswith("# file: "):
            path = line[8:]
            assert path == "." or (path.startswith("./") and ".." not in Path(path).parts)
    run("sh", "-c", "umask 077; mkdir /tmp/acl-meta; getfacl -R -p -n . > /tmp/acl-meta/before.acl")
    apply()
    rollback_inventory = fixture_inventory(root)
    verify_rollback_preflight(root, rollback_inventory)
    run("setfacl", "--restore=/tmp/acl-meta/before.acl")
    assert run("getfacl", "-R", "-p", "-n", ".").stdout == before
    assert {
        p.relative_to(root).as_posix(): (
            p.stat().st_uid,
            p.stat().st_gid,
            p.stat().st_mode,
            p.stat().st_ino,
        )
        for p in [root, *root.rglob("*")]
    } == inventory
    apply()
    run("tar", "--owner=0", "--group=0", "--numeric-owner", "-cf", "/tmp/uploads.tar", ".")
    run("mkdir", "/tmp/restored")
    run("tar", "-xf", "/tmp/uploads.tar", "-C", "/tmp/restored")
    assert "user:10001" not in run("getfacl", "-n", f"/tmp/restored/{relative}").stdout
    assert run("cat", f"/tmp/restored/{relative}", uid="10001", check=False).returncode != 0
    run("setfacl", "-m", "u:10001:rwx", "/tmp/restored", f"/tmp/restored/{original.parent.name}")
    run("setfacl", "-m", "u:10001:r--", f"/tmp/restored/{relative}")
    run("setfacl", "-m", "u:10001:rw-", "/tmp/restored/.backup.lock")
    assert run("cat", f"/tmp/restored/{relative}", uid="10001").stdout == "synthetic original"
    assert run("stat", "-c", "%u:%g", f"/tmp/restored/{relative}").stdout.strip() == "0:0"
    acl = run("getfacl", "-n", f"/tmp/restored/{relative}").stdout
    assert "user:10001:r--" in acl and "mask::r--" in acl
    # Exercise the real atomic writer and duplicate-integrity gate on restored storage.
    script = (
        "from pathlib import Path; from app.documents import service; "
        "service.UPLOAD_DIR=Path('/tmp/restored'); "
        "old=b'synthetic original'; h=service.compute_sha256(old); "
        "service._write_document_content(h,old); "
        "new=b'restored new'; n=service.compute_sha256(new); "
        "service._write_document_content(n,new); service._write_document_content(n,new); "
        "assert service.read_verified_document_content(service.UPLOAD_DIR/h[:2]/h,h)==old"
    )
    lock_before = run("stat", "-c", "%i", "/tmp/restored/.backup.lock").stdout
    holder = subprocess.Popen(
        [
            "docker",
            "exec",
            acl_stage[-1],
            "python",
            "-c",
            (
                "import fcntl,time;f=open('/tmp/restored/.backup.lock','a+b');"
                "fcntl.flock(f,fcntl.LOCK_EX);print('locked',flush=True);time.sleep(2)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout.readline().strip() == "locked"
    import time

    started = time.monotonic()
    run("python", "-c", script, uid="10001")
    assert time.monotonic() - started >= 1
    assert holder.wait(timeout=5) == 0
    assert run("stat", "-c", "%i", "/tmp/restored/.backup.lock").stdout == lock_before


def test_permission_fixture_rejects_symlinks_and_special_files(tmp_path):
    (tmp_path / "link").symlink_to("/etc/passwd")
    with pytest.raises(ValueError, match="Unsafe"):
        validate_fixture(tmp_path)
    (tmp_path / "link").unlink()
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(ValueError, match="Unsafe"):
        validate_fixture(tmp_path)


@pytest.mark.parametrize("change", ["added", "deleted", "replaced", "content", "mode"])
def test_rollback_preflight_rejects_changed_inventory(tmp_path, change):
    path = tmp_path / "original"
    path.write_bytes(b"before")
    before = fixture_inventory(tmp_path)
    if change == "added":
        (tmp_path / "new").write_bytes(b"new")
    elif change == "deleted":
        path.unlink()
    elif change == "replaced":
        other = tmp_path / "replacement"
        other.write_bytes(b"before")
        other.replace(path)
    elif change == "content":
        path.write_bytes(b"after")
    else:
        path.chmod(0o777)
    with pytest.raises(ValueError, match="changed"):
        verify_rollback_preflight(tmp_path, before)
