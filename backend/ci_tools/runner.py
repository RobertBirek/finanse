"""Bounded CI subprocesses and fail-closed artifact gate; no database provisioning."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import Thread
from typing import Any, cast

from ci_tools.partition import GROUPS, Manifest
from ci_tools.results import validate_manifest, validate_results

BACKEND = Path(__file__).resolve().parent.parent


def execute(command: list[str], output: Path, timeout: float) -> int:
    from ci_tools.pytest_plugin import sanitize

    if timeout <= 0:
        raise ValueError("Positive deadline required")
    output.mkdir(parents=True, exist_ok=True)
    secrets = [
        value
        for key, value in os.environ.items()
        if any(part in key.upper() for part in ("SECRET", "PASSWORD", "TOKEN", "API_KEY"))
    ]
    start = time.monotonic()
    timed_out = False
    with (output / "run.log").open("x", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=BACKEND,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        assert process.stdout is not None

        def consume() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                log.write(sanitize(line, secrets))
                log.flush()

        reader = Thread(target=consume, daemon=True)
        reader.start()
        grace = min(5.0, timeout / 4)
        try:
            code = process.wait(timeout=max(0.01, timeout - grace))
        except subprocess.TimeoutExpired:
            timed_out = True
            for sig, wait in ((signal.SIGINT, grace / 2), (signal.SIGTERM, grace / 2)):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    process.wait(timeout=wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            code = 124
        finally:
            # Only the new, owned process group, including subprocesses after parent exit.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            reader.join(timeout=1)
            process.stdout.close()
        receipt = {
            "exit": code,
            "seconds": time.monotonic() - start,
            "timed_out": timed_out,
        }
        (output / "process.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return code


def verify_artifacts(manifest: Manifest, root: Path) -> None:
    validate_manifest(manifest)
    if {p.name for p in root.iterdir() if p.is_dir()} != set(GROUPS):
        raise ValueError("Missing or foreign result directory")
    journals: dict[str, list[dict[str, Any]]] = {}
    for group in GROUPS:
        directory = root / group
        for filename in ("journal.jsonl", "process.json", "junit.xml", "run.log"):
            path = directory / filename
            if not path.is_file() or path.is_symlink():
                raise ValueError("Missing or unsafe artifact")
        receipt = json.loads((directory / "process.json").read_text())
        if (
            type(receipt.get("exit")) is not int
            or receipt["exit"] != 0
            or receipt.get("timed_out") is not False
            or receipt.get("group") != group
            or receipt.get("commit") != manifest["commit"]
            or receipt.get("digest") != manifest["digest"]
        ):
            raise ValueError("Process failed or receipt belongs to another run")
        journals[group] = [
            json.loads(line) for line in (directory / "journal.jsonl").read_text().splitlines()
        ]
        try:
            xml = ET.parse(directory / "junit.xml")
        except ET.ParseError as exc:
            raise ValueError("Incomplete JUnit") from exc
        cases = xml.findall(".//testcase")
        if len(cases) != len(manifest["groups"][group]):
            raise ValueError("JUnit count mismatch")
        if any(
            case.find(kind) is not None
            for case in cases
            for kind in ("skipped", "failure", "error")
        ):
            raise ValueError("Unsuccessful JUnit case")
    validate_results(manifest, journals)


def check_job_status(needs: dict[str, Any]) -> None:
    if set(needs) != {"backend_static", "backend_tests"}:
        raise ValueError("Missing or foreign required job")
    if any(value.get("result") != "success" for value in needs.values()):
        raise ValueError("Required job failed, skipped or cancelled")


def checkout_commit() -> str:
    return subprocess.check_output(
        ["git", "-C", str(BACKEND), "rev-parse", "HEAD"], text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--commit", required=True)
    collect.add_argument("--timeout-seconds", type=float, default=40)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--group", choices=GROUPS, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--timeout-seconds", type=float, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--results", type=Path, required=True)
    verify.add_argument("--needs", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "verify":
            manifest = cast(Manifest, json.loads(args.manifest.read_text()))
            if manifest["commit"] != checkout_commit():
                raise ValueError("Foreign checkout")
            if args.needs is not None:
                check_job_status(json.loads(args.needs.read_text()))
            verify_artifacts(manifest, args.results)
            print("Complete backend target: all IDs passed, no SKIP or missing phases")
            return 0
        command = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-c",
            str(BACKEND / "pyproject.toml"),
            "-p",
            "no:cacheprovider",
            "-p",
            "ci_tools.pytest_plugin",
            "-m",
            "not proxy or proxy",
        ]
        if args.mode == "collect":
            if args.commit != checkout_commit() or args.output.exists():
                raise ValueError("Foreign commit or existing collection output")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            command += [
                "--collect-only",
                "-q",
                "--ci-collect",
                str(args.output.resolve()),
                "--ci-commit",
                args.commit,
            ]
            return execute(command, args.output.parent / "collection", args.timeout_seconds)
        manifest = cast(Manifest, json.loads(args.manifest.read_text()))
        validate_manifest(manifest)
        if manifest["commit"] != checkout_commit():
            raise ValueError("Foreign checkout")
        args.output.mkdir(parents=True, exist_ok=True)
        command += [
            "-vv",
            "--maxfail=1",
            "--tb=short",
            "--durations=30",
            "--ci-manifest",
            str(args.manifest.resolve()),
            "--ci-group",
            args.group,
            "--ci-journal",
            str((args.output / "journal.jsonl").resolve()),
            "--junitxml",
            str((args.output / "junit.xml").resolve()),
        ]
        code = execute(command, args.output, args.timeout_seconds)
        receipt_path = args.output / "process.json"
        receipt = json.loads(receipt_path.read_text())
        receipt.update(commit=manifest["commit"], digest=manifest["digest"], group=args.group)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        return code
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        # Avoid repr/traceback of untrusted data or environment-bearing exceptions.
        print(f"CI verification failed ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
