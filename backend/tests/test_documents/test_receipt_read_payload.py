import uuid

import pytest
from pydantic import ValidationError


def payload_data():
    return {
        "document_type": "receipt",
        "currency": "PLN",
        "printed_total": "90.00",
        "lines": [
            {
                "index": 0,
                "name": "Mleko",
                "amount": "80.00",
                "basis": "before_separate_discount",
                "source_text": "MLEKO 80,00",
                "unreadable": False,
            },
            {
                "index": 1,
                "name": "Płyn",
                "amount": "20.00",
                "basis": "before_separate_discount",
                "source_text": "PLYN 20,00",
                "unreadable": False,
            },
        ],
        "discounts": [
            {
                "index": 0,
                "name": "Kupon",
                "amount": "10.00",
                "kind": "separate",
                "shares": [
                    {"line_index": 0, "amount": "8.00"},
                    {"line_index": 1, "amount": "2.00"},
                ],
                "source_text": "Kupon -10,00",
            }
        ],
        "warnings": [],
    }


def calculate(proposal, total=9000):
    from app.finance.receipt_math import calculate_receipt

    body = proposal.body.model_copy(deep=True)
    for n, line in enumerate(body.lines):
        line.category_id = uuid.UUID(int=n + 10)
    return calculate_receipt(body, expected_total_minor=total)


def test_transcribed_8000_2000_discount_800_200_is_7200_1800():
    from app.documents.receipt_read_payload import ReceiptReadPayload, build_receipt_read_proposal

    data = ReceiptReadPayload.model_validate(payload_data())
    before = data.model_dump()
    proposal = build_receipt_read_proposal(data)
    result = calculate(proposal)
    assert proposal.importable and all(l.category_id is None for l in proposal.body.lines)
    assert [r.amount_minor for r in result.parts] == [7200, 1800]
    assert result.net_total_minor == 9000 and result.difference_minor == 0 and not result.problems
    assert data.model_dump() == before


def test_already_included_discount_is_not_subtracted_again():
    from app.documents.receipt_read_payload import ReceiptReadPayload, build_receipt_read_proposal

    data = payload_data()
    data["lines"][0]["amount"] = "72.00"
    data["lines"][1]["amount"] = "18.00"
    for l in data["lines"]:
        l["basis"] = "after_included_discount"
    data["discounts"][0]["kind"] = "included"
    proposal = build_receipt_read_proposal(ReceiptReadPayload.model_validate(data))
    assert proposal.body.discounts == [] and calculate(proposal).net_total_minor == 9000
    assert any(p.requires_ack and p.code == "included_discount" for p in proposal.problems)


def test_global_coupon_has_no_invented_proportions():
    from app.documents.receipt_read_payload import ReceiptReadPayload, build_receipt_read_proposal

    data = payload_data()
    data["discounts"][0]["shares"] = []
    proposal = build_receipt_read_proposal(ReceiptReadPayload.model_validate(data))
    assert proposal.body.discounts[0].shares == [] and calculate(proposal).net_total_minor is None


def test_missing_rows_matching_total_still_requires_review():
    from app.documents.receipt_read_payload import ReceiptReadPayload, build_receipt_read_proposal

    data = payload_data()
    data["warnings"] = ["missing_rows"]
    proposal = build_receipt_read_proposal(ReceiptReadPayload.model_validate(data))
    assert calculate(proposal).net_total_minor == 9000
    assert any(p.code == "missing_rows" and p.requires_ack for p in proposal.problems)


@pytest.mark.parametrize(
    "kind", ["unknown_basis", "unreadable", "missing_amount", "missing_name", "unknown_discount"]
)
def test_ambiguous_values_remain_missing_for_manual_review(kind):
    from app.documents.receipt_read_payload import ReceiptReadPayload, build_receipt_read_proposal

    data = payload_data()
    if kind == "unknown_basis":
        data["lines"][0]["basis"] = "unknown"
    if kind == "unreadable":
        data["lines"][0]["unreadable"] = True
    if kind == "missing_amount":
        data["lines"][0]["amount"] = None
    if kind == "missing_name":
        data["lines"][0]["name"] = None
    if kind == "unknown_discount":
        data["discounts"][0]["kind"] = "unknown"
    proposal = build_receipt_read_proposal(ReceiptReadPayload.model_validate(data))
    assert proposal.problems
    if kind == "missing_name":
        assert proposal.body.lines[0].name == ""
    elif kind == "unknown_discount":
        assert proposal.body.discounts[0].amount_minor is None
    else:
        assert proposal.body.lines[0].amount_minor is None
    assert calculate(proposal).problems


@pytest.mark.parametrize(
    "raw,want",
    [
        (None, None),
        ("0", 0),
        ("0.00", 0),
        ("1", 100),
        ("0.01", 1),
        ("12.3", 1230),
        ("90071992547409.91", 9007199254740991),
    ],
)
def test_canonical_decimal_conversion_is_exact(raw, want):
    from app.documents.receipt_read_payload import parse_receipt_read_amount

    assert parse_receipt_read_amount(raw, allow_zero=True) == want


@pytest.mark.parametrize(
    "raw", [True, 1, 1.2, "", " 1", "01", "1,00", "1e2", "-1", "1.001", "NaN", "90071992547409.92"]
)
def test_invalid_nonblank_amount_is_not_coerced_or_rounded(raw):
    from app.documents.receipt_read_payload import parse_receipt_read_amount

    with pytest.raises(ValueError):
        parse_receipt_read_amount(raw, allow_zero=True)


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "dangling",
        "share_duplicate",
        "category",
        "bool_index",
        "overflow",
        "normalized_name",
    ],
)
def test_provider_payload_cannot_smuggle_authority_or_bad_structure(kind):
    from app.documents.receipt_read_config import get_receipt_read_config
    from app.documents.receipt_read_payload import ReceiptReadPayload, validate_receipt_read_intake
    from tests.test_documents.test_receipt_read_policy import config_settings

    data = payload_data()
    if kind == "duplicate":
        data["lines"][1]["index"] = 0
    if kind == "dangling":
        data["discounts"][0]["shares"][0]["line_index"] = 999
    if kind == "share_duplicate":
        data["discounts"][0]["shares"].append(data["discounts"][0]["shares"][0])
    if kind == "category":
        data["lines"][0]["category_id"] = str(uuid.uuid4())
    if kind == "bool_index":
        data["lines"][0]["index"] = True
    if kind == "overflow":
        data["lines"][0]["amount"] = "90071992547409.92"
    if kind == "normalized_name":
        data["lines"][0]["name"] = "ﬃ" * 150
    with pytest.raises((ValidationError, ValueError)):
        validate_receipt_read_intake(
            ReceiptReadPayload.model_validate(data), get_receipt_read_config(config_settings())
        )


def test_historical_payload_keeps_readable_after_intake_limits_change():
    from app.documents.receipt_read_config import get_receipt_read_config
    from app.documents.receipt_read_payload import ReceiptReadPayload, validate_receipt_read_intake
    from tests.test_documents.test_receipt_read_policy import config_settings

    value = ReceiptReadPayload.model_validate(payload_data())
    tight = get_receipt_read_config(config_settings(FINANCE_RECEIPT_MAX_LINES=1))
    with pytest.raises(ValueError):
        validate_receipt_read_intake(value, tight)
    assert ReceiptReadPayload.model_validate(value.model_dump()) == value
