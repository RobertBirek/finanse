"""Selector regressions: missing/duplicate IDs and file splitting must fail closed."""

import copy

import pytest


def rows():
    values = [
        {
            "nodeid": f"tests/test_synthetic_{i}.py::test_ok",
            "integration": bool(i % 2),
            "migration": False,
            "proxy": False,
        }
        for i in range(12)
    ]
    values += [
        {
            "nodeid": "tests/test_migrate.py::test_migrate",
            "integration": False,
            "migration": True,
            "proxy": False,
        },
        {
            "nodeid": "tests/test_migrate.py::test_lineage",
            "integration": False,
            "migration": False,
            "proxy": False,
        },
        {
            "nodeid": "tests/test_documents/test_proxy_upload.py::test_proxy",
            "integration": False,
            "migration": False,
            "proxy": True,
        },
        {
            "nodeid": "tests/test_optional.py::test_image",
            "integration": False,
            "migration": False,
            "proxy": True,
        },
    ]
    return values


def test_exact_target_and_unique_union():
    from ci_tools.partition import build_manifest
    from ci_tools.results import validate_manifest

    m = build_manifest(rows(), "a" * 40)
    validate_manifest(m)
    assert set(m["groups"]) == {"legacy", "proxy", *(f"ordinary-{i}" for i in range(1, 7))}
    selected = [node for values in m["groups"].values() for node in values]
    assert len(selected) == len(set(selected)) == 15
    assert "tests/test_optional.py::test_image" not in selected


def test_file_grouping_and_migration_sibling():
    from ci_tools.partition import build_manifest

    m = build_manifest(rows(), "a" * 40)
    assert m["groups"]["legacy"] == [
        "tests/test_migrate.py::test_migrate",
        "tests/test_migrate.py::test_lineage",
    ]


def test_stable_under_inventory_permutation():
    from ci_tools.partition import build_manifest

    first = build_manifest(rows(), "a" * 40)
    second = build_manifest(list(reversed(rows())), "a" * 40)
    assert {k: set(v) for k, v in first["groups"].items()} == {
        k: set(v) for k, v in second["groups"].items()
    }


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "foreign", "empty", "split", "bad_inventory"]
)
def test_rejects_duplicate_missing_foreign_and_empty_group(mutation):
    from ci_tools.partition import build_manifest, manifest_digest
    from ci_tools.results import validate_manifest

    m = copy.deepcopy(build_manifest(rows(), "a" * 40))
    group = m["groups"]["ordinary-1"]
    if mutation == "duplicate":
        group.append(group[0])
    elif mutation == "missing":
        group.pop()
    elif mutation == "foreign":
        group[0] = "tests/test_foreign.py::test_missing"
    elif mutation == "empty":
        m["groups"]["ordinary-1"] = []
    elif mutation == "split":
        m["groups"]["ordinary-1"].append(m["groups"]["legacy"].pop())
    else:
        m["inventory"].append(dict(m["inventory"][0]))
    m["digest"] = manifest_digest(m)
    with pytest.raises(ValueError):
        validate_manifest(m)
