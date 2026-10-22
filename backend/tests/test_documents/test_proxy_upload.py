"""Run explicitly: pytest tests/test_documents/test_proxy_upload.py -m proxy.

Uses only a disposable localhost container, never the production proxy.
"""

import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest


@pytest.mark.proxy
def test_nginx_accepts_2mib_but_rejects_over_21mib(tmp_path):
    source = Path(__file__).resolve().parents[3] / "frontend/nginx.conf"
    config = source.read_text().replace("http://backend:8000", "http://127.0.0.1:8000")
    config += "\nserver { listen 8000; client_max_body_size 0; location / { return 204; } }\n"
    path = tmp_path / "default.conf"
    path.write_text(config)
    name = "document-proxy-test-" + uuid.uuid4().hex[:10]
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            "127.0.0.1::80",
            "-v",
            f"{path}:/etc/nginx/conf.d/default.conf:ro",
            "nginx:alpine",
        ],
        check=True,
        capture_output=True,
    )
    try:
        port = (
            subprocess.check_output(["docker", "port", name, "80/tcp"], text=True)
            .strip()
            .split(":")[-1]
        )
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            for attempt in range(50):
                try:
                    response = client.get("/api/documents/upload")
                    if response.status_code == 204:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Disposable proxy did not become ready")
            assert (
                client.post("/api/documents/upload", content=b"x" * (2 * 1024**2)).status_code
                == 204
            )
            assert (
                client.post("/api/documents/upload", content=b"x" * (21 * 1024**2 + 1)).status_code
                == 413
            )
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)
