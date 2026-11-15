"""Explicit CI-only plugin. It never changes fixtures, assertions or test outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any, TextIO, cast

import pytest

from ci_tools.partition import CollectedTest, Manifest, build_manifest
from ci_tools.results import validate_manifest

_GZIP_ID_SCOPE = pytest.StashKey[bool]()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> Iterator[None]:
    config = metafunc.config
    previous = config.stash.get(_GZIP_ID_SCOPE, False)
    config.stash[_GZIP_ID_SCOPE] = (
        metafunc.definition.path == config.rootpath / "tests/test_documents/test_ocr_client.py"
        and metafunc.function.__name__ == "test_ocr_stream_rejects_expansion_and_closes"
    )
    try:
        yield
    finally:
        config.stash[_GZIP_ID_SCOPE] = previous


def pytest_make_parametrize_id(val: object, argname: str, config: pytest.Config) -> str | None:
    # gzip.compress() defaults to current mtime. Hash all payload/header bytes
    # except that timestamp; do not alter the actual value delivered to the test.
    if (
        config.stash.get(_GZIP_ID_SCOPE, False)
        and argname == "data"
        and isinstance(val, bytes)
        and len(val) >= 10
        and val[:4] == b"\x1f\x8b\x08\x00"
    ):
        normalized = val[:4] + b"\0" * 4 + val[8:]
        return "gzip-data-" + hashlib.sha256(normalized).hexdigest()
    return None


def sanitize(text: str, secrets: list[str]) -> str:
    text = re.sub(
        r"(?:postgresql(?:\+asyncpg)?|https?|redis)://[^\s\"'<>]+", "[URL REDACTED]", text
    )
    for value in sorted(set(secrets), key=len, reverse=True):
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def pytest_addoption(parser: pytest.Parser) -> None:
    for name in ("collect", "commit", "manifest", "group", "journal"):
        parser.addoption(f"--ci-{name}", default=None)


def git_commit(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


class Recorder:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.rows: list[CollectedTest] = []
        self.manifest: Manifest | None = None
        self.stream: TextIO | None = None
        self._files = ExitStack()
        config.add_cleanup(self._files.close)
        self.secrets = [
            value
            for key, value in os.environ.items()
            if any(part in key.upper() for part in ("SECRET", "PASSWORD", "TOKEN", "API_KEY"))
        ]
        destination = config.getoption("ci_journal")
        if destination:
            # Lifetime spans hooks; ExitStack closes on pytest configuration cleanup.
            self.stream = self._files.enter_context(
                Path(destination).open("x", encoding="utf-8")  # noqa: SIM115
            )

    def emit(self, event: dict[str, Any]) -> None:
        if self.stream is not None:
            self.stream.write(json.dumps(event) + "\n")
            self.stream.flush()

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        self.rows = [
            CollectedTest(
                nodeid=item.nodeid,
                integration=item.get_closest_marker("integration") is not None,
                migration=item.get_closest_marker("migration") is not None,
                proxy=item.get_closest_marker("proxy") is not None,
            )
            for item in items
        ]
        source = config.getoption("ci_manifest")
        if not source:
            return
        try:
            manifest = cast(Manifest, json.loads(Path(source).read_text()))
            validate_manifest(manifest)
            if manifest["commit"] != git_commit(config.rootpath):
                raise ValueError("Different checkout")
            if {r["nodeid"]: r for r in self.rows} != {
                r["nodeid"]: r for r in manifest["inventory"]
            }:
                raise ValueError("Collection drift")
            group = config.getoption("ci_group")
            selected = manifest["groups"][group]
        except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
            raise pytest.UsageError("CI manifest rejected") from exc
        wanted = set(selected)
        omitted = [item for item in items if item.nodeid not in wanted]
        items[:] = [item for item in items if item.nodeid in wanted]
        config.hook.pytest_deselected(items=omitted)
        self.manifest = manifest
        self.emit(
            {
                "event": "header",
                "version": 1,
                "commit": manifest["commit"],
                "digest": manifest["digest"],
                "group": group,
                "selected": selected,
            }
        )

    def pytest_runtest_logstart(self, nodeid: str, location: tuple[str, int | None, str]) -> None:
        self.emit({"event": "begin", "nodeid": nodeid, "retry": 0})

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.emit(
            {
                "event": "phase",
                "nodeid": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "duration": report.duration,
                "retry": getattr(report, "rerun", 0),
                "wasxfail": hasattr(report, "wasxfail"),
                "traceback": sanitize(str(report.longrepr or ""), self.secrets),
            }
        )

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        destination = self.config.getoption("ci_collect")
        if destination and int(exitstatus) == 0:
            commit = git_commit(self.config.rootpath)
            if self.config.getoption("ci_commit") != commit:
                raise pytest.UsageError("Collection commit mismatch")
            manifest = build_manifest(self.rows, commit)
            validate_manifest(manifest)
            Path(destination).write_text(json.dumps(manifest, indent=2) + "\n")
        self.emit({"event": "end", "exit": int(exitstatus)})
        if self.stream is not None:
            self.stream.close()


def pytest_configure(config: pytest.Config) -> None:
    collect = config.getoption("ci_collect")
    run = config.getoption("ci_manifest")
    if not collect and not run:
        raise pytest.UsageError("CI plugin requires an explicit mode")
    if bool(collect) == bool(run):
        raise pytest.UsageError("Choose collection or execution")
    # Fail closed if default marker semantics change; never guess a new target.
    if config.getini("addopts") != ["-m", "not proxy"]:
        raise pytest.UsageError(f"Unsupported default selection in {config.rootpath.name}")
    if config.option.markexpr != "not proxy or proxy":
        raise pytest.UsageError("CI requires explicit all-items collection")
    if collect and (not config.option.collectonly or not config.getoption("ci_commit")):
        raise pytest.UsageError("Manifest export requires collect-only and commit")
    if run and (
        config.option.collectonly
        or not config.getoption("ci_group")
        or not config.getoption("ci_journal")
    ):
        raise pytest.UsageError("Execution requires group and journal")
    if hasattr(config.option, "numprocesses") and config.option.numprocesses:
        raise pytest.UsageError("Shared-database parallelism is forbidden")
    config.pluginmanager.register(Recorder(config), "advisor-ci-recorder")
