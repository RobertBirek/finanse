"""Read-only, deterministic candidate evidence; never infer or persist dates."""

import re
import unicodedata
from datetime import date, timedelta

from app.finance.bills_schemas import (
    BillCandidate,
    BillCandidateDateComparison,
    BillCandidateEvidence,
)
from app.finance.models import FinancialDocument, FinancialTransaction, Posting


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(
        char if unicodedata.category(char)[0] in {"L", "N"} else " " for char in normalized
    ).split()


def supplier_name_in_description(supplier_name: str | None, description: str) -> bool:
    description = re.sub(r"^(?:\s*\[actual:[^\]]*\])+", "", description)
    name, words = _tokens(supplier_name or ""), _tokens(description)
    return bool(name) and any(
        words[index : index + len(name)] == name for index in range(len(words) - len(name) + 1)
    )


def build_candidate_evidence(
    bill: FinancialDocument,
    transaction: FinancialTransaction,
    posting: Posting,
    *,
    today: date,
    window_days: int,
) -> BillCandidateEvidence:
    meta = transaction.date_metadata
    if meta is not None and (
        meta.user_id != transaction.user_id
        or transaction.user_id != bill.user_id
        or meta.transaction_id != transaction.id
    ):
        meta = None
    purchase = meta.purchase_date if meta else None
    booking = meta.booking_date if meta else None
    txn_basis: str
    doc_basis: str
    if purchase is not None and bill.sale_date is not None:
        txn_basis, txn_date, doc_basis, doc_date = "purchase", purchase, "sale", bill.sale_date
    elif booking is not None and bill.due_date is not None:
        txn_basis, txn_date, doc_basis, doc_date = "booking", booking, "due", bill.due_date
    elif purchase is not None and bill.issue_date is not None:
        txn_basis, txn_date, doc_basis, doc_date = "purchase", purchase, "issue", bill.issue_date
    elif booking is not None and bill.issue_date is not None:
        txn_basis, txn_date, doc_basis, doc_date = "booking", booking, "issue", bill.issue_date
    else:
        txn_basis = "booking" if booking == transaction.date else "legacy"
        txn_date = transaction.date
        if bill.due_date is not None:
            doc_basis, doc_date = "due", bill.due_date
        elif bill.issue_date is not None:
            doc_basis, doc_date = "issue", bill.issue_date
        elif bill.sale_date is not None:
            doc_basis, doc_date = "sale", bill.sale_date
        else:
            doc_basis, doc_date = "today", today
    delta = (txn_date - doc_date).days
    purchase_reference = bill.sale_date or bill.issue_date
    return BillCandidateEvidence.model_validate(
        {
            "description": transaction.description,
            "currency": "PLN",
            "purchase_date": purchase,
            "booking_date": booking,
            "purchase_date_source": meta.purchase_date_source if meta else None,
            "booking_date_source": meta.booking_date_source if meta else None,
            "date_comparison": BillCandidateDateComparison.model_validate(
                {
                    "transaction_basis": txn_basis,
                    "transaction_date": txn_date,
                    "document_basis": doc_basis,
                    "document_date": doc_date,
                    "delta_days": delta,
                    "within_window": abs(delta) <= window_days,
                }
            ),
            "supplier_name_in_description": supplier_name_in_description(
                bill.supplier_name, transaction.description
            ),
            "planned_account_matches": (
                bill.payment_account_id == posting.account_id if bill.payment_account_id else None
            ),
            "legacy_date_before_window": transaction.date
            < ((bill.due_date or bill.issue_date or today) - timedelta(days=window_days)),
            "purchase_within_window": bool(
                purchase is not None
                and purchase_reference is not None
                and abs((purchase - purchase_reference).days) <= window_days
            ),
        }
    )


def candidate_sort_key(
    candidate: BillCandidate, total_minor: int
) -> tuple[int, int, int, int, str, str]:
    evidence = candidate.evidence
    if evidence is None:
        raise ValueError("candidate_evidence_required")
    return (
        0 if candidate.legacy_inbox_reference else 1,
        abs(candidate.amount_minor - total_minor),
        0 if evidence.supplier_name_in_description else 1,
        abs(evidence.date_comparison.delta_days),
        str(candidate.transaction_id),
        str(candidate.posting_id),
    )
