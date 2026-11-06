"""The compiler must reject unsafe category changes before a DB is involved."""

import importlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from tests.test_finance.category_tree_cases import cases, uid, write_bundle


def operator() -> Any:
    return importlib.import_module("scripts.category_tree_manifest")


def compiled(tmp_path: Path, source: dict[str, Any], mapping: dict[str, Any]) -> Any:
    api = operator()
    hashes = write_bundle(tmp_path, source, mapping)
    return api.compile_tree(api.load_bundle(tmp_path, **hashes))


def test_complete_fixture_has_thirty_minimal_updates_and_fourteen_creates(tmp_path: Path) -> None:
    plan = compiled(tmp_path, *cases())
    assert len(plan.patches) == 30
    assert len(plan.creates) == 14
    assert sum(p.name is not None for p in plan.patches) == 19
    assert sum(p.parent_changed for p in plan.patches) == 21
    assert len(plan.expected_paths) == 79
    assert len(plan.hold_ids) == 11
    assert len(plan.keep_ids) == 16
    assert not ({p.id for p in plan.patches} & (plan.hold_ids | plan.keep_ids))
    assert plan.expected_paths[uid(13)] == "T10 / S13"


def test_ancestor_rename_does_not_patch_eight_unchanged_children(tmp_path: Path) -> None:
    plan = compiled(tmp_path, *cases())
    patched = {p.id for p in plan.patches}
    for index in [5, 6, 13, 40, 41, 43, 48, 58]:
        assert uid(index) not in patched
    assert plan.expected_paths[uid(5)] == "T25 / S5"


def test_compiled_plan_binds_snapshot_schema(tmp_path: Path) -> None:
    assert compiled(tmp_path, *cases()).schema_revision == "7b57f2f0bde6"


def test_hold_keeps_name_parent_and_path(tmp_path: Path) -> None:
    plan = compiled(tmp_path, *cases())
    assert uid(56) in plan.hold_ids
    assert plan.expected_paths[uid(56)] == "S1 / S56"
    source, mapping = cases()
    mapping["mapping"][56]["target_path"] = "N0 / S56"
    with pytest.raises(operator().CategoryTreeError):
        compiled(tmp_path, source, mapping)


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "duplicate", "action", "preserve", "type", "delete"]
)
def test_rejects_missing_extra_duplicate_source(tmp_path: Path, mutation: str) -> None:
    source, mapping = cases()
    if mutation == "missing":
        mapping["mapping"].pop()
    elif mutation == "extra":
        row = dict(mapping["mapping"][0], source_id=str(uuid4()))
        mapping["mapping"].append(row)
    elif mutation == "duplicate":
        mapping["mapping"].append(mapping["mapping"][0].copy())
    elif mutation == "action":
        mapping["mapping"][0]["action"] = "DELETE"
    elif mutation == "preserve":
        mapping["mapping"][0]["preserve_id"] = False
    elif mutation == "type":
        mapping["mapping"][0]["type"] = "income"
    else:
        mapping["mapping"][0]["delete"] = True
    with pytest.raises(operator().CategoryTreeError):
        compiled(tmp_path, source, mapping)


@pytest.mark.parametrize(
    "mutation", ["cross_type", "cycle", "orphan", "duplicate_id", "source_label"]
)
def test_rejects_cross_type_parent_cycle_and_orphan(tmp_path: Path, mutation: str) -> None:
    source, mapping = cases()
    if mutation == "cross_type":
        source["categories"][0]["parent_id"] = str(uid(63))
    elif mutation == "cycle":
        source["categories"][1]["parent_id"] = str(uid(0))
    elif mutation == "orphan":
        source["categories"][0]["parent_id"] = str(uuid4())
    elif mutation == "duplicate_id":
        source["categories"][0]["id"] = str(uid(1))
    else:
        mapping["mapping"][0]["source_path"] = "Unapproved source path"
    with pytest.raises(operator().CategoryTreeError):
        compiled(tmp_path, source, mapping)


@pytest.mark.parametrize(
    "mutation", ["collision", "duplicate", "third_level", "missing_parent", "target_collision"]
)
def test_rejects_new_node_collision_and_third_level(tmp_path: Path, mutation: str) -> None:
    source, mapping = cases()
    if mutation == "collision":
        mapping["new_expense_nodes"][0] = "S1"
    elif mutation == "duplicate":
        mapping["new_expense_nodes"][0] = "N1"
    elif mutation == "third_level":
        mapping["new_expense_nodes"].append("N6 / N7 / deep")
    elif mutation == "missing_parent":
        mapping["mapping"][0]["target_path"] = "Missing / T0"
    else:
        mapping["mapping"][0]["target_path"] = mapping["mapping"][8]["target_path"]
    with pytest.raises(operator().CategoryTreeError):
        compiled(tmp_path, source, mapping)


def test_fingerprint_ignores_observation_not_names_source_or_active(tmp_path: Path) -> None:
    api = operator()
    source, mapping = cases()
    bundle = api.load_bundle(tmp_path, **write_bundle(tmp_path, source, mapping))
    before = api.tree_fingerprint(bundle.source)
    assert before == api.tree_fingerprint(tuple(reversed(bundle.source)))
    for field, value in [
        ("name", "Different"),
        ("source", "manual"),
        ("is_active", False),
        ("parent_id", uid(16)),
    ]:
        rows = list(bundle.source)
        rows[0] = rows[0].model_copy(update={field: value})
        assert api.tree_fingerprint(rows) != before
    source["observed_at"] = "2100-01-01"
    source["categories"][0]["transaction_count"] = 999
    updated = api.load_bundle(tmp_path, **write_bundle(tmp_path, source, mapping))
    assert api.tree_fingerprint(updated.source) == before


@pytest.mark.parametrize(
    "filename", ["source-private.json", "mapping-private.json", "proposal-private.md"]
)
def test_modified_json_or_markdown_hash_is_rejected(tmp_path: Path, filename: str) -> None:
    api = operator()
    hashes = write_bundle(tmp_path, *cases())
    (tmp_path / filename).write_bytes(b"tampered")
    with pytest.raises(api.CategoryTreeError) as exc:
        api.load_bundle(tmp_path, **hashes)
    assert str(exc.value) == "bundle_integrity"


def test_bundle_does_not_execute_private_python_or_follow_symlink(tmp_path: Path) -> None:
    api = operator()
    hashes = write_bundle(tmp_path, *cases())
    assert len(api.compile_tree(api.load_bundle(tmp_path, **hashes)).creates) == 14
    path = tmp_path / "source-private.json"
    outside = tmp_path.parent / "outside-source.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(api.CategoryTreeError):
        api.load_bundle(tmp_path, **hashes)


def test_manifest_cannot_redirect_a_read_outside_bundle(tmp_path: Path) -> None:
    api = operator()
    hashes = write_bundle(tmp_path, *cases())
    manifest = json.loads((tmp_path / "manifest-private.json").read_text())
    manifest["files"]["../outside"] = "0" * 64
    (tmp_path / "manifest-private.json").write_text(json.dumps(manifest))
    with pytest.raises(api.CategoryTreeError):
        api.load_bundle(tmp_path, **hashes)
