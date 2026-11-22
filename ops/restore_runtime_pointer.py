"""Stable restore-runtime pointer primitives; never an approval or a deploy tool."""

import argparse
import os
import re
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

POINTER = "restore-runtime-current"
INHIBITION = "restore-runtime-inhibited"
LEGACY_NAME = "restore-runtime-db062d2"
LEGACY_REVISION = "db062d222951e110af176ebf605291683ba32757"
VERSIONED_NAME = re.compile(r"restore-runtime-[0-9a-f]{12}")
FULL_REVISION = re.compile(r"[0-9a-f]{40}")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
PointerAction = Literal["keep", "stop", "migrate_then_activate", "activate"]


class PointerError(ValueError):
    """A bounded error code, safe to put in an operational report."""


def _secure(info: os.stat_result, owner: int, *, ancestor: bool = False) -> None:
    if info.st_uid not in ({0, owner} if ancestor else {owner}):
        raise PointerError("owner_mismatch")
    if info.st_mode & 0o022 and not (ancestor and info.st_mode & stat.S_ISVTX):
        raise PointerError("writable_path")


@contextmanager
def _root_directory(root: Path, owner: int) -> Iterator[int]:
    if not root.is_absolute() or root == Path("/") or ".." in root.parts:
        raise PointerError("runtime_root_invalid")
    fd = os.open("/", DIR_FLAGS)
    try:
        for index, part in enumerate(root.parts[1:], start=1):
            new = os.open(part, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = new
            _secure(os.fstat(fd), owner, ancestor=index < len(root.parts) - 1)
        yield fd
    finally:
        os.close(fd)


def _validate_target(root_fd: int, name: str, owner: int) -> None:
    if name != LEGACY_NAME and not VERSIONED_NAME.fullmatch(name):
        raise PointerError("target_invalid")
    target_fd = os.open(name, DIR_FLAGS, dir_fd=root_fd)
    try:
        _secure(os.fstat(target_fd), owner)
        ops_fd = os.open("ops", DIR_FLAGS, dir_fd=target_fd)
        try:
            _secure(os.fstat(ops_fd), owner)
            script = os.stat("restore-verify.sh", dir_fd=ops_fd, follow_symlinks=False)
            if not stat.S_ISREG(script.st_mode) or not script.st_mode & stat.S_IXUSR:
                raise PointerError("script_invalid")
            _secure(script, owner)
        finally:
            os.close(ops_fd)
    finally:
        os.close(target_fd)


def _current(root_fd: int, root: Path, owner: int) -> Path | None:
    try:
        info = os.stat(POINTER, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != owner:
        raise PointerError("pointer_invalid")
    name = os.readlink(POINTER, dir_fd=root_fd)
    _validate_target(root_fd, name, owner)
    return root / name


def _inhibited(root_fd: int) -> bool:
    try:
        os.stat(INHIBITION, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def inspect_pointer(
    root: Path, *, owner_uid: int = 0, allow_inhibited: bool = False
) -> Path:
    """Resolve only a relative, versioned direct child of the trusted root."""
    try:
        with _root_directory(root, owner_uid) as fd:
            if not allow_inhibited and _inhibited(fd):
                raise PointerError("restore_inhibited")
            current = _current(fd, root, owner_uid)
    except OSError as error:
        raise PointerError("pointer_unavailable") from error
    if current is None:
        raise PointerError("pointer_missing")
    return current


def inhibit_restore(root: Path, *, owner_uid: int = 0) -> None:
    """Persist the stop condition before migration, even if the lock owner dies."""
    with _root_directory(root, owner_uid) as fd:
        marker = os.open(
            INHIBITION,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=fd,
        )
        try:
            os.fsync(marker)
        finally:
            os.close(marker)
        os.fsync(fd)


def clear_restore_inhibition(
    root: Path, *, expected_current: Path, owner_uid: int = 0
) -> None:
    """Caller must have confirmed the actual schema and the expected runtime."""
    with _root_directory(root, owner_uid) as fd:
        if _current(fd, root, owner_uid) != expected_current:
            raise PointerError("current_changed")
        info = os.stat(INHIBITION, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise PointerError("inhibition_invalid")
        _secure(info, owner_uid)
        os.unlink(INHIBITION, dir_fd=fd)
        os.fsync(fd)


def activate_pointer(
    root: Path,
    *,
    expected_current: Path | None,
    target: Path,
    approved_revision: str,
    owner_uid: int = 0,
) -> None:
    """Switch a checked target; caller must hold backup/restore lock and approvals.

    This low-level function does not authenticate an approval, validate a
    migration graph, acquire the orchestration lock, or repair an invalid pin.
    """
    if target.parent != root or not FULL_REVISION.fullmatch(approved_revision):
        raise PointerError("target_invalid")
    expected_name = (
        LEGACY_NAME
        if target.name == LEGACY_NAME and approved_revision == LEGACY_REVISION
        else f"restore-runtime-{approved_revision[:12]}"
    )
    if target.name != expected_name:
        raise PointerError("revision_mismatch")
    with _root_directory(root, owner_uid) as fd:
        _validate_target(fd, target.name, owner_uid)
        if _current(fd, root, owner_uid) != expected_current:
            raise PointerError("current_changed")
        if target == expected_current:
            return
        pending = f".restore-runtime-pending-{secrets.token_hex(16)}"
        os.symlink(target.name, pending, dir_fd=fd)
        try:
            os.replace(pending, POINTER, src_dir_fd=fd, dst_dir_fd=fd)
        except OSError:
            os.unlink(pending, dir_fd=fd)
            raise
        os.fsync(fd)


def pointer_action(
    current_runtime_head: str,
    live_schema: str,
    requested_head: str,
    verified_next_head: str | None,
) -> PointerAction:
    """Compare heads after approved lineage verification; never infer paths."""
    if live_schema == requested_head:
        if current_runtime_head == live_schema:
            return "keep"
        return "activate" if verified_next_head == live_schema else "stop"
    if current_runtime_head == live_schema and verified_next_head == requested_head:
        return "migrate_then_activate"
    return "stop"


def main(*, owner_uid: int = 0) -> int:
    parser = argparse.ArgumentParser(
        description="Read a trusted restore-runtime pointer."
    )
    parser.add_argument("--root", type=Path, default=Path("/usr/local/lib/finanse"))
    args = parser.parse_args()
    try:
        print(inspect_pointer(args.root, owner_uid=owner_uid))
    except PointerError as error:
        parser.exit(2, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
