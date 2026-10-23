"""Fail closed on runtime path mistakes; never repair ownership or permissions."""

import os
import stat
import tempfile
from pathlib import Path


def validate_directory(path: Path, uid: int, gid: int) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (info.st_uid, info.st_gid) != (uid, gid):
        raise ValueError(f"Unexpected runtime directory type/owner: {path}")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError(f"Runtime directory must have mode 0700: {path}")
    # Probe effective access as the actual runtime identity, without chmod/chown.
    with tempfile.TemporaryFile(dir=path) as probe:
        probe.write(b"runtime-check")
        probe.flush()


def main() -> None:
    uid, gid = os.getuid(), os.getgid()
    if (uid, gid) != (1001, 1001):
        raise ValueError("Stirling requires UID/GID 1001:1001")
    if os.environ.get("HOME") != "/tmp/stirling-home":
        raise ValueError("Unexpected HOME")
    for root in ("/configs", "/logs", "/pipeline"):
        validate_directory(Path(root), uid, gid)
    for name in (
        "/tmp/stirling-home",
        "/tmp/stirling-pdf",
        "/tmp/stirling-pdf/heap_dumps",
        "/configs/heap_dumps",
        "/configs/cache",
    ):
        path = Path(name)
        path.mkdir(mode=0o700, exist_ok=True)
        validate_directory(path, uid, gid)


if __name__ == "__main__":
    main()
