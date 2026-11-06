"""Neutral test data and private temp bundles, never the user's actual taxonomy."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_DNS, UUID, uuid5


def uid(index: int) -> UUID:
    return uuid5(NAMESPACE_DNS, f"category-tree-synthetic-v1/{index}")


def cases() -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/category_tree_synthetic.json").read_text()
    )
    original = {r[0]: (r[3], r[1]) for r in fixture["nodes"]}
    target = {r[0]: (r[4], r[5]) for r in fixture["nodes"]}
    target.update({r[0]: (r[1], r[2]) for r in fixture["new_nodes"]})

    def path(table: dict[Any, Any], key: Any) -> str:
        name, parent = table[key]
        return path(table, parent) + " / " + name if parent is not None else name

    source = {
        "read_only": True,
        "rolled_back": True,
        "schema": "7b57f2f0bde6",
        "observed_at": "2000-01-01T00:00:00Z",
        "categories": [
            {
                "id": str(uid(r[0])),
                "parent_id": str(uid(r[1])) if r[1] is not None else None,
                "name": r[3],
                "type": r[2],
                "source": "actual",
                "is_active": True,
                "transaction_count": 0,
            }
            for r in fixture["nodes"]
        ],
    }
    mapping = {
        "status": "proposal_not_approved_not_executed",
        "snapshot_sha256": "",  # set when serializing
        "source_count": 65,
        "target_count": 79,
        "action_counts": dict(Counter(r[6] for r in fixture["nodes"])),
        "new_expense_nodes": [path(target, r[0]) for r in fixture["new_nodes"]],
        "mapping": [
            {
                "source_id": str(uid(r[0])),
                "type": r[2],
                "source_path": path(original, r[0]),
                "target_path": path(target, r[0]),
                "action": r[6],
                "reason": "Synthetic test case",
                "preserve_id": True,
                "source": "actual",
                "is_active": True,
                "direct_transaction_count": 0,
            }
            for r in fixture["nodes"]
        ],
        "blocked_automatic_actions": [
            "delete",
            "merge",
            "deactivate",
            "change_type",
            "rewrite_postings",
            "FX_conversion",
            "loan_account_creation",
            "enable_marker_or_consent",
            "historical_rule_scan",
        ],
    }
    return source, mapping


def write_bundle(
    directory: Path, source: dict[str, Any], mapping: dict[str, Any]
) -> dict[str, str]:
    directory.mkdir(mode=0o700, exist_ok=True)
    data = {
        "source-private.json": json.dumps(source).encode(),
        "proposal-private.md": b"# Neutral test proposal\n",
    }
    mapping["snapshot_sha256"] = hashlib.sha256(data["source-private.json"]).hexdigest()
    data["mapping-private.json"] = json.dumps(mapping).encode()
    data["prepare_design.py"] = b"raise RuntimeError('MUST NEVER EXECUTE')\n"
    data["verification-private.json"] = b'{"passed":true}\n'
    for name, value in data.items():
        p = directory / name
        p.write_bytes(value)
        p.chmod(0o600)
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in data.items()}
    manifest = directory / "manifest-private.json"
    manifest.write_text(json.dumps({"files": hashes, "status": "test"}))
    manifest.chmod(0o600)
    return {
        "expected_source_sha": hashes["source-private.json"],
        "expected_mapping_sha": hashes["mapping-private.json"],
        "expected_proposal_sha": hashes["proposal-private.md"],
    }
