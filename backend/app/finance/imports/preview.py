"""Immutable reviewed server plans; quotes before locks, fingerprints before any future commit."""

import asyncio
import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.import_storage import ImportStorageError, read_import_original
from app.documents.models import Document
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.card_statements import validate_card_header
from app.finance.imports.contracts import ParsedStatement
from app.finance.imports.decisions import (
    ReviewedRow,
    load_batch,
    signed_posting,
    validate_decision,
    validate_link,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.matching import candidate_postings
from app.finance.imports.models import (
    ImportDecision,
    ImportGroup,
    ImportGroupRow,
    ImportPreview,
    ImportRevision,
)
from app.finance.imports.schemas import ImportDecisionInput, PreviewDTO, PreviewRequest
from app.finance.imports.valuation import freeze_exchange, freeze_quote
from app.finance.models import Account, Category, FinancialTransaction, Posting


def canonical(value: object) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")))


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(canonical(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def record(value: Any) -> dict[str, Any]:
    return canonical({column.key: getattr(value, column.key) for column in value.__table__.columns})


def revision_record(revision: ImportRevision) -> dict[str, Any]:
    values = record(revision)
    values["result_sha256"] = digest(values.pop("result"))
    return values


async def _snapshot(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, group_ids: list[uuid.UUID]
):
    batch = await load_batch(db, owner, batch_id)
    groups = []
    contexts: list[tuple[ImportDecisionInput, list[ReviewedRow]]] = []
    accounts: set[uuid.UUID] = set()
    categories: set[uuid.UUID] = set()
    required: set[str] = set()
    warnings: set[str] = set()
    source_records = {}
    candidate_records = {}
    for group_id in sorted(group_ids, key=str):
        group = await db.scalar(
            select(ImportGroup)
            .where(
                ImportGroup.id == group_id,
                ImportGroup.user_id == owner,
                ImportGroup.batch_id == batch_id,
            )
            .execution_options(populate_existing=True)
        )
        if group is None:
            raise ImportError("group_not_found", "Nie znaleziono grupy.", 404)
        if group.state != "ready":
            raise ImportError("group_not_ready", "Podgląd wymaga pełnej nierozliczonej grupy.")
        decision_record = await db.scalar(
            select(ImportDecision)
            .where(
                ImportDecision.group_id == group_id,
                ImportDecision.user_id == owner,
                ImportDecision.version == group.version,
            )
            .execution_options(populate_existing=True)
        )
        if decision_record is None:
            raise ImportError("decision_missing", "Brak bieżącej decyzji grupy.")
        decision = ImportDecisionInput.model_validate(decision_record.data)
        members = list(
            (
                await db.scalars(
                    select(ImportGroupRow)
                    .where(
                        ImportGroupRow.group_id == group_id,
                        ImportGroupRow.user_id == owner,
                        ImportGroupRow.batch_id == batch_id,
                    )
                    .order_by(ImportGroupRow.row_id)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        if {member.row_id for member in members} != set(decision.row_ids):
            raise ImportError(
                "group_membership_conflict", "Skład grupy zmienił się; sprawdź decyzję."
            )
        rows = await validate_decision(db, owner, batch, decision)
        contexts.append((decision, rows))
        groups.append(
            {
                "group": record(group),
                "decision": record(decision_record),
                "membership": [record(member) for member in members],
                "rows": [record(row.row) for row in rows],
            }
        )
        if decision.account_id:
            accounts.add(decision.account_id)
        if decision.other_account_id:
            accounts.add(decision.other_account_id)
        categories.update(
            value for value in [decision.category_id, decision.fee_category_id] if value
        )
        for row in rows:
            if row.source.id not in source_records:
                document = await db.scalar(
                    select(Document)
                    .where(Document.id == row.source.document_id, Document.user_id == owner)
                    .execution_options(populate_existing=True)
                )
                if document is None or document.archived_at is not None:
                    raise ImportError("source_unavailable", "Oryginał źródła jest niedostępny.")
                try:
                    await asyncio.to_thread(read_import_original, document)
                except ImportStorageError as error:
                    raise ImportError(
                        error.code,
                        "Nie udało się zweryfikować oryginału źródła.",
                        error.http_status,
                    ) from error
                candidate = await db.scalar(
                    select(ImportRevision)
                    .where(
                        ImportRevision.source_id == row.source.id, ImportRevision.user_id == owner
                    )
                    .order_by(ImportRevision.number.desc())
                    .limit(1)
                    .execution_options(populate_existing=True)
                )
                source_records[row.source.id] = {
                    "source": record(row.source),
                    "revision": revision_record(row.revision),
                    "candidate_revision": revision_record(candidate)
                    if candidate and candidate.id != row.revision.id
                    else None,
                    "document": record(document),
                }
            assert row.account is not None
            source_result = row.revision.result or {}
            opening = source_result.get("opening")
            start = source_result.get("period_start")
            if type(opening) is int and isinstance(start, str):
                ledger_opening = int(
                    await db.scalar(
                        select(
                            func.coalesce(
                                func.sum(
                                    case(
                                        (Posting.direction == "credit", Posting.source_amount),
                                        else_=-Posting.source_amount,
                                    )
                                ),
                                0,
                            )
                        )
                        .join(
                            FinancialTransaction, FinancialTransaction.id == Posting.transaction_id
                        )
                        .where(
                            Posting.account_id == row.account.id,
                            FinancialTransaction.user_id == owner,
                            FinancialTransaction.date < date.fromisoformat(start),
                            FinancialTransaction.is_pending.is_(False),
                        )
                    )
                    or 0
                )
                if ledger_opening != opening:
                    required.add(f"opening_gap:{row.source.id}")
            for warning in row.revision.warnings:
                warnings.add(f"source_warning:{row.source.id}:{warning}")
            candidates = await candidate_postings(db, owner, row.row.id, row.account.id)
            candidate_records[row.row.id] = [
                {
                    "candidate": candidate.model_dump(mode="json"),
                    "transaction": record(transaction),
                    "posting": record(posting),
                }
                for candidate, transaction, posting in candidates
            ]
            if candidates and decision.action == "create":
                required.add(f"possible_duplicate:{row.row.id}")
            if decision.action == "link" and row.value.fee:
                warnings.add(f"cost_split_unreconciled:{row.row.id}")
        if len({row.value.booking_date for row in rows}) > 1:
            required.add(f"transfer_date_difference:{decision.group_id}")
    account_records = list(
        (
            await db.scalars(
                select(Account)
                .where(Account.user_id == owner, Account.id.in_(accounts))
                .order_by(Account.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    category_records = list(
        (
            await db.scalars(
                select(Category)
                .where(Category.user_id == owner, Category.id.in_(categories))
                .order_by(Category.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    # Hash every posting/transaction touching selected accounts, not just net balances:
    # concurrent cancelling movements and newly created duplicate candidates still stale.
    ledger = (
        await db.execute(
            select(Posting, FinancialTransaction)
            .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
            .where(Posting.account_id.in_(accounts), FinancialTransaction.user_id == owner)
            .order_by(Posting.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    balances = {str(account_id): {"source": 0, "base": 0} for account_id in accounts}
    for posting, _transaction in ledger:
        balances[str(posting.account_id)]["source"] += signed_posting(posting)
        balances[str(posting.account_id)]["base"] += (
            -posting.base_amount_pln if posting.direction == "debit" else posting.base_amount_pln
        )
    snapshot = canonical(
        {
            "batch": record(batch),
            "groups": groups,
            "sources": {str(key): value for key, value in source_records.items()},
            "accounts": [record(account) for account in account_records],
            "categories": [record(category) for category in category_records],
            "ledger_balances": balances,
            "ledger_digest": digest(
                [[record(posting), record(transaction)] for posting, transaction in ledger]
            ),
            "candidates": {str(key): value for key, value in candidate_records.items()},
        }
    )
    return snapshot, contexts, sorted(required), sorted(warnings)


def _posting(
    account_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    amount: int,
    currency: str,
    base: int,
    rate: Decimal,
    source: str,
    *,
    incoming: bool,
) -> dict[str, Any]:
    return {
        "account_id": str(account_id) if account_id else None,
        "category_id": str(category_id) if category_id else None,
        "source_amount": abs(amount),
        "source_currency": currency,
        "base_amount_pln": base,
        "fx_rate": str(rate),
        "fx_rate_source": source,
        "direction": "credit" if incoming else "debit",
    }


async def _financial_plan(
    db: AsyncSession, owner: uuid.UUID, decision: ImportDecisionInput, rows: list[ReviewedRow]
) -> dict[str, Any]:
    if decision.action == "link":
        postings = await validate_link(db, owner, decision, rows)
        return {
            "group_id": str(decision.group_id),
            "action": "link",
            "transaction_id": str(decision.existing_transaction_id),
            "links": [
                {
                    "row_id": str(row.row.id),
                    "posting_id": str(posting.id),
                    "component": "whole",
                    "attributed_source_amount": row.value.amount,
                }
                for row, posting in zip(rows, postings, strict=True)
            ],
            "operations": [],
        }
    operations = []
    internal = decision.kind in {"transfer", "exchange"}
    if internal:
        if len(rows) == 2:
            outgoing = next(row for row in rows if row.value.amount + row.value.fee < 0)
            incoming = next(row for row in rows if row.value.amount + row.value.fee > 0)
            assert outgoing.account is not None and incoming.account is not None
            from_id, to_id = outgoing.account.id, incoming.account.id
            from_amount, to_amount = (
                -(outgoing.value.amount + outgoing.value.fee),
                incoming.value.amount + incoming.value.fee,
            )
            from_currency, to_currency = outgoing.value.currency, incoming.value.currency
        else:
            outgoing = rows[0]
            assert outgoing.account is not None and decision.other_account_id is not None
            other = await db.get(Account, decision.other_account_id)
            if other is None:
                raise ImportError("account_not_found", "Brak drugiego rachunku.", 404)
            amount = outgoing.value.amount + outgoing.value.fee
            from_id, to_id = (
                (outgoing.account.id, other.id) if amount < 0 else (other.id, outgoing.account.id)
            )
            from_amount = to_amount = abs(amount)
            from_currency = to_currency = outgoing.value.currency
        booking = outgoing.value.booking_date
        assert booking is not None
        if decision.kind == "exchange":
            value = await freeze_exchange(
                from_currency,
                from_amount,
                to_currency,
                to_amount,
                booking,
                manual_rate=decision.manual_rate,
            )
            base, from_rate, to_rate = value.base_pln, value.from_rate, value.to_rate
            from_source, to_source = value.from_source, value.to_source
            quote = canonical(asdict(value))
        else:
            frozen = await freeze_quote(
                from_currency, from_amount, booking, manual_rate=decision.manual_rate
            )
            base, from_rate, to_rate = frozen.base_amount, frozen.rate, frozen.rate
            from_source = to_source = frozen.source
            quote = canonical(asdict(frozen))
        operations.append(
            {
                "kind": decision.kind,
                "component": "main",
                "row_ids": [str(row.row.id) for row in rows],
                "booking_date": booking.isoformat(),
                "purchase_date": outgoing.value.operation_date.isoformat()
                if outgoing.value.operation_date
                else None,
                "description": outgoing.value.description,
                "quote": quote,
                "postings": [
                    _posting(
                        from_id,
                        None,
                        from_amount,
                        from_currency,
                        base,
                        from_rate,
                        from_source,
                        incoming=False,
                    ),
                    _posting(
                        to_id, None, to_amount, to_currency, base, to_rate, to_source, incoming=True
                    ),
                ],
            }
        )
    for row in rows:
        assert row.account is not None and row.value.booking_date is not None
        components = (
            [("main", row.value.amount + row.value.fee, decision.category_id)]
            if not internal
            else []
        )
        if row.value.fee:
            components.append(("fee", -row.value.fee, decision.fee_category_id))
        for component, amount, category in components:
            if not amount:
                continue
            quote = await freeze_quote(
                row.value.currency,
                abs(amount),
                row.value.booking_date,
                manual_rate=decision.manual_rate,
            )
            kind = (
                "expense_refund"
                if component == "fee" and amount > 0
                else "expense"
                if component == "fee"
                else decision.kind
            )
            operations.append(
                {
                    "kind": kind,
                    "component": component,
                    "row_ids": [str(row.row.id)],
                    "booking_date": row.value.booking_date.isoformat(),
                    "purchase_date": row.value.operation_date.isoformat()
                    if row.value.operation_date
                    else None,
                    "description": row.value.description,
                    "quote": canonical(asdict(quote)),
                    "postings": [
                        _posting(
                            row.account.id,
                            None,
                            amount,
                            row.value.currency,
                            quote.base_amount,
                            quote.rate,
                            quote.source,
                            incoming=amount > 0,
                        ),
                        _posting(
                            None,
                            category,
                            amount,
                            row.value.currency,
                            quote.base_amount,
                            quote.rate,
                            quote.source,
                            incoming=amount < 0,
                        ),
                    ],
                }
            )
    return {"group_id": str(decision.group_id), "action": "create", "operations": operations}


async def _plan(
    db: AsyncSession, owner: uuid.UUID, decision: ImportDecisionInput, rows: list[ReviewedRow]
) -> dict[str, Any]:
    plan = await _financial_plan(db, owner, decision, rows)
    if decision.card_header is not None:
        statement = validate_card_header(
            ParsedStatement.model_validate(rows[0].revision.result), decision.card_header
        )
        plan["card_statement"] = {
            "source_id": str(rows[0].source.id),
            "account_id": str(decision.card_header.account_id),
            "data": statement.model_dump(mode="json"),
        }
    return plan


async def prepare_preview(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: PreviewRequest
) -> PreviewDTO:
    batch = await load_batch(db, owner, batch_id)
    if batch.version != data.expected_version:
        raise ImportError("import_version_conflict", "Import zmienił się; odśwież decyzje.")
    before, contexts, required, warnings = await _snapshot(db, owner, batch_id, data.group_ids)
    if set(required) - set(data.acknowledgements):
        raise ImportError(
            "import_acknowledgement_required", "Wymagane potwierdzenia: " + ", ".join(required), 409
        )
    # All external quote I/O completes before taking the owner/batch write locks.
    plans = [await _plan(db, owner, decision, rows) for decision, rows in contexts]
    await lock_document_mutations(db, owner)
    batch = await load_batch(db, owner, batch_id, locked=True)
    after, _contexts, required_after, warnings_after = await _snapshot(
        db, owner, batch_id, data.group_ids
    )
    if before != after or batch.version != data.expected_version or required_after != required:
        raise ImportError(
            "preview_stale", "Dane zmieniły się podczas wyceny; przygotuj podgląd ponownie."
        )
    payload = canonical(
        {
            "owner_id": str(owner),
            "batch_id": str(batch_id),
            "version": batch.version,
            "group_ids": [str(item) for item in sorted(data.group_ids, key=str)],
            "snapshot": after,
            "plans": plans,
            "acknowledgements": sorted(set(data.acknowledgements)),
            "required_acknowledgements": required_after,
            "warnings": sorted(set(warnings + warnings_after + required_after)),
        }
    )
    preview = ImportPreview(
        user_id=owner,
        batch_id=batch_id,
        version=batch.version,
        request_hash=digest(payload),
        payload=payload,
    )
    db.add(preview)
    await log_event(
        db,
        owner,
        "bank_import_preview",
        str(batch_id),
        "prepare_preview",
        new_state={"version": batch.version, "request_hash": preview.request_hash},
    )
    await db.flush()
    return PreviewDTO(
        id=preview.id,
        batch_id=batch_id,
        version=batch.version,
        request_hash=preview.request_hash,
        new_transaction_count=sum(len(plan["operations"]) for plan in plans),
        linked_transaction_count=sum(plan["action"] == "link" for plan in plans),
        warnings=payload["warnings"],
        payload=payload,
    )


async def canonical_preview_payload(
    db: AsyncSession, owner: uuid.UUID, preview_id: uuid.UUID
) -> dict[str, object]:
    preview = await db.scalar(
        select(ImportPreview).where(ImportPreview.id == preview_id, ImportPreview.user_id == owner)
    )
    if preview is None:
        raise ImportError("preview_not_found", "Nie znaleziono podglądu.", 404)
    payload: dict[str, Any] = canonical(preview.payload)
    if digest(payload) != preview.request_hash or payload.get("owner_id") != str(owner):
        raise ImportError("preview_stale", "Podgląd jest niespójny.")
    try:
        snapshot, _contexts, required, _warnings = await _snapshot(
            db, owner, preview.batch_id, [uuid.UUID(value) for value in payload["group_ids"]]
        )
    except ImportError as error:
        if error.code in {"source_integrity_failed", "source_size_limit"}:
            raise
        raise ImportError(
            "preview_stale", "Dane podglądu zmieniły się; wymagane ponowne potwierdzenie."
        ) from error
    if snapshot != payload["snapshot"] or required != payload["required_acknowledgements"]:
        raise ImportError(
            "preview_stale", "Dane podglądu zmieniły się; wymagane ponowne potwierdzenie."
        )
    return payload
