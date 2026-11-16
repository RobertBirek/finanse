"""Deterministic whole-file sharding; no database or application imports."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import TypedDict


class CollectedTest(TypedDict):
    nodeid: str
    integration: bool
    migration: bool
    proxy: bool


class Manifest(TypedDict):
    version: int
    commit: str
    inventory: list[CollectedTest]
    groups: dict[str, list[str]]
    digest: str


GROUPS = ("legacy", "proxy", *(f"ordinary-{i}" for i in range(1, 7)))
PROXY_FILES = frozenset(
    {
        "tests/test_documents/test_proxy_upload.py",
        "tests/test_documents/test_parser_container.py",
        "tests/test_document_hardening.py",
    }
)
LEGACY_FILES = frozenset(
    {
        "tests/test_identity/test_sessions.py",
        "tests/test_documents/test_lifecycle_migration.py",
        "tests/test_documents/test_retry_migration.py",
        "tests/test_documents/test_vision_migration.py",
        "tests/test_finance/test_credit_card_migration.py",
        "tests/test_finance/test_ui_migration.py",
        "tests/test_finance/test_credit_card_accounts.py",
        "tests/test_finance/test_category_tree_apply.py",
        "tests/test_finance/test_category_tree_guard.py",
        "tests/test_finance/test_entity_colors.py",
    }
)


def manifest_digest(manifest: Manifest) -> str:
    payload = {k: v for k, v in manifest.items() if k != "digest"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def check_inventory(rows: list[CollectedTest]) -> None:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Empty or invalid inventory")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"nodeid", "integration", "migration", "proxy"}:
            raise ValueError("Invalid inventory row")
        node = row["nodeid"]
        if not isinstance(node, str) or not node.startswith("tests/") or "::" not in node:
            raise ValueError("Invalid test ID")
        if node in seen or any(
            type(row[key]) is not bool for key in ("integration", "migration", "proxy")
        ):
            raise ValueError("Duplicate ID or invalid marker")
        seen.add(node)


def build_manifest(rows: list[CollectedTest], commit: str) -> Manifest:
    check_inventory(rows)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected exact Git SHA")
    by_file: dict[str, list[CollectedTest]] = defaultdict(list)
    for row in rows:
        if not row["proxy"] or row["nodeid"].split("::", 1)[0] in PROXY_FILES:
            by_file[row["nodeid"].split("::", 1)[0]].append(row)
    legacy = set(LEGACY_FILES) | {
        filename for filename, items in by_file.items() if any(r["migration"] for r in items)
    }
    ordinary = {
        filename: items
        for filename, items in by_file.items()
        if filename not in legacy and filename not in PROXY_FILES
    }
    count = sum(len(items) for items in ordinary.values())
    integrations = sum(r["integration"] for items in ordinary.values() for r in items)

    def weight(items: list[CollectedTest]) -> int:
        return sum(r["integration"] for r in items) * count + len(items) * integrations

    assigned = {filename: "legacy" for filename in by_file if filename in legacy}
    assigned.update({filename: "proxy" for filename in by_file if filename in PROXY_FILES})
    loads = [0] * 6
    for filename, items in sorted(ordinary.items(), key=lambda pair: (-weight(pair[1]), pair[0])):
        index = min(range(6), key=lambda i: (loads[i], i))
        assigned[filename] = f"ordinary-{index + 1}"
        loads[index] += weight(items)
    groups: dict[str, list[str]] = {group: [] for group in GROUPS}
    for row in rows:
        filename = row["nodeid"].split("::", 1)[0]
        if not row["proxy"] or filename in PROXY_FILES:
            groups[assigned[filename]].append(row["nodeid"])
    manifest: Manifest = {
        "version": 1,
        "commit": commit,
        "inventory": rows,
        "groups": groups,
        "digest": "",
    }
    manifest["digest"] = manifest_digest(manifest)
    return manifest
