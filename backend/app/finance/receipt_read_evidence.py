"""Pure provenance and review derivation. Client labels never decide what was edited."""

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from app.documents.receipt_read_models import ReceiptReadExtraction
from app.finance.categorization_context import CategorizationError, digest
from app.finance.receipt_read_contracts import (
    ReceiptReadEvidenceView,
    ReceiptReadProblem,
    ReceiptReadReviewInput,
)
from app.finance.receipt_read_models import ReceiptReadLineage
from app.finance.receipt_schemas import ReceiptBody


@dataclass(frozen=True)
class ReceiptReadLineageData:
    extraction_id: uuid.UUID
    extraction_sha256: str
    body_sha256: str
    line_map: dict[str, Any]
    discount_map: dict[str, Any]
    pending_problem_keys: list[str]
    acknowledgements: dict[str, str]


def receipt_read_problems(
    extraction: ReceiptReadExtraction, header_sha256: str
) -> list[ReceiptReadProblem]:
    problems = [ReceiptReadProblem.model_validate(p) for p in extraction.problems_json]
    if extraction.header_sha256 != header_sha256:
        problems.append(
            ReceiptReadProblem(
                key="context/header_changed/" + header_sha256,
                code="header_changed_since_read",
                message="Nagłówek zmienił się od odczytu zdjęcia. Sprawdź zgodność produktów z aktualnym paragonem.",
                requires_ack=True,
            )
        )
    return problems


def derive_receipt_read_lineage(
    parent: ReceiptReadLineage | None,
    *,
    extraction: ReceiptReadExtraction | None,
    body: ReceiptBody,
    header_sha256: str,
    line_map: dict[str, int] | None = None,
    discount_map: dict[str, int] | None = None,
    review: ReceiptReadReviewInput | None = None,
) -> ReceiptReadLineageData | None:
    if extraction is None:
        if review:
            raise CategorizationError(
                "extraction_review_invalid", "Ten szkic nie ma odczytu do potwierdzenia.", 422
            )
        return None
    original = ReceiptBody.model_validate(extraction.proposal_json["body"])
    raw_lines = {l["index"]: l for l in extraction.payload_json["lines"]}
    raw_discounts = {d["index"]: d for d in extraction.payload_json["discounts"]}
    originals_lines = {int(l.line_key) - 1: l for l in original.lines}
    originals_discounts = {int(d.discount_key) - (1 << 64) - 1: d for d in original.discounts}
    line_indices = (
        line_map
        if line_map is not None
        else {key: value["source_index"] for key, value in parent.line_map.items()}
        if parent
        else {}
    )
    discount_indices = (
        discount_map
        if discount_map is not None
        else {key: value["source_index"] for key, value in parent.discount_map.items()}
        if parent
        else {}
    )
    surviving = {
        str(l.line_key): line_indices[str(l.line_key)]
        for l in body.lines
        if str(l.line_key) in line_indices
    }
    new_lines = {}
    new_discounts = {}
    for line in body.lines:
        key = str(line.line_key)
        if key not in surviving:
            continue
        index = surviving[key]
        old_line = originals_lines[index]
        fields: dict[str, Any] = {"name": old_line.name, "amount_minor": old_line.amount_minor}
        hashes = {k: digest({"value": v}) for k, v in fields.items()}
        new_lines[key] = {
            "source_index": index,
            "original_field_sha256": hashes,
            "edited_fields": [
                k for k in fields if hashes[k] != digest({"value": getattr(line, k)})
            ],
            "source_text": raw_lines[index]["source_text"],
            "basis": raw_lines[index]["basis"],
        }
    for discount in body.discounts:
        key = str(discount.discount_key)
        if key not in discount_indices:
            continue
        index = discount_indices[key]
        old_discount = originals_discounts[index]

        def source_shares(shares: list[Any], original: bool) -> list[dict[str, Any]]:
            return sorted(
                [
                    {
                        "source_index": int(s.line_key) - 1
                        if original
                        else surviving.get(str(s.line_key), str(s.line_key)),
                        "amount_minor": s.amount_minor,
                    }
                    for s in shares
                ],
                key=lambda r: str(r["source_index"]),
            )

        fields = {
            "name": old_discount.name,
            "amount_minor": old_discount.amount_minor,
            "shares": source_shares(old_discount.shares, True),
        }
        current = {
            "name": discount.name,
            "amount_minor": discount.amount_minor,
            "shares": source_shares(discount.shares, False),
        }
        hashes = {k: digest({"value": v}) for k, v in fields.items()}
        new_discounts[key] = {
            "source_index": index,
            "original_field_sha256": hashes,
            "edited_fields": [k for k in fields if hashes[k] != digest({"value": current[k]})],
            "source_text": raw_discounts[index]["source_text"],
            "kind": raw_discounts[index]["kind"],
        }
    # Sort shares in exactly the same way as append_receipt_revision's canonical body.
    canonical = body.model_copy(deep=True)
    for discount in canonical.discounts:
        discount.shares.sort(key=lambda s: str(s.line_key))
    body_sha = digest(canonical.model_dump(mode="json"))
    binding = digest(
        {
            "body_sha256": body_sha,
            "header_sha256": header_sha256,
            "extraction_sha256": extraction.payload_sha256,
        }
    )
    problems = receipt_read_problems(extraction, header_sha256)
    required = {p.key for p in problems if p.requires_ack}
    acknowledgements = (
        {k: v for k, v in parent.acknowledgements.items() if k in required and v == binding}
        if parent
        else {}
    )
    if review:
        if (
            review.extraction_id != extraction.id
            or review.expected_extraction_sha256 != extraction.payload_sha256
        ):
            raise CategorizationError("extraction_changed", "Dowód odczytu zmienił się.")
        keys = set(review.acknowledged_problem_keys)
        if not keys <= required or len(keys) != len(review.acknowledged_problem_keys):
            raise CategorizationError(
                "extraction_review_invalid", "Potwierdzenia dotyczą nieznanych problemów.", 422
            )
        acknowledgements = {key: binding for key in keys}
    return ReceiptReadLineageData(
        extraction.id,
        extraction.payload_sha256,
        body_sha,
        new_lines,
        new_discounts,
        sorted(required - set(acknowledgements)),
        acknowledgements,
    )


def receipt_read_evidence_view(
    data: ReceiptReadLineageData, extraction: ReceiptReadExtraction, header_sha256: str
) -> ReceiptReadEvidenceView:
    return ReceiptReadEvidenceView(
        extraction_id=extraction.id,
        extraction_sha256=extraction.payload_sha256,
        job_id=extraction.job_id,
        source_document_id=extraction.document_id,
        source_sha256=extraction.source_sha256,
        line_map=data.line_map,
        discount_map=data.discount_map,
        pending_problems=[
            p
            for p in receipt_read_problems(extraction, header_sha256)
            if p.key in data.pending_problem_keys
        ],
        acknowledgements=data.acknowledgements,
    )


def lineage_values(data: ReceiptReadLineageData) -> dict[str, Any]:
    return asdict(data)
