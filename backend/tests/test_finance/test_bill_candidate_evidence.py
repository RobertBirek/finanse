"""Pins date/name evidence without DB, inferred dates or monetary writes."""

import uuid
from datetime import date, timedelta

import pytest

from app.finance.bills_schemas import BillCandidate, BillCandidatePage
from app.finance.models import (
    FinancialDocument,
    FinancialTransaction,
    Posting,
    TransactionDateMetadata,
)

TODAY = date(2026, 11, 7)
PURCHASE = date(2026, 10, 30)
BOOKING = date(2026, 11, 2)


def example(*, purchase=PURCHASE, booking=BOOKING, sale=PURCHASE, due=TODAY, issue=None):
    owner, transaction_id = uuid.uuid4(), uuid.uuid4()
    bill = FinancialDocument(
        user_id=owner,
        sale_date=sale,
        due_date=due,
        issue_date=issue,
        supplier_name="Supplier",
        total_minor=10000,
        payment_account_id=None,
    )
    transaction = FinancialTransaction(
        id=transaction_id,
        user_id=owner,
        date=BOOKING,
        description="Supplier payment",
    )
    transaction.date_metadata = TransactionDateMetadata(
        transaction_id=transaction_id,
        user_id=owner,
        purchase_date=purchase,
        purchase_date_source="manual" if purchase else None,
        booking_date=booking,
        booking_date_source="bank" if booking else None,
    )
    return bill, transaction, Posting(account_id=uuid.uuid4())


def evidence(parts, window=2):
    from app.finance.bill_candidate_evidence import build_candidate_evidence

    return build_candidate_evidence(*parts, today=TODAY, window_days=window)


def candidate(**changes):
    return BillCandidate.model_validate(
        {
            "transaction_id": uuid.UUID(int=1),
            "posting_id": uuid.UUID(int=2),
            "date": BOOKING,
            "account": "Karta",
            "amount_minor": 10000,
            "unallocated_minor": 6000,
            "reasons": [],
            "recurring_conflicts": [],
            **changes,
        }
    )


def test_legacy_candidate_schema_defaults():
    row = candidate()
    page = BillCandidatePage(items=[row], total=1, limit=20, offset=0)
    assert row.evidence is None
    assert page.unavailable_reason is None
    assert row.date == BOOKING
    assert (row.amount_minor, row.unallocated_minor) == (10000, 6000)


@pytest.mark.parametrize(
    "purchase,booking,sale,due,issue,txn_basis,doc_basis,expected",
    [
        (PURCHASE, BOOKING, PURCHASE, TODAY, TODAY, "purchase", "sale", 0),
        (PURCHASE, BOOKING, None, TODAY, PURCHASE, "booking", "due", -5),
        (PURCHASE, BOOKING, None, None, PURCHASE, "purchase", "issue", 0),
        (None, BOOKING, None, None, PURCHASE, "booking", "issue", 3),
        (None, None, PURCHASE, None, None, "legacy", "sale", 3),
        (None, BOOKING, None, None, None, "booking", "today", -5),
        (None, None, None, None, None, "legacy", "today", -5),
    ],
)
def test_date_pair_precedence(purchase, booking, sale, due, issue, txn_basis, doc_basis, expected):
    parts = example(purchase=purchase, booking=booking, sale=sale, due=due, issue=issue)
    before = (parts[1].date, parts[1].date_metadata.purchase_date)
    e = evidence(parts)
    assert (e.purchase_date, e.booking_date) == (purchase, booking)
    assert e.purchase_date_source == ("manual" if purchase else None)
    assert e.booking_date_source == ("bank" if booking else None)
    assert e.date_comparison.transaction_basis == txn_basis
    assert e.date_comparison.document_basis == doc_basis
    assert e.date_comparison.delta_days == expected
    assert e.date_comparison.within_window is (abs(expected) <= 2)
    assert before == (parts[1].date, parts[1].date_metadata.purchase_date)


@pytest.mark.parametrize("invalid", ["absent", "owner", "transaction"])
def test_unknown_and_foreign_metadata_are_not_evidence(invalid):
    bill, txn, posting = example()
    if invalid == "absent":
        txn.date_metadata = None
    elif invalid == "owner":
        txn.date_metadata.user_id = uuid.uuid4()
    else:
        txn.date_metadata.transaction_id = uuid.uuid4()
    e = evidence((bill, txn, posting))
    assert e.purchase_date is e.booking_date is None
    assert e.purchase_date_source is e.booking_date_source is None
    assert e.date_comparison.transaction_basis == "legacy"
    assert e.date_comparison.transaction_date == BOOKING


@pytest.mark.parametrize(
    "name,description,want",
    [
        ("ŻÓŁĆ, Sp. z o.o.", "zapłata żółć sp z o o terminal", True),
        ("é", "e\u0301", True),
        ("ＡＢＣ", "ABC", True),
        ("ABC", "XABCD", False),
        ("ABC", "[actual:ABC] unrelated", False),
        ("ABC", " [actual:ABC] [actual:other] prawdziwe ABC", True),
        (None, "payment", False),
        ("  ", "  ", False),
        ("--", "--", False),
        ("Żółć", "Zolc", False),
        ("One Two", "One unrelated Two", False),
    ],
)
def test_text_signal_is_whole_normalized_phrase(name, description, want):
    from app.finance.bill_candidate_evidence import supplier_name_in_description

    assert supplier_name_in_description(name, description) is want


@pytest.mark.parametrize("days,want", [(-3, False), (-2, True), (2, True), (3, False)])
def test_evidence_window_edges(days, want):
    parts = example(sale=PURCHASE + timedelta(days=days), due=BOOKING)
    e = evidence(parts)
    assert e.purchase_within_window is want
    assert e.date_comparison.within_window is want
    assert e.legacy_date_before_window is False
    parts[0].due_date = BOOKING + timedelta(days=3)
    assert evidence(parts).legacy_date_before_window is True
    parts[0].due_date = BOOKING + timedelta(days=2)
    assert evidence(parts).legacy_date_before_window is False


def test_sort_priority_and_account_information():
    from app.finance.bill_candidate_evidence import candidate_sort_key

    parts = example()
    e = evidence(parts)
    assert e.planned_account_matches is None
    parts[0].payment_account_id = parts[2].account_id
    assert evidence(parts).planned_account_matches is True
    parts[0].payment_account_id = uuid.uuid4()
    assert evidence(parts).planned_account_matches is False
    rows = [
        candidate(posting_id=uuid.UUID(int=9), evidence=e),
        candidate(posting_id=uuid.UUID(int=8), evidence=e),
        candidate(amount_minor=9999, evidence=e),
        candidate(evidence=e.model_copy(update={"supplier_name_in_description": False})),
        candidate(legacy_inbox_reference="old", amount_minor=9000, evidence=e),
    ]
    ordered = sorted(rows, key=lambda row: candidate_sort_key(row, 10000))
    assert ordered == [rows[4], rows[1], rows[0], rows[3], rows[2]]
    far = e.model_copy(
        update={"date_comparison": e.date_comparison.model_copy(update={"delta_days": -5})}
    )
    assert candidate_sort_key(candidate(evidence=e), 10000) < candidate_sort_key(
        candidate(evidence=far), 10000
    )
