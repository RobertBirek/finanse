"""Explicit proxy tests: local images only, owned namespace, no host ports."""

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

OLD = "/api/documents/upload"
NEW = "/api/finance/imports/00000000-0000-0000-0000-000000000001/sources"
CLIENT = """
import http.client,json,os,time
os.environ.clear()
for attempt in range(50):
    try:
        c=http.client.HTTPConnection('127.0.0.1',80,timeout=2)
        c.request('GET','/api/health'); r=c.getresponse();r.read();c.close()
        if r.status==204: break
    except OSError: pass
    time.sleep(0.1)
else: raise RuntimeError('isolated nginx not ready')
rows=[]
paths=['/api/documents/upload','/api/documents/upload/',
 '/api/finance/imports/00000000-0000-0000-0000-000000000001/sources',
 '/api/finance/imports/00000000-0000-0000-0000-000000000001/sources/']
for path in paths+['/api/health','/api/finance/accounts']:
    sizes=[2*1024*1024,21*1024*1024+1] if path in paths else [2*1024*1024]
    for size in sizes:
        c=http.client.HTTPConnection('127.0.0.1',80,timeout=20)
        try:
            try:c.request('POST',path,body=b'x'*size,headers={'Connection':'close'})
            except (BrokenPipeError,ConnectionResetError): pass
            r=c.getresponse();r.read()
            rows.append({'path':path,'bytes':size,'status':r.status})
        finally:c.close()
print(json.dumps(rows))
"""


def docker(*args: str) -> str:
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.PIPE, timeout=90
    ).strip()


@pytest.fixture(scope="module")
def proxy_results(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, str | int]]:
    nginx = os.getenv("FINANSE_PROXY_TEST_NGINX_IMAGE", "nginx:alpine")
    python = os.getenv("FINANSE_PROXY_TEST_PYTHON_IMAGE", "python:3.12-alpine")
    # Resolve only installed images; no pulls or production container interactions.
    images = {
        s: json.loads(docker("image", "inspect", i))[0]["Id"]
        for s, i in [("nginx", nginx), ("python", python)]
    }
    token = uuid4().hex
    path = tmp_path_factory.mktemp("owned-proxy") / "default.conf"
    source = Path(__file__).resolve().parents[3] / "frontend/nginx.conf"
    path.write_text(
        source.read_text().replace("http://backend:8000", "http://127.0.0.1:8000")
        + "\nserver { listen 127.0.0.1:8000; client_max_body_size 0;"
        " location / { return 204; } }\n"
    )
    owned: list[tuple[str, str, str]] = []
    try:
        cid = docker(
            "create",
            "--pull=never",
            "--name",
            "finanse-proxy-" + token,
            "--label",
            "advisor.proxy.test=" + token,
            "--network",
            "none",
            "--mount",
            f"type=bind,src={path},dst=/etc/nginx/conf.d/default.conf,readonly",
            "--entrypoint",
            "nginx",
            images["nginx"],
            "-g",
            "daemon off;",
        )
        owned.append((cid, "none", images["nginx"]))
        docker("start", cid)
        client = docker(
            "create",
            "--pull=never",
            "--name",
            "finanse-proxy-client-" + token,
            "--label",
            "advisor.proxy.test=" + token,
            "--network",
            "container:" + cid,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "10001:10001",
            "--entrypoint",
            "python",
            images["python"],
            "-I",
            "-B",
            "-c",
            CLIENT,
        )
        owned.append((client, "container:" + cid, images["python"]))
        result = docker("start", "-a", client)
        state = json.loads(docker("inspect", client))[0]["State"]
        assert not state["Running"] and state["ExitCode"] == 0
        rows = json.loads(result)
        assert len(rows) == 10
        yield rows
    finally:
        for identity, network, image in reversed(owned):
            info = json.loads(docker("inspect", identity))[0]
            assert info["Id"] == identity and info["Image"] == image
            assert info["Config"]["Labels"]["advisor.proxy.test"] == token
            assert info["HostConfig"]["NetworkMode"] == network
            assert not info["HostConfig"]["PortBindings"]
            if info["State"]["Running"]:
                docker("stop", "--time", "10", identity)
            assert not json.loads(docker("inspect", identity))[0]["State"]["Running"]
            docker("rm", identity)
            assert not docker("ps", "-aq", "--no-trunc", "--filter", "id=" + identity)


@pytest.mark.proxy
@pytest.mark.parametrize("upload_path", [OLD, OLD + "/", NEW, NEW + "/"])
def test_upload_2mib_reaches_upstream_and_over_21mib_is_rejected(
    proxy_results: list[dict[str, str | int]], upload_path: str
) -> None:
    rows = [row for row in proxy_results if row["path"] == upload_path]
    assert [(r["bytes"], r["status"]) for r in rows] == [
        (2 * 1024**2, 204),
        (21 * 1024**2 + 1, 413),
    ]


@pytest.mark.proxy
@pytest.mark.parametrize("path", ["/api/health", "/api/finance/accounts"])
def test_non_upload_api_keeps_small_body_limit(
    proxy_results: list[dict[str, str | int]], path: str
) -> None:
    assert [r["status"] for r in proxy_results if r["path"] == path] == [413]
