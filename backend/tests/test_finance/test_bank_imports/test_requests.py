import uuid

import pytest
from pydantic import ValidationError

from app.finance.imports.schemas import CommitRequest, DecisionUpdate, PreviewRequest


def expense_decision() -> dict[str, object]:
    return {
        "group_id": str(uuid.uuid4()),
        "row_ids": [str(uuid.uuid4())],
        "action": "create",
        "kind": "expense",
        "account_id": str(uuid.uuid4()),
        "category_id": str(uuid.uuid4()),
    }


@pytest.mark.parametrize("version", [0, -1, True, "1", 1.0])
def test_decision_version_cannot_bypass_optimistic_locking(version: object) -> None:
    with pytest.raises(ValidationError):
        DecisionUpdate.model_validate(
            {"expected_version": version, "decisions": [expense_decision()]}
        )


def test_client_cannot_supply_ledger_postings_as_import_decisions() -> None:
    decision = expense_decision() | {"postings": [{"base_amount_pln": 999}]}
    with pytest.raises(ValidationError):
        DecisionUpdate.model_validate({"expected_version": 1, "decisions": [decision]})


def test_same_row_cannot_be_selected_in_two_create_groups() -> None:
    first, second = expense_decision(), expense_decision()
    second["row_ids"] = first["row_ids"]
    with pytest.raises(ValidationError):
        DecisionUpdate.model_validate({"expected_version": 1, "decisions": [first, second]})


def test_deferred_unclassified_row_does_not_require_a_fabricated_account() -> None:
    group_id, row_id = uuid.uuid4(), uuid.uuid4()
    request = DecisionUpdate.model_validate(
        {
            "expected_version": 1,
            "decisions": [
                {"group_id": str(group_id), "row_ids": [str(row_id)], "action": "defer"},
            ],
        }
    )
    assert request.decisions[0].account_id is None
    assert request.decisions[0].kind is None


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "transfer"},
        {"kind": "exchange"},
        {"action": "link"},
        {"category_id": None},
        {"existing_transaction_id": str(uuid.uuid4())},
    ],
)
def test_incomplete_or_conflicting_financial_decision_is_rejected(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DecisionUpdate.model_validate(
            {"expected_version": 1, "decisions": [expense_decision() | changes]}
        )


def test_transfer_requires_distinct_existing_account_targets() -> None:
    account = str(uuid.uuid4())
    with pytest.raises(ValidationError):
        DecisionUpdate.model_validate(
            {
                "expected_version": 1,
                "decisions": [
                    expense_decision()
                    | {
                        "kind": "transfer",
                        "account_id": account,
                        "other_account_id": account,
                    }
                ],
            }
        )


def test_zero_or_duplicate_preview_groups_are_not_a_valid_confirmation() -> None:
    group = uuid.uuid4()
    for ids in [[], [str(group), str(group)]]:
        with pytest.raises(ValidationError):
            PreviewRequest.model_validate({"expected_version": 1, "group_ids": ids})


def test_commit_refers_to_server_preview_not_freeform_financial_payload() -> None:
    valid = {"preview_id": str(uuid.uuid4()), "request_hash": "a" * 64}
    request = CommitRequest.model_validate(valid)
    assert request.request_hash == "a" * 64
    for changes in [{"postings": []}, {"request_hash": "fake"}, {"request_hash": "G" * 64}]:
        with pytest.raises(ValidationError):
            CommitRequest.model_validate(valid | changes)
