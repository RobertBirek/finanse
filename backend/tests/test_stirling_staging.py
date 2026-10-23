"""Explicit OCR gate: STIRLING_TEST_IMAGE=sha256:... pytest -m proxy <this file>."""

import hashlib
import json
import os
import subprocess
import time
import uuid
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont

COMPOSE = Path(__file__).resolve().parents[2] / "ops/stirling/staging.compose.yaml"


@pytest.mark.proxy
def test_actual_stirling_nonroot_ocr_and_shutdown(tmp_path):
    image = os.environ.get("STIRLING_TEST_IMAGE")
    if not image:
        pytest.skip("Explicit immutable STIRLING_TEST_IMAGE required for OCR staging")
    assert image.startswith("sha256:") or "@sha256:" in image
    for name in ("configs", "logs"):
        directory = tmp_path / name
        directory.mkdir(mode=0o700)
        os.chown(directory, 1001, 1001)
    project = "stirling-stage-" + uuid.uuid4().hex[:10]
    env = os.environ | {"STIRLING_STAGE_ROOT": str(tmp_path), "STIRLING_TEST_IMAGE": image}
    command = ["docker", "compose", "-p", project, "-f", str(COMPOSE)]

    def compose(*args):
        return subprocess.check_output(
            [*command, *args], env=env, stderr=subprocess.STDOUT, text=True
        )

    try:
        compose("up", "-d", "--no-build", "--pull", "never")
        container = compose("ps", "-aq", "stirling").strip()
        initial = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
        if not initial["State"]["Running"]:
            pytest.fail("Staging exited: " + compose("logs", "--tail", "80", "stirling"))
        network = initial["NetworkSettings"]["Networks"]
        assert len(network) == 1
        address = next(iter(network.values()))["IPAddress"]
        assert address
        with httpx.Client(
            base_url=f"http://{address}:8080", timeout=120, trust_env=False
        ) as client:
            last_probe = "not attempted"
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                state = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
                if not state["State"]["Running"]:
                    pytest.fail("Staging exited: " + compose("logs", "--tail", "80", "stirling"))
                try:
                    response = client.get("/api/v1/info/status", timeout=2)
                    last_probe = f"HTTP {response.status_code}: {response.text[:100]}"
                    if response.status_code == 200:
                        break
                except httpx.TransportError as error:
                    last_probe = str(error)
                time.sleep(1)
            else:
                internal = subprocess.run(
                    [
                        *command,
                        "exec",
                        "-T",
                        "stirling",
                        "curl",
                        "-sS",
                        "--max-time",
                        "3",
                        "-i",
                        "http://127.0.0.1:8080/api/v1/info/status",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                pytest.fail(
                    f"External probe: {last_probe}; internal: {internal.stdout[:400]} {internal.stderr[:200]}\n"
                    "Staging readiness timeout: " + compose("logs", "--tail", "80", "stirling")
                )
            assert state["Config"]["User"] == "1001:1001"
            assert compose("exec", "-T", "stirling", "id", "-u").strip() == "1001"
            assert compose("exec", "-T", "stirling", "id", "-g").strip() == "1001"
            identity = compose(
                "exec",
                "-T",
                "stirling",
                "python3",
                "-c",
                "from pathlib import Path; "
                "paths=[p for p in Path('/proc').glob('[0-9]*/status') if 'Name:\\tjava\\n' in p.read_text() or p.parent.name=='1']; "
                "assert len(paths)>=2; "
                "assert all(all(line.split()[1:]==['1001']*4 for line in p.read_text().splitlines() if line.startswith(('Uid:','Gid:'))) for p in paths); print('identities OK')",
            )
            assert "identities OK" in identity
            assert not state["HostConfig"]["PortBindings"]
            assert state["HostConfig"]["ReadonlyRootfs"]
            assert state["HostConfig"]["Memory"] == 2 * 1024**3
            assert state["HostConfig"]["PidsLimit"] == 256
            assert "ALL" in state["HostConfig"]["CapDrop"]
            assert "no-new-privileges:true" in state["HostConfig"]["SecurityOpt"]
            assert {m["Destination"] for m in state["Mounts"] if m["RW"]} <= {
                "/tmp",
                "/configs",
                "/pipeline",
                "/logs",
            }
            languages = compose("exec", "-T", "stirling", "tesseract", "--list-langs")
            pipeline = compose(
                "exec",
                "-T",
                "stirling",
                "sh",
                "-c",
                "readlink -f /app/pipeline; stat -c '%u:%g %a' /pipeline; grep ' /pipeline ' /proc/mounts",
            )
            assert "/pipeline\n1001:1001 700\n" in pipeline
            for option in ("tmpfs", "noexec", "nosuid", "size=16384k"):
                assert option in pipeline
            assert "pol" in languages.splitlines() and "eng" in languages.splitlines()
            canvas = Image.new("RGB", (1240, 1754), "white")
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 64)
            ImageDraw.Draw(canvas).text(
                (80, 160),
                "Faktura numer 12345\nInvoice total 250 PLN\nZażółć gęślą jaźń",
                font=font,
                fill="black",
            )

            def post(path, filename, content, data):
                response = client.post(
                    path,
                    files={"fileInput": (filename, content)},
                    data=data,
                    headers={"Accept-Encoding": "identity"},
                )
                assert response.status_code == 200, response.text[:500]
                assert response.headers.get("content-encoding", "identity") == "identity"
                return response.content

            for fmt in ("PNG", "JPEG", "PDF"):
                output = BytesIO()
                canvas.save(output, format=fmt, resolution=150)
                original = output.getvalue()
                before = hashlib.sha256(original).digest()
                pdf = (
                    original
                    if fmt == "PDF"
                    else post("/api/v1/convert/img/pdf", "scan." + fmt.lower(), original, {})
                )
                processed = post(
                    "/api/v1/misc/ocr-pdf",
                    "scan.pdf",
                    pdf,
                    {"languages": "pol,eng", "ocrType": "skip-text"},
                )
                text = post(
                    "/api/v1/convert/pdf/text", "scan.pdf", processed, {"outputFormat": "txt"}
                ).decode("utf-8")
                assert (
                    "12345" in text and "Invoice" in text and "Faktura" in text and "Zażółć" in text
                ), text[:500]
                assert hashlib.sha256(original).digest() == before
        started = time.monotonic()
        usage = compose("exec", "-T", "stirling", "du", "-sk", "/pipeline")
        assert int(usage.split()[0]) < 16 * 1024
        print("pipeline usage KiB:", usage.split()[0])
        compose("stop", "-t", "45", "stirling")
        assert time.monotonic() - started < 45
        state = json.loads(subprocess.check_output(["docker", "inspect", container]))[0]
        assert not state["State"]["OOMKilled"]
        assert state["State"]["ExitCode"] != 137
        assert subprocess.check_output(["docker", "diff", container], text=True).strip() == ""
    finally:
        compose("down", "--volumes", "--remove-orphans")
