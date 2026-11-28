"""Public recurrence-proposal responses remain explicitly advisory."""

from datetime import date
from types import SimpleNamespace

from app.finance.imports.recurring_detection import (
    NewScheduleProposal,
    RecurrenceAnalysis,
    RecurrenceEvidence,
)
from app.finance.imports.recurring_proposals import (
    _historical_reference_matches_identity,
    _source_binds_account,
    proposal_response,
)
from tests.test_finance.test_bank_imports.test_contracts import statement_row


def test_endpoint_response_keeps_observed_dates_separate_from_formal_deadline() -> None:
    """Fails if the adapter turns an observed statement date into a due date."""
    response = proposal_response(
        RecurrenceAnalysis(
            status="proposed",
            proposal=NewScheduleProposal(
                merchant="netflix.com",
                frequency="monthly",
                amount_kind="stable",
                amount_minor=-4900,
                currency="PLN",
            ),
            evidence=(
                RecurrenceEvidence(
                    strong_identity="velo:ref-1",
                    economic_identity="velo:ref-1",
                    source="bank_import",
                    occurred_on=date(2026, 1, 3),
                    amount_minor=-4900,
                    currency="PLN",
                ),
            ),
        )
    )

    assert response.status == "proposed"
    assert response.proposal is not None
    assert response.proposal.formal_deadline is None
    assert response.evidence[0].occurred_on == date(2026, 1, 3)


def test_recurring_source_requires_matching_account_reference_and_bank_provenance() -> None:
    """Fails if a selected owned account can stand in for an unbound statement source."""
    source = SimpleNamespace(bank="velo", account_reference="PL12 3456")
    account = SimpleNamespace(bank_name="Velo Bank", iban="123456")

    assert _source_binds_account(source, None, account) is True
    assert (
        _source_binds_account(
            SimpleNamespace(bank="velo", account_reference=None),
            {"account_reference": "PL12 3456"},
            account,
        )
        is True
    )
    assert (
        _source_binds_account(
            SimpleNamespace(bank="velo", account_reference="PL99 9999"), None, account
        )
        is False
    )
    assert (
        _source_binds_account(
            SimpleNamespace(bank="ing", account_reference="PL12 3456"), None, account
        )
        is False
    )
    assert (
        _source_binds_account(SimpleNamespace(bank="velo", account_reference=None), None, account)
        is False
    )
    assert (
        _source_binds_account(source, None, SimpleNamespace(bank_name=None, iban="123456")) is False
    )
    assert (
        _source_binds_account(source, None, SimpleNamespace(bank_name="Velo Bank", iban=None))
        is False
    )


def test_historical_row_requires_its_exact_canonical_bank_reference() -> None:
    """Fails if a group/account identity can canonicalize a different statement row."""
    row = statement_row(bank_reference="statement-reference")

    assert _historical_reference_matches_identity(row, "statement-reference") is True
    assert _historical_reference_matches_identity(row, "other-group-reference") is False
    assert (
        _historical_reference_matches_identity(
            statement_row(bank_reference=None), "statement-reference"
        )
        is False
    )
