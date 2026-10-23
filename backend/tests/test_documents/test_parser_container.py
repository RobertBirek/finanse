"""Optional isolated container resource smoke test, run with -m proxy."""

import subprocess

import pytest


@pytest.mark.proxy
def test_nonroot_container_enforces_memory_and_cpu_limit():
    base = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "128m",
        "--cpus",
        "0.5",
        "--pids-limit",
        "32",
        "--user",
        "10001:10001",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--entrypoint",
        "python",
        "python:3.12-slim",
        "-c",
    ]
    memory = """import os,resource
assert os.getuid() == 10001
resource.setrlimit(resource.RLIMIT_AS, (64*1024**2, 64*1024**2))
try:
    bytearray(128*1024**2)
except MemoryError:
    print('memory bounded')
else:
    raise AssertionError('memory limit not enforced')
"""
    result = subprocess.run([*base, memory], capture_output=True, check=True, timeout=90)
    assert b"memory bounded" in result.stdout
    cpu = "import resource;resource.setrlimit(resource.RLIMIT_CPU,(1,1))\nwhile True: pass"
    result = subprocess.run([*base, cpu], capture_output=True, check=False, timeout=15)
    assert result.returncode == 137
