"""Linux-only runner for a trusted, private Compose snapshot."""

import ctypes
import hashlib
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

if __name__ != "__main__":
    from release_preflight_policy import PreflightInputError

# The sole Compose build qualified for this isolation profile.
ISOLATED_COMPOSE_SHA256 = (
    "9c0f3f21b463fbdd42afed3be203c1a65f0cd440c9b59c68785f35e78d2ebf6a"
)
_BIN = "/bin/compose"
_ENV = {
    "PATH": "/bin",
    "HOME": "/nonexistent",
    "LC_ALL": "C.UTF-8",
    "DOCKER_CONFIG": "/nonexistent",
    "DOCKER_HOST": "unix:///run/docker.sock",
}
_HELPER = Path(__file__).resolve()
_DENIED = (
    "socket",
    "socketpair",
    "io_uring_setup",
    "mount",
    "umount2",
    "pivot_root",
    "open_tree",
    "move_mount",
    "fsopen",
    "fsconfig",
    "fsmount",
    "fspick",
    "mount_setattr",
    "chroot",
    "unshare",
    "setns",
)


def _valid_argv(argv: tuple[str, ...]) -> bool:
    if type(argv) is not tuple or any(type(item) is not str for item in argv):
        return False
    if argv[-3:] == ("config", "--format", "json"):
        prefix = argv[:-3]
    elif argv[-2:] == ("up", "--help"):
        prefix = argv[:-2]
    else:
        return False
    if len(prefix) < 10 or len(prefix) % 2:
        return False
    flags = prefix[::2]
    if flags[:3] != ("--project-name", "--project-directory", "--env-file"):
        return False
    if any(flag != "-f" for flag in flags[3:]):
        return False
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", prefix[1])) and all(
        path.startswith("/")
        and not any(part in {"", ".", ".."} for part in path[1:].split("/"))
        and not any(char in path for char in "\x00\r\n$")
        for path in prefix[3::2]
    )


def _trusted_binary(root: Path) -> bool:
    if not root.is_absolute() or root.resolve(strict=True) != root:
        return False
    for directory in (root, root / "bin"):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            return False
    with os.fdopen(
        os.open(root / "bin/compose", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb"
    ) as stream:
        info = os.fstat(stream.fileno())
        return (
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and not info.st_mode & 0o7022
            and info.st_size <= 128 * 1024 * 1024
            and hashlib.file_digest(stream, "sha256").hexdigest()
            == ISOLATED_COMPOSE_SHA256
        )


def _checked(result: int) -> None:
    if result != 0:
        raise OSError("isolation setup failed")


def _child(root: Path, ready: int, argv: tuple[str, ...]) -> None:
    libc = ctypes.CDLL("libc.so.6")
    if ready < 3:
        raise OSError("invalid readiness descriptor")
    libc.close_range.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_int]
    if ready > 3:
        _checked(libc.close_range(3, ready - 1, 0))
    _checked(libc.close_range(ready + 1, ctypes.c_uint(-1).value, 0))
    if not _valid_argv(argv) or not _trusted_binary(root):
        raise OSError("invalid renderer inputs")
    sec = ctypes.CDLL("libseccomp.so.2")
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    cap_last = int(Path("/proc/sys/kernel/cap_last_cap").read_text())
    os.unshare(os.CLONE_NEWNET)
    os.chroot(root)
    os.chdir("/")
    os.setgroups([])
    _checked(libc.prctl(47, 4, 0, 0, 0))  # Clear ambient capabilities.
    for cap in range(cap_last + 1):
        _checked(libc.prctl(24, cap, 0, 0, 0))  # Drop bounding capabilities.
    os.setresgid(65534, 65534, 65534)
    os.setresuid(65534, 65534, 65534)
    # Explicitly clear both 32-bit words of effective, permitted and inheritable.
    header = (ctypes.c_uint32 * 2)(0x20080522, 0)  # Linux capability ABI v3.
    data = (ctypes.c_uint32 * 6)()
    _checked(libc.capset(header, data))
    _checked(libc.capget(header, data))
    if any(data):
        raise OSError("renderer retained capabilities")
    _checked(libc.prctl(38, 1, 0, 0, 0))  # no_new_privs.
    ctx = sec.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise OSError("seccomp initialization failed")
    for name in _DENIED:
        syscall = sec.seccomp_syscall_resolve_name(name.encode("ascii"))
        if syscall < 0:
            raise OSError("seccomp syscall unavailable")
        _checked(sec.seccomp_rule_add(ctx, 0x00050001, syscall, 0))  # EPERM
    _checked(sec.seccomp_load(ctx))
    os.write(ready, b"R")
    os.close(ready)
    os.execve(_BIN, [_BIN, *argv], _ENV)


def run_isolated_compose(
    root: Path, argv: tuple[str, ...], *, max_output_bytes: int
) -> str:
    """Run a closed command against an already verified, root-owned snapshot."""
    if (
        not isinstance(root, Path)
        or not _valid_argv(argv)
        or type(max_output_bytes) is not int
        or max_output_bytes < 1
    ):
        raise PreflightInputError("renderer_arguments_invalid")
    if sys.platform != "linux" or os.geteuid() != 0:
        raise PreflightInputError("renderer_setup_failed")
    deadline = time.monotonic() + 10
    process = None
    read_fd = write_fd = None
    try:
        if not _trusted_binary(root):
            raise PreflightInputError("renderer_setup_failed")
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(_HELPER),
                str(root),
                str(write_fd),
                *argv,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_ENV,
            cwd="/",
            start_new_session=True,
            pass_fds=(write_fd,),
        )
        os.close(write_fd)
        write_fd = None
        assert (
            process.stdin is not None
            and process.stdout is not None
            and process.stderr is not None
        )
        process.stdin.close()
        output = bytearray()
        ready = bytearray()
        count = 0
        with selectors.DefaultSelector() as selector:
            selector.register(read_fd, selectors.EVENT_READ, "status")
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PreflightInputError("renderer_timeout")
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fd, min(65536, max_output_bytes + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data == "status":
                        ready.extend(chunk)
                        if ready != b"R":
                            raise PreflightInputError("renderer_setup_failed")
                    else:
                        count += len(chunk)
                        if count > max_output_bytes:
                            raise PreflightInputError("renderer_output_limit")
                        if key.data == "stdout":
                            output.extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PreflightInputError("renderer_timeout")
        code = process.wait(timeout=remaining)
        if ready != b"R" or code == 125:
            raise PreflightInputError("renderer_setup_failed")
        if code:
            raise PreflightInputError("renderer_failed")
        return output.decode("utf-8")
    except subprocess.TimeoutExpired:
        raise PreflightInputError("renderer_timeout") from None
    except UnicodeError:
        raise PreflightInputError("renderer_failed") from None
    except PreflightInputError:
        raise
    except (OSError, ValueError):
        raise PreflightInputError("renderer_setup_failed") from None
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)
        if process is not None:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                raise PreflightInputError("renderer_cleanup_failed") from None


if __name__ == "__main__":
    try:
        _child(Path(sys.argv[1]), int(sys.argv[2]), tuple(sys.argv[3:]))
    except (OSError, ValueError, AttributeError):
        sys.exit(125)
