"""Exercise real subprocess exits/deadlines and artifact failures."""

import json
import sys
from pathlib import Path

import pytest

from tests.test_ci_tools.test_reporting import evidence


def test_child_nonzero_and_timeout_propagate(tmp_path):
    from ci_tools.runner import execute

    assert execute([sys.executable, "-c", "raise SystemExit(7)"], tmp_path / "bad", 3) == 7
    assert (
        execute([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path / "slow", 0.5)
        == 124
    )
    receipt = json.loads((tmp_path / "slow/process.json").read_text())
    assert receipt["timed_out"] is True
    assert receipt["seconds"] < 2


def test_runner_sanitizes_child_output(tmp_path, monkeypatch):
    from ci_tools.runner import execute

    monkeypatch.setenv("SECRET_KEY", "literal-secret-for-test")
    execute([sys.executable, "-c", "print('literal-secret-for-test')"], tmp_path, 3)
    assert "literal-secret-for-test" not in (tmp_path / "run.log").read_text()


def write_artifacts(root: Path):
    m, journals = evidence()
    for group, events in journals.items():
        path = root / group
        path.mkdir()
        (path / "journal.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        (path / "process.json").write_text(
            json.dumps(
                {
                    "exit": 0,
                    "timed_out": False,
                    "commit": m["commit"],
                    "digest": m["digest"],
                    "group": group,
                }
            )
        )
        cases = "".join("<testcase name='ok'/>" for _ in m["groups"][group])
        (path / "junit.xml").write_text("<testsuite>" + cases + "</testsuite>")
        (path / "run.log").write_text("synthetic success\n")
    return m


@pytest.mark.parametrize(
    "mutation", ["none", "missing", "skip", "exit", "digest", "truncated", "xml", "missing_log"]
)
def test_gate_requires_all_jobs(tmp_path, mutation):
    from ci_tools.runner import verify_artifacts

    m = write_artifacts(tmp_path)
    target = tmp_path / "proxy"
    if mutation == "none":
        verify_artifacts(m, tmp_path)
        return
    if mutation == "missing":
        (target / "journal.jsonl").unlink()
    elif mutation == "skip":
        (target / "junit.xml").write_text("<testsuite><testcase><skipped/></testcase></testsuite>")
    elif mutation in {"exit", "digest"}:
        p = target / "process.json"
        r = json.loads(p.read_text())
        r[mutation] = 1 if mutation == "exit" else "other"
        p.write_text(json.dumps(r))
    elif mutation == "truncated":
        with (target / "journal.jsonl").open("a") as stream:
            stream.write("{")
    elif mutation == "xml":
        (target / "junit.xml").write_text("<testsuite>")
    else:
        (target / "run.log").unlink()
    with pytest.raises((ValueError, OSError)):
        verify_artifacts(m, tmp_path)


@pytest.mark.parametrize("status", ["success", "failure", "cancelled", "skipped"])
def test_required_job_status_cannot_be_hidden(status):
    from ci_tools.runner import check_job_status

    needs = {"backend_static": {"result": "success"}, "backend_tests": {"result": status}}
    if status == "success":
        check_job_status(needs)
    else:
        with pytest.raises(ValueError):
            check_job_status(needs)
    with pytest.raises(ValueError):
        check_job_status({"backend_static": {"result": "success"}})
