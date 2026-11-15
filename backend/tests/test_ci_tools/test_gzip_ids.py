"""Real pytest collections: unrelated gzip parameters retain their normal IDs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_normalization_only_known_ocr_case(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    target = root / "tests/test_documents"
    target.mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "id_hooks.py").write_text(
        "import json, os\nfrom pathlib import Path\n"
        "from ci_tools import pytest_plugin as impl\n"
        "pytest_make_parametrize_id = impl.pytest_make_parametrize_id\n"
        "if hasattr(impl, 'pytest_generate_tests'):\n"
        "    pytest_generate_tests = impl.pytest_generate_tests\n"
        "def pytest_collection_finish(session):\n"
        "    rows = {str(i.path.relative_to(session.config.rootpath)) + '::' + i.originalname: i.nodeid for i in session.items}\n"
        "    Path(os.environ['ID_RECORD']).write_text(json.dumps(rows))\n"
    )
    preamble = (
        "import gzip, os, pytest\n"
        "value = gzip.compress(b'x' * 100, mtime=int(os.environ['GZIP_MTIME']))\n"
    )
    test_body = (
        "    assert int.from_bytes(data[4:8], 'little') == int(os.environ['GZIP_MTIME'])\n"
        "    assert gzip.decompress(data) == b'x' * 100\n"
    )
    known = "test_ocr_stream_rejects_expansion_and_closes"
    (target / "test_ocr_client.py").write_text(
        preamble
        + f"@pytest.mark.parametrize('data', [value])\ndef {known}(data):\n"
        + test_body
        + "@pytest.mark.parametrize('data', [value])\ndef test_other(data):\n"
        + test_body
    )
    (target / "test_other.py").write_text(
        preamble + f"@pytest.mark.parametrize('data', [value])\ndef {known}(data):\n" + test_body
    )
    observed = []
    for mtime in (123, 456):
        record = root / f"ids-{mtime}.json"
        env = os.environ | {
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]) + ":" + str(root),
            "GZIP_MTIME": str(mtime),
            "ID_RECORD": str(record),
        }
        run = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-c",
                str(root / "pytest.ini"),
                "-q",
                "-x",
                "-p",
                "no:cacheprovider",
                "-p",
                "id_hooks",
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        observed.append(json.loads(record.read_text()))
    expected_stable = "tests/test_documents/test_ocr_client.py::" + known
    assert observed[0][expected_stable] == observed[1][expected_stable]
    assert "gzip-data-" in observed[0][expected_stable]
    for key in set(observed[0]) - {expected_stable}:
        assert observed[0][key] != observed[1][key], (
            f"Hook incorrectly changed unrelated case: {key}"
        )
