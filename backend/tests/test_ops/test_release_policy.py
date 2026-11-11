"""Rollback requires an empty schema AND trusted, drift-free original identities."""

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "ops/release_policy.py"
TABLES = [
    "bank_import_batches",
    "bank_import_decisions",
    "bank_import_evidence",
    "bank_import_group_rows",
    "bank_import_groups",
    "bank_import_identities",
    "bank_import_jobs",
    "bank_import_previews",
    "bank_import_revisions",
    "bank_import_rows",
    "bank_import_sources",
    "loan_schedule_memberships",
    "loan_schedule_revisions",
]


def load_policy() -> Any:
    spec = importlib.util.spec_from_file_location("release_policy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evidence() -> dict[str, Any]:
    return {
        "schema_head": "84fdbd10aa18",
        "fenced": True,
        "writers_stopped": True,
        "old_runtime_on_current_schema_passed": True,
        "old_image_ids": {
            s: "sha256:" + h * 64 for s, h in [("backend", "a"), ("worker", "b"), ("frontend", "c")]
        },
        "import_table_counts": dict.fromkeys(TABLES, 0),
        "bank_import_documents": 0,
        "import_command_receipts": 0,
        "active_schedule_pointers": 0,
        "superseded_pointers": 0,
    }


@pytest.fixture
def freeze(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_sha": "a" * 40,
        "git_tip": "b" * 40,
        "schema_from": "739144d5eaef",
        "schema_to": "84fdbd10aa18",
        "source_hashes": {"main.py": "c" * 64},
        "dist_hashes": {"index.html": "d" * 64},
        "image_ids": copy.deepcopy(evidence["old_image_ids"]),
        "compose_hashes": {"synthetic.yaml": "e" * 64},
        "data_container_ids": {"synthetic-pg": "f" * 64},
    }


def test_unbound_rollback_evidence_is_refused(evidence: dict[str, Any]) -> None:
    assert load_policy().select_rollback(evidence) == "stop"


def test_exact_trusted_and_observed_freeze_allows_only_empty_schema84(
    evidence: dict[str, Any], freeze: dict[str, Any]
) -> None:
    assert (
        load_policy().select_rollback(
            evidence, expected_freeze=freeze, observed_freeze=copy.deepcopy(freeze)
        )
        == "app_only"
    )


@pytest.mark.parametrize("service", ["backend", "worker", "frontend"])
def test_well_formed_but_untrusted_old_image_id_is_refused(
    evidence: dict[str, Any], freeze: dict[str, Any], service: str
) -> None:
    evidence["old_image_ids"][service] = "sha256:" + "0" * 64
    assert (
        load_policy().select_rollback(evidence, expected_freeze=freeze, observed_freeze=freeze)
        == "stop"
    )


@pytest.mark.parametrize(
    "field",
    [
        "runtime_sha",
        "git_tip",
        "schema_from",
        "schema_to",
        "source_hashes",
        "dist_hashes",
        "image_ids",
        "compose_hashes",
        "data_container_ids",
    ],
)
def test_every_freeze_drift_is_refused(
    evidence: dict[str, Any], freeze: dict[str, Any], field: str
) -> None:
    observed = copy.deepcopy(freeze)
    observed[field] = None
    policy = load_policy()
    with pytest.raises(RuntimeError):
        policy.check_freeze(freeze, observed)
    assert (
        policy.select_rollback(evidence, expected_freeze=freeze, observed_freeze=observed) == "stop"
    )


@pytest.mark.parametrize("bad", [None, False, True, "0", 0.0, -1, 1])
def test_every_import_table_requires_an_actual_integer_zero(
    evidence: dict[str, Any], freeze: dict[str, Any], bad: Any
) -> None:
    for table in TABLES:
        modified = copy.deepcopy(evidence)
        modified["import_table_counts"][table] = bad
        assert (
            load_policy().select_rollback(modified, expected_freeze=freeze, observed_freeze=freeze)
            == "stop"
        )


def test_incomplete_guards_schema_or_extra_policy_never_authorizes(
    evidence: dict[str, Any], freeze: dict[str, Any]
) -> None:
    policy = load_policy()
    modifications = [
        {"fenced": False},
        {"writers_stopped": False},
        {"old_runtime_on_current_schema_passed": False},
        {"bank_import_documents": 1},
        {"import_command_receipts": 1},
        {"active_schedule_pointers": 1},
        {"superseded_pointers": 1},
        {"schema_head": "739144d5eaef"},
        {"schema_head": "6bd8758ebc7d"},
        {"import_table_counts": {}},
        {"extra": True},
    ]
    for modified in [evidence | change for change in modifications]:
        assert (
            policy.select_rollback(modified, expected_freeze=freeze, observed_freeze=freeze)
            == "stop"
        )
    for key in evidence:
        missing = {k: v for k, v in evidence.items() if k != key}
        assert (
            policy.select_rollback(missing, expected_freeze=freeze, observed_freeze=freeze)
            == "stop"
        )
