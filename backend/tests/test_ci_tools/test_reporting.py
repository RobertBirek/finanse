"""Gate rejects partial/foreign results even if a JUnit file looks green."""

import copy
import gzip
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ci_tools.partition import build_manifest
from tests.test_ci_tools.test_partition import rows


def test_gzip_timestamp_does_not_change_parameter_identity(pytestconfig):
    from ci_tools.pytest_plugin import pytest_generate_tests, pytest_make_parametrize_id

    a = gzip.compress(b"x" * 100, mtime=123)
    b = gzip.compress(b"x" * 100, mtime=456)
    changed = gzip.compress(b"other payload", mtime=123)
    context = pytest_generate_tests(
        SimpleNamespace(
            config=pytestconfig,
            definition=SimpleNamespace(
                path=pytestconfig.rootpath / "tests/test_documents/test_ocr_client.py"
            ),
            function=SimpleNamespace(__name__="test_ocr_stream_rejects_expansion_and_closes"),
        )
    )
    next(context)
    try:
        assert pytest_make_parametrize_id(a, "data", pytestconfig) == pytest_make_parametrize_id(
            b, "data", pytestconfig
        )
        assert pytest_make_parametrize_id(a, "data", pytestconfig) != pytest_make_parametrize_id(
            changed, "data", pytestconfig
        )
        assert pytest_make_parametrize_id(b"not gzip", "data", pytestconfig) is None
    finally:
        context.close()
    assert pytest_make_parametrize_id(a, "data", pytestconfig) is None


def evidence():
    m = build_manifest(rows(), "a" * 40)
    journals = {}
    for group, nodes in m["groups"].items():
        events = [
            {
                "event": "header",
                "version": 1,
                "commit": m["commit"],
                "digest": m["digest"],
                "group": group,
                "selected": nodes,
            }
        ]
        for node in nodes:
            events.append({"event": "begin", "nodeid": node, "retry": 0})
            for phase in ("setup", "call", "teardown"):
                events.append(
                    {
                        "event": "phase",
                        "nodeid": node,
                        "phase": phase,
                        "outcome": "passed",
                        "duration": 0.01,
                        "retry": 0,
                        "wasxfail": False,
                        "traceback": "",
                    }
                )
        events.append({"event": "end", "exit": 0})
        journals[group] = events
    return m, journals


def test_three_phases_required():
    from ci_tools.results import validate_results

    m, journals = evidence()
    validate_results(m, journals)
    journals["legacy"].pop(-2)
    with pytest.raises(ValueError):
        validate_results(m, journals)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_job",
        "truncated",
        "duplicate",
        "foreign",
        "commit",
        "digest",
        "retry",
        "skip",
        "xfail",
        "error",
        "exit",
        "no_begin",
        "order",
        "unknown_event",
    ],
)
def test_missing_job_or_truncated_journal_fails(mutation):
    from ci_tools.results import validate_results

    m, original = evidence()
    journals = copy.deepcopy(original)
    events = journals["ordinary-1"]
    if mutation == "missing_job":
        del journals["proxy"]
    elif mutation == "truncated":
        events.pop()
    elif mutation == "duplicate":
        events.insert(3, dict(events[2]))
    elif mutation == "foreign":
        events[2]["nodeid"] = "tests/foreign.py::test_other"
    elif mutation in {"commit", "digest"}:
        events[0][mutation] = "b" * 40
    elif mutation == "retry":
        events[2]["retry"] = 1
    elif mutation == "skip":
        events[2]["outcome"] = "skipped"
    elif mutation == "xfail":
        events[2]["wasxfail"] = True
    elif mutation == "error":
        events[2]["outcome"] = "failed"
        events[2]["traceback"] = "synthetic setup failure"
    elif mutation == "exit":
        events[-1]["exit"] = 1
    elif mutation == "no_begin":
        events.pop(1)
    elif mutation == "order":
        events[2], events[3] = events[3], events[2]
    else:
        events.insert(1, {"event": "ignored_failure"})
    with pytest.raises(ValueError):
        validate_results(m, journals)


def test_redaction_removes_dsn_and_literal_secret():
    from ci_tools.pytest_plugin import sanitize

    text = (
        "error postgresql+asyncpg://alice:private@127.0.0.1/db?token=private other synthetic-secret"
    )
    result = sanitize(text, ["synthetic-secret", "private"])
    assert "alice" not in result and "private" not in result and "synthetic-secret" not in result
    assert "error" in result


def test_plugin_records_real_setup_error_and_does_not_start_next(tmp_path):
    """Real pytest child, not a mocked report; cannot silently downgrade setup errors."""
    import json

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text(
        "[pytest]\naddopts = -m 'not proxy'\n"
        "markers =\n    integration: synthetic\n    migration: synthetic\n    proxy: synthetic\n"
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_failure.py").write_text(
        "import pytest\n"
        "@pytest.fixture\ndef broken():\n    raise RuntimeError('synthetic first setup error')\n"
        "def test_first(broken): pass\n"
        "def test_next(): raise AssertionError('must not start')\n"
    )
    for row in rows():
        filename, name = row["nodeid"].split("::")
        path = repo / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write("import pytest\n")
            for marker in ("integration", "migration", "proxy"):
                if row[marker]:
                    stream.write(f"@pytest.mark.{marker}\n")
            stream.write(f"def {name}(): pass\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "synthetic",
        ],
        check=True,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    # This deliberately partial journal is never submitted as full-suite success.
    m = build_manifest(
        rows()
        + [
            {
                "nodeid": f"tests/test_failure.py::test_{name}",
                "integration": False,
                "migration": False,
                "proxy": False,
            }
            for name in ("first", "next")
        ],
        commit,
    )
    group = next(
        k for k, values in m["groups"].items() if "tests/test_failure.py::test_first" in values
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(m))
    journal = tmp_path / "journal.jsonl"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-c",
            str(repo / "pytest.ini"),
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "-p",
            "ci_tools.pytest_plugin",
            "-m",
            "not proxy or proxy",
            "--ci-manifest",
            str(manifest),
            "--ci-group",
            group,
            "--ci-journal",
            str(journal),
        ],
        check=False,
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    reports = [e for e in events if e["event"] == "phase"]
    assert reports[0]["phase"] == "setup" and reports[0]["outcome"] == "failed"
    assert "first setup error" in reports[0]["traceback"]
    assert not any(e.get("nodeid", "").endswith("::test_next") for e in events)
    assert events[-1] == {"event": "end", "exit": 1}
