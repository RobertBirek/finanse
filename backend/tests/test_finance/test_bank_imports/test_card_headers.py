import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.finance.credit_card_schemas import StatementCreate
from app.finance.imports.card_statements import CardHeaderDecision, validate_card_header
from app.finance.imports.errors import ImportError
from tests.test_finance.test_bank_imports.test_velo_card import card_statement


def confirmed(**changes):
    return CardHeaderDecision.model_validate(
        {
            "account_id": str(uuid.uuid4()),
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "due_date": "2026-02-15",
            "debt_pln": 92000,
            "minimum_pln": 5000,
            "debt_definition_confirmed": True,
            **changes,
        }
    )


def test_confirmed_header_projects_existing_statement_contract_without_postings() -> None:
    decision = confirmed()
    parsed = card_statement()
    first = validate_card_header(parsed, decision)
    assert isinstance(first, StatementCreate)
    assert (
        first.debt_pln == 92000
        and first.minimum_pln == 5000
        and first.due_date == date(2026, 2, 15)
    )
    assert first.request_id == validate_card_header(parsed, decision).request_id
    assert first.source_reference.startswith("bank-import:")


@pytest.mark.parametrize(
    "changes",
    [
        {"debt_definition_confirmed": False},
        {"debt_pln": 1000000},
        {"minimum_pln": 0},
        {"due_date": "2026-02-16"},
        {"period_start": "2025-12-31"},
    ],
)
def test_user_must_confirm_actual_source_values_not_replace_them_with_total_limit_or_guess(
    changes,
) -> None:
    with pytest.raises(ImportError):
        validate_card_header(card_statement(), confirmed(**changes))


def test_ambiguous_or_missing_header_cannot_create_a_statement_record() -> None:
    parsed = card_statement()
    assert parsed.card_header is not None
    for header in [
        None,
        parsed.card_header | {"minimum_pln": None},
        parsed.card_header | {"debt_definition": "unknown"},
    ]:
        with pytest.raises(ImportError):
            validate_card_header(parsed.model_copy(update={"card_header": header}), confirmed())


@pytest.mark.parametrize(
    "changes",
    [
        {"postings": []},
        {"debt_pln": -1},
        {"minimum_pln": True},
        {"debt_definition_confirmed": "true"},
    ],
)
def test_header_decision_never_accepts_postings_or_coerced_financial_values(changes) -> None:
    with pytest.raises(ValidationError):
        confirmed(**changes)
