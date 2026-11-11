"""Pure, fail-closed release checks. They do not execute or authorize deployment."""

import json
import re
from typing import Any, Literal

FREEZE_KEYS = {
    "runtime_sha",
    "git_tip",
    "schema_from",
    "schema_to",
    "source_hashes",
    "dist_hashes",
    "image_ids",
    "compose_hashes",
    "data_container_ids",
}
SERVICES = {"backend", "worker", "frontend"}
TABLES = {
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
}
ZERO_FIELDS = {
    "bank_import_documents",
    "import_command_receipts",
    "active_schedule_pointers",
    "superseded_pointers",
}
TRUE_FIELDS = {"fenced", "writers_stopped", "old_runtime_on_current_schema_passed"}
EVIDENCE_KEYS = (
    ZERO_FIELDS | TRUE_FIELDS | {"schema_head", "old_image_ids", "import_table_counts"}
)


def valid_ids(value: Any) -> bool:
    return (
        type(value) is dict
        and set(value) == SERVICES
        and all(
            type(v) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", v)
            for v in value.values()
        )
    )


def check_freeze(expected: Any, observed: Any) -> None:
    for item in (expected, observed):
        if type(item) is not dict or set(item) != FREEZE_KEYS:
            raise RuntimeError("Incomplete freeze")
        for key in ["runtime_sha", "git_tip"]:
            if type(item[key]) is not str or not re.fullmatch(
                r"[0-9a-f]{40}", item[key]
            ):
                raise RuntimeError("Invalid revision")
        if item["schema_from"] != "739144d5eaef" or item["schema_to"] != "84fdbd10aa18":
            raise RuntimeError("Unexpected schema contract")
        if not valid_ids(item["image_ids"]):
            raise RuntimeError("Invalid original image IDs")
        for key in [
            "source_hashes",
            "dist_hashes",
            "compose_hashes",
            "data_container_ids",
        ]:
            values = item[key]
            if (
                type(values) is not dict
                or not values
                or not all(
                    type(k) is str
                    and k
                    and type(v) is str
                    and re.fullmatch(r"[0-9a-f]{64}", v)
                    for k, v in values.items()
                )
            ):
                raise RuntimeError("Invalid fingerprint set")
    if json.dumps(expected, sort_keys=True, allow_nan=False) != json.dumps(
        observed, sort_keys=True, allow_nan=False
    ):
        raise RuntimeError("Freeze drift; stop")


def select_rollback(
    evidence: Any, *, expected_freeze: Any = None, observed_freeze: Any = None
) -> Literal["app_only", "stop"]:
    # expected_freeze must come from the separately trusted frozen inventory,
    # never from the caller's current evidence. No SQL or side effects here.
    try:
        check_freeze(expected_freeze, observed_freeze)
    except RuntimeError:
        return "stop"
    if type(evidence) is not dict or set(evidence) != EVIDENCE_KEYS:
        return "stop"
    if evidence["schema_head"] != "84fdbd10aa18" or not valid_ids(
        evidence["old_image_ids"]
    ):
        return "stop"
    if evidence["old_image_ids"] != expected_freeze["image_ids"]:
        return "stop"
    if any(evidence[key] is not True for key in TRUE_FIELDS):
        return "stop"
    if any(type(evidence[key]) is not int or evidence[key] != 0 for key in ZERO_FIELDS):
        return "stop"
    counts = evidence["import_table_counts"]
    if type(counts) is not dict or set(counts) != TABLES:
        return "stop"
    if any(type(count) is not int or count != 0 for count in counts.values()):
        return "stop"
    return "app_only"
