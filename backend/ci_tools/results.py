"""Fail-closed verification, independent of the shard-building algorithm."""

from __future__ import annotations

import re
from typing import Any

from ci_tools.partition import (
    GROUPS,
    LEGACY_FILES,
    PROXY_FILES,
    Manifest,
    check_inventory,
    manifest_digest,
)


def validate_manifest(manifest: Manifest) -> None:
    if set(manifest) != {"version", "commit", "inventory", "groups", "digest"}:
        raise ValueError("Invalid manifest fields")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("Unsupported manifest version")
    if not isinstance(manifest["commit"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", manifest["commit"]
    ):
        raise ValueError("Invalid commit")
    check_inventory(manifest["inventory"])
    if manifest["digest"] != manifest_digest(manifest):
        raise ValueError("Manifest digest mismatch")
    groups = manifest["groups"]
    if not isinstance(groups, dict) or set(groups) != set(GROUPS):
        raise ValueError("Missing or unknown group")
    rows = manifest["inventory"]
    target = {
        row["nodeid"]
        for row in rows
        if not row["proxy"] or row["nodeid"].split("::", 1)[0] in PROXY_FILES
    }
    legacy_files = set(LEGACY_FILES) | {
        row["nodeid"].split("::", 1)[0]
        for row in rows
        if row["migration"] and row["nodeid"] in target
    }
    seen: set[str] = set()
    owners: dict[str, str] = {}
    for group, nodes in groups.items():
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("Empty group")
        for node in nodes:
            if not isinstance(node, str) or node not in target or node in seen:
                raise ValueError("Duplicate, missing or foreign test ID")
            filename = node.split("::", 1)[0]
            if owners.setdefault(filename, group) != group:
                raise ValueError("Split file")
            expected = (
                "proxy"
                if filename in PROXY_FILES
                else "legacy"
                if filename in legacy_files
                else None
            )
            if expected is not None and group != expected:
                raise ValueError("Unsafe special-file assignment")
            if expected is None and not group.startswith("ordinary-"):
                raise ValueError("Unexpected special group")
            seen.add(node)
    if seen != target:
        raise ValueError("Incomplete target union")


def validate_results(manifest: Manifest, journals: dict[str, list[dict[str, Any]]]) -> None:
    validate_manifest(manifest)
    if set(journals) != set(GROUPS):
        raise ValueError("Missing or foreign job")
    for group, selected in manifest["groups"].items():
        events = journals[group]
        if not events or events[0] != {
            "event": "header",
            "version": 1,
            "commit": manifest["commit"],
            "digest": manifest["digest"],
            "group": group,
            "selected": selected,
        }:
            raise ValueError("Foreign or invalid journal header")
        if events[-1] != {"event": "end", "exit": 0}:
            raise ValueError("Missing end or nonzero exit")
        expected = set(selected)
        phases: dict[str, list[str]] = {}
        active: str | None = None
        for event in events[1:-1]:
            node = event.get("nodeid")
            if not isinstance(node, str) or node not in expected or event.get("retry") != 0:
                raise ValueError("Foreign ID or retry")
            if event.get("event") == "begin":
                if node in phases or active is not None:
                    raise ValueError("Duplicate or concurrent test")
                phases[node] = []
                active = node
            elif event.get("event") == "phase":
                if (
                    node != active
                    or event.get("outcome") != "passed"
                    or event.get("wasxfail") is not False
                ):
                    raise ValueError("Failure, SKIP, xfail or invalid phase")
                wanted = ("setup", "call", "teardown")
                done = phases[node]
                if len(done) >= 3 or event.get("phase") != wanted[len(done)]:
                    raise ValueError("Duplicate or out-of-order phase")
                done.append(event["phase"])
                if len(done) == 3:
                    active = None
            else:
                raise ValueError("Unexpected journal event")
        if set(phases) != expected or any(
            v != ["setup", "call", "teardown"] for v in phases.values()
        ):
            raise ValueError("Missing tests or phases")
