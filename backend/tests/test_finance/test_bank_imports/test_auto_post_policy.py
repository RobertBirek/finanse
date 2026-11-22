from datetime import date

import pytest

from app.finance.imports.contracts import SourcePosition, StatementRow


def bank_row(*, amount: int = -700, fee: int = 0, **raw: str) -> StatementRow:
    return StatementRow(
        key="row",
        position=SourcePosition(line=1),
        booking_date=date(2026, 11, 2),
        description="Sklep testowy",
        amount=amount,
        fee=fee,
        currency="PLN",
        state="posted",
        raw=raw,
    )


@pytest.mark.parametrize("label", ["Płatność kartą", "CARD_PAYMENT", "Card Payment"])
def test_bank_card_purchase_can_be_an_expense(label: str) -> None:
    from app.finance.imports.auto_policy import classify

    assert classify("revolut", bank_row(Rodzaj=label)) == ("expense", None)


@pytest.mark.parametrize("label", ["Transfer", "Topup", "Refund", "Wymiana", "Wypłata gotówki"])
def test_a_sign_does_not_make_a_transfer_or_refund_an_external_payment(label: str) -> None:
    from app.finance.imports.auto_policy import classify

    for amount in [-700, 700]:
        assert classify("revolut", bank_row(amount=amount, Rodzaj=label)) == (
            None,
            "movement_unclear",
        )


def test_pdf_requires_an_explicit_label_not_a_substring_in_free_text() -> None:
    from app.finance.imports.auto_policy import classify

    row = bank_row().model_copy(
        update={"raw": {"description_lines": ["PŁATNOŚĆ KARTĄ", "Sklep testowy"]}}
    )
    assert classify("velo", row) == ("expense", None)
    row = row.model_copy(
        update={"raw": {"description_lines": ["Przelew własny", "Płatność kartą"]}}
    )
    assert classify("velo", row) == (None, "movement_unclear")


def test_credit_of_bank_interest_is_income_but_positive_card_payment_is_not() -> None:
    from app.finance.imports.auto_policy import classify

    assert classify("revolut", bank_row(amount=30, Rodzaj="Interest")) == ("income", None)
    assert classify("revolut", bank_row(amount=30, Rodzaj="Card Payment")) == (
        None,
        "movement_unclear",
    )


def test_nonposted_and_fees_are_not_auto_posted() -> None:
    from app.finance.imports.auto_policy import classify

    pending = bank_row(Rodzaj="CARD_PAYMENT").model_copy(update={"state": "pending"})
    assert classify("revolut", pending) == (None, "not_postable")
    assert classify("revolut", bank_row(fee=30, Rodzaj="CARD_PAYMENT")) == (
        None,
        "fee_review",
    )


def test_automatic_posting_has_separate_settings_and_source_command() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    settings = paths["/api/finance/imports/auto-post-settings"]
    assert {"get", "put"} <= settings.keys()
    path = "/api/finance/imports/{batch_id}/sources/{source_id}/auto-post"
    assert "post" in paths[path]
    assert "get" not in paths[path]
