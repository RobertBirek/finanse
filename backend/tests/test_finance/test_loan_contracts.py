"""Strict API inputs cannot silently round or coerce planned money."""

import pytest
from pydantic import ValidationError

from app.finance.loan_schemas import LoanCreate, LoanInstallmentCreate, LoanInstallmentUpdate


@pytest.mark.parametrize("value", [True, 1.0, "100", -1, 9_007_199_254_740_992])
def test_components_are_strict_safe_integers(value: object) -> None:
    with pytest.raises(ValidationError):
        LoanInstallmentCreate.model_validate(
            {
                "number": 1,
                "due_date": "2026-01-01",
                "principal_pln": value,
                "interest_pln": 1,
                "fees_pln": 0,
            }
        )
    with pytest.raises(ValidationError):
        LoanInstallmentUpdate.model_validate({"principal_pln": value})


def test_installment_total_is_positive_and_safe() -> None:
    for principal, interest in [(0, 0), (9_007_199_254_740_991, 1)]:
        with pytest.raises(ValidationError):
            LoanInstallmentCreate(
                number=1,
                due_date="2026-01-01",
                principal_pln=principal,
                interest_pln=interest,
                fees_pln=0,
            )


def test_loan_name_cannot_be_whitespace() -> None:
    with pytest.raises(ValidationError):
        LoanCreate.model_validate(
            {
                "name": "   ",
                "account_id": "10000000-0000-0000-0000-000000000001",
                "payment_account_id": "10000000-0000-0000-0000-000000000002",
            }
        )
