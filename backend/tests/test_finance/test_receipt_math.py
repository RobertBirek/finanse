"""Receipt amounts are deterministic evidence, never estimates or floating-point math."""

import uuid

import pytest
from pydantic import ValidationError

A, B = uuid.UUID(int=1), uuid.UUID(int=2)
FOOD, HOME = uuid.UUID(int=3), uuid.UUID(int=4)


def body(*, amounts=(8000, 2000), shares=(800, 200), discount=1000, categories=(FOOD, HOME)):
    from app.finance.receipt_schemas import ReceiptBody

    return ReceiptBody(
        store_id=None,
        store_version=None,
        lines=[
            {
                "line_key": A,
                "name": "Żywność",
                "amount_minor": amounts[0],
                "category_id": categories[0],
            },
            {
                "line_key": B,
                "name": "Chemia",
                "amount_minor": amounts[1],
                "category_id": categories[1],
            },
        ],
        discounts=[
            {
                "discount_key": uuid.UUID(int=5),
                "name": "Kupon",
                "amount_minor": discount,
                "shares": [
                    {"line_key": A, "amount_minor": shares[0]},
                    {"line_key": B, "amount_minor": shares[1]},
                ],
            }
        ],
    )


def test_exact_8000_2000_discount_1000_explicit_800_200():
    from app.finance.receipt_math import calculate_receipt

    draft = body()
    before = draft.model_dump()
    result = calculate_receipt(draft, expected_total_minor=9000)
    assert result.net_total_minor == 9000 and result.difference_minor == 0
    assert [(p.category_id, p.amount_minor) for p in result.parts] == [(FOOD, 7200), (HOME, 1800)]
    assert [(r.line_key, r.net_minor) for r in result.line_nets] == [(A, 7200), (B, 1800)]
    assert result.problems == [] and draft.model_dump() == before


def test_missing_amount_is_not_zero():
    from app.finance.receipt_math import calculate_receipt

    result = calculate_receipt(body(amounts=(None, 2000)), expected_total_minor=9000)
    assert result.net_total_minor is None and result.difference_minor is None
    assert any(p.code == "missing_amount" and p.line_key == A for p in result.problems)


def test_discount_already_in_price_mismatch_is_blocked():
    from app.finance.receipt_math import calculate_receipt

    result = calculate_receipt(body(amounts=(7000, 2000)), expected_total_minor=9000)
    assert result.net_total_minor == 8000 and result.difference_minor == -1000
    assert any(p.code == "total_mismatch" for p in result.problems)


def test_multiple_discounts_no_negative_net():
    from app.finance.receipt_math import calculate_receipt

    draft = body()
    draft.discounts.append(draft.discounts[0].model_copy(update={"discount_key": uuid.UUID(int=6)}))
    result = calculate_receipt(draft, expected_total_minor=8000)
    assert result.net_total_minor == 8000 and not result.problems
    result = calculate_receipt(body(amounts=(500, 2000)), expected_total_minor=1500)
    assert any(p.code == "negative_net" and p.line_key == A for p in result.problems)
    assert result.parts == []


def test_zero_line_needs_no_category():
    from app.finance.receipt_math import calculate_receipt
    from app.finance.receipt_schemas import ReceiptBody

    draft = ReceiptBody(
        lines=[
            {"line_key": A, "name": "Gratis", "amount_minor": 0, "category_id": None},
            {"line_key": B, "name": "Produkt", "amount_minor": 100, "category_id": FOOD},
        ]
    )
    result = calculate_receipt(draft, expected_total_minor=100)
    assert not result.problems and len(result.parts) == 1 and result.parts[0].amount_minor == 100


@pytest.mark.parametrize("expected,difference", [(8999, 1), (9001, -1)])
def test_difference_one_grosz_blocks_approval(expected, difference):
    from app.finance.receipt_math import calculate_receipt

    result = calculate_receipt(body(), expected_total_minor=expected)
    assert result.difference_minor == difference
    assert any(p.code == "total_mismatch" for p in result.problems)


@pytest.mark.parametrize("value", [True, "100", -1, 9007199254740992, 1.2])
def test_strict_amounts_reject_invalid_numeric_inputs(value):
    with pytest.raises(ValidationError):
        body(amounts=(value, 2000))


@pytest.mark.parametrize(
    "kind", ["line", "discount", "share", "dangling", "normalized_name", "max_lines", "max_parts"]
)
def test_structural_and_configured_limits_are_enforced(kind, monkeypatch):
    from app.config import settings
    from app.finance.receipt_math import calculate_receipt
    from app.finance.receipt_schemas import ReceiptBody

    data = body().model_dump()
    if kind == "line":
        data["lines"].append(data["lines"][0])
    if kind == "discount":
        data["discounts"].append(data["discounts"][0])
    if kind == "share":
        data["discounts"][0]["shares"].append(data["discounts"][0]["shares"][0])
    if kind == "dangling":
        data["discounts"][0]["shares"][0]["line_key"] = uuid.UUID(int=999)
    if kind == "normalized_name":
        data["lines"][0]["name"] = "ﬃ" * 150
    if kind == "max_lines":
        monkeypatch.setattr(settings, "FINANCE_RECEIPT_MAX_LINES", 1)
    if kind == "max_parts":
        monkeypatch.setattr(settings, "FINANCE_CATEGORY_SPLIT_MAX_PARTS", 1)
        result = calculate_receipt(ReceiptBody.model_validate(data), expected_total_minor=9000)
        assert any(p.code == "too_many_parts" for p in result.problems)
    else:
        from app.finance.receipt_schemas import validate_receipt_input_limits

        with pytest.raises((ValidationError, ValueError)):
            validate_receipt_input_limits(ReceiptBody.model_validate(data))


@pytest.mark.parametrize(
    "kind", ["missing_share", "wrong_share_sum", "category", "blank", "discount_name"]
)
def test_incomplete_draft_reports_problems_without_inventing_data(kind):
    from app.finance.receipt_math import calculate_receipt

    draft = body()
    if kind == "missing_share":
        draft.discounts[0].shares[0].amount_minor = None
    if kind == "wrong_share_sum":
        draft.discounts[0].shares[0].amount_minor = 700
    if kind == "category":
        draft.lines[0].category_id = None
    if kind == "blank":
        draft.lines[0].name = " "
    if kind == "discount_name":
        draft.discounts[0].name = " "
    result = calculate_receipt(draft, expected_total_minor=9000)
    assert result.problems
    if kind in {"missing_share", "wrong_share_sum"}:
        assert result.net_total_minor is None


def test_overflow_total_is_not_exposed_as_a_safe_browser_amount():
    from app.finance.receipt_math import calculate_receipt
    from app.finance.receipt_schemas import ReceiptBody

    draft = ReceiptBody(
        lines=[
            {"line_key": A, "name": "A", "amount_minor": 9007199254740991, "category_id": FOOD},
            {"line_key": B, "name": "B", "amount_minor": 1, "category_id": HOME},
        ]
    )
    result = calculate_receipt(draft, expected_total_minor=100)
    assert result.net_total_minor is None and result.difference_minor is None and result.parts == []
    assert any(p.code == "amount_out_of_range" for p in result.problems)
