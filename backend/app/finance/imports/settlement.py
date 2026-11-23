"""Owner-scoped statement suggestions and atomic one-to-one confirmation."""

import re
import uuid
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.finance.imports.commit import commit_with_preparation
from app.finance.imports.contracts import StatementRow
from app.finance.imports.decisions import (
    load_batch,
    normalized_reference,
    save_decisions,
    signed_posting,
)
from app.finance.imports.errors import ImportError
from app.finance.imports.matching import candidate_postings
from app.finance.imports.models import ImportEvidence, ImportRevision, ImportSource
from app.finance.imports.preview import digest, prepare_preview, record, statement_opening_gap
from app.finance.imports.queries import get_batch, list_rows
from app.finance.imports.schemas import (
    CommitRequest,
    CommitResult,
    DecisionUpdate,
    ImportDecisionInput,
    PreviewRequest,
    SourceDTO,
)
from app.finance.imports.settlement_policy import (
    Match,
    description_key,
    distinct_category,
    repeated_targets,
    settlement_kind,
    strict_match,
)
from app.finance.imports.settlement_schemas import (
    SettlementConfirm,
    SettlementPreview,
    SettlementRow,
    SettlementTarget,
)
from app.finance.models import Account, Category, FinancialTransaction, Posting
from app.finance.queries import lock_accounts


def source_usable(
    source: SourceDTO, db_source: ImportSource, revision: ImportRevision, account: Account
) -> bool:
    bank = re.sub(r"[^a-z]", "", (account.bank_name or "").lower())
    reference = db_source.account_reference or (revision.result or {}).get("account_reference")
    return (
        source.processing_state == "ready"
        and source.validation_state != "blocked"
        and source.candidate_revision_id is None
        and (source.auto_post is None or source.auto_post.state != "queued")
        and all(check.result == "passed" for check in source.checks if check.required)
        and ((source.layout == "velo_card_v1") == (account.type == "credit_card"))
        and (not bank or bool(source.bank and source.bank in bank))
        and (
            not isinstance(reference, str)
            or not account.iban
            or normalized_reference(reference) == normalized_reference(account.iban)
        )
    )


def _may_duplicate(value: StatementRow, other: StatementRow) -> bool:
    return bool(
        other.state == "posted"
        and other.currency == value.currency
        and (
            (value.bank_reference and value.bank_reference == other.bank_reference)
            or (
                value.booking_date
                and other.booking_date
                and abs((value.booking_date - other.booking_date).days) <= 3
                and value.amount == other.amount
            )
        )
    )


async def _previous_categories(
    db: AsyncSession, owner: uuid.UUID, account: uuid.UUID
) -> dict[tuple[str, str], set[uuid.UUID]]:
    category_posting = aliased(Posting)
    rows = await db.execute(
        select(FinancialTransaction.type, FinancialTransaction.description, Category.id)
        .select_from(FinancialTransaction)
        .join(Posting, Posting.transaction_id == FinancialTransaction.id)
        .join(category_posting, category_posting.transaction_id == FinancialTransaction.id)
        .join(Category, Category.id == category_posting.category_id)
        .where(
            FinancialTransaction.user_id == owner,
            FinancialTransaction.is_pending.is_(False),
            FinancialTransaction.created_by == "human",
            FinancialTransaction.type.in_(("expense", "income")),
            Posting.account_id == account,
            Category.user_id == owner,
            Category.is_active.is_(True),
            Category.type == FinancialTransaction.type,
        )
        .distinct()
    )
    result: dict[tuple[str, str], set[uuid.UUID]] = {}
    for kind, description, category_id in rows:
        result.setdefault((kind, description_key(description)), set()).add(category_id)
    return result


async def settlement_preview(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, account_id: uuid.UUID
) -> SettlementPreview:
    batch = await load_batch(db, owner, batch_id)
    version = batch.version
    account = await db.scalar(
        select(Account)
        .where(Account.id == account_id, Account.user_id == owner)
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise ImportError("account_not_found", "Nie znaleziono rachunku.", 404)
    if (
        not account.is_active
        or account.currency != "PLN"
        or account.type
        not in {
            "checking",
            "savings",
            "credit_card",
        }
    ):
        raise ImportError(
            "settlement_account_unavailable", "Wybierz aktywny rachunek lub kartę w PLN.", 422
        )

    details = await get_batch(db, owner, batch_id)
    if details is None:
        raise ImportError("settlement_stale", "Import zmienił się; przygotuj podgląd ponownie.")
    page = await list_rows(db, owner, batch_id, source_id=None, offset=0, limit=100)
    if page.total > settings.FINANCE_IMPORT_AUTO_POST_MAX_ROWS:
        raise ImportError("too_many_rows", "Wyciąg jest zbyt duży do zbiorczego przeglądu.", 422)
    rows = list(page.items)
    for offset in range(100, page.total, 100):
        following = await list_rows(db, owner, batch_id, source_id=None, offset=offset, limit=100)
        if following.total != page.total:
            raise ImportError("settlement_stale", "Odczyt zmienił się; przygotuj podgląd ponownie.")
        rows.extend(following.items)
    if len({row.id for row in rows}) != page.total:
        raise ImportError("settlement_stale", "Odczyt zmienił się; przygotuj podgląd ponownie.")
    source_map = {source.id: source for source in details.sources}
    source_records = {
        source.id: (source, revision)
        for source, revision in (
            await db.execute(
                select(ImportSource, ImportRevision)
                .join(ImportRevision, ImportRevision.id == ImportSource.current_revision_id)
                .where(
                    ImportSource.user_id == owner,
                    ImportSource.batch_id == batch_id,
                    ImportRevision.user_id == owner,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    linked = (
        await db.execute(
            select(
                ImportEvidence.row_id, ImportEvidence.transaction_id, ImportEvidence.batch_id
            ).where(ImportEvidence.user_id == owner)
        )
    ).all()
    settled = {row_id for row_id, _, existing_batch in linked if existing_batch == batch_id}
    # The bulk workflow never reuses a transaction, even on a repeated bank reference.
    used = {transaction_id for _, transaction_id, _ in linked}
    grouped = {row_id for group in details.groups for row_id in group.row_ids}
    for group in details.groups:
        if group.decision and group.decision.get("action") == "link":
            target = group.decision.get("existing_transaction_id")
            if isinstance(target, str):
                used.add(uuid.UUID(target))

    ledger = (
        await db.execute(
            select(Posting, FinancialTransaction)
            .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
            .where(Posting.account_id == account.id, FinancialTransaction.user_id == owner)
            .order_by(Posting.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    pending = {
        (txn.date, posting.source_currency, abs(posting.source_amount))
        for posting, txn in ledger
        if txn.is_pending
    }
    by_description: dict[str, set[tuple[date, uuid.UUID]]] = {}
    for _, txn in ledger:
        key = description_key(txn.description)
        if key:
            by_description.setdefault(key, set()).add((txn.date, txn.id))
    past = await _previous_categories(db, owner, account.id)
    categories = (
        await db.scalars(
            select(Category)
            .where(Category.user_id == owner, Category.is_active.is_(True))
            .order_by(Category.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    opening_gaps: dict[uuid.UUID, bool] = {}
    values = [(row, row.bank_fields) for row in rows if row.bank_fields is not None]
    proposals: list[SettlementRow] = []
    for row, value in values:
        proposal = SettlementRow(
            id=row.id,
            description=value.description,
            date=value.booking_date,
            amount=value.amount,
            currency=value.currency,
            status="review",
            reason="movement_unclear",
        )
        proposals.append(proposal)
        if row.id in settled:
            proposal.status, proposal.reason = "settled", "recorded_evidence"
            continue
        if row.id in grouped:
            proposal.reason = "saved_decision"
            continue
        source = source_map.get(row.source_id)
        source_record = source_records.get(row.source_id)
        if source is None or source_record is None or source_record[1].id != row.revision_id:
            raise ImportError("settlement_stale", "Odczyt zmienił się; przygotuj podgląd ponownie.")
        db_source, revision = source_record
        if not source_usable(source, db_source, revision, account):
            proposal.reason = "source_or_account_review"
            continue
        if value.currency != "PLN":
            proposal.reason = "fx_review"
            continue
        kind = settlement_kind(source.bank or "", source.layout, value)
        if kind is None or value.booking_date is None or not value.description.strip():
            continue
        if any(other.id != row.id and _may_duplicate(value, field) for other, field in values):
            proposal.reason = "possible_duplicate"
            continue
        candidates = await candidate_postings(db, owner, row.id, account.id)
        desc = description_key(value.description)
        measured = {txn.id for _, txn, _ in candidates}
        if any(
            target not in measured and abs((day - value.booking_date).days) <= 3
            for day, target in by_description.get(desc, set())
        ):
            proposal.reason = "possible_duplicate"
            continue
        choice = strict_match(
            value,
            [
                Match(
                    txn.id,
                    txn.type,
                    txn.description,
                    txn.date,
                    signed_posting(posting),
                    candidate.strength == "strong",
                )
                for candidate, txn, posting in candidates
            ],
            used,
        )
        if any(
            amount == abs(value.amount)
            and currency == value.currency
            and abs((day - value.booking_date).days) <= 3
            for day, currency, amount in pending
        ) or (candidates and (choice is None or choice.kind != kind)):
            proposal.reason = "possible_duplicate"
            continue
        proposal.kind = kind
        if choice is None:
            proposal.status, proposal.reason = "create", "no_existing_candidate"
            proposal.category_id = distinct_category(past.get((kind, desc), set()))
        else:
            assert choice.booking_date is not None
            proposal.status = "link"
            proposal.reason = (
                "same_bank_reference" if choice.bank_reference else "exact_statement_match"
            )
            proposal.target = SettlementTarget(
                id=choice.transaction_id, description=choice.description, date=choice.booking_date
            )
        if row.source_id not in opening_gaps:
            result = revision.result or {}
            opening, start = result.get("opening"), result.get("period_start")
            opening_gaps[row.source_id] = bool(
                type(opening) is int
                and isinstance(start, str)
                and await statement_opening_gap(
                    db, owner, account.id, date.fromisoformat(start), opening
                )
            )
        if opening_gaps[row.source_id]:
            proposal.acknowledgement = f"opening_gap:{row.source_id}"

    repeated = repeated_targets(item.target.id for item in proposals if item.target is not None)
    for item in proposals:
        if item.target is not None and item.target.id in repeated:
            item.status, item.reason = "review", "possible_duplicate"
            item.target, item.kind, item.acknowledgement = None, None, None
    fingerprint = digest(
        {
            "owner": str(owner),
            "batch": str(batch_id),
            "version": version,
            "account": record(account),
            "source_heads": sorted(
                (str(key), str(value.current_revision_id)) for key, value in source_map.items()
            ),
            "ledger": [[record(posting), record(txn)] for posting, txn in ledger],
            "categories": [record(category) for category in categories],
            "proposals": [item.model_dump(mode="json") for item in proposals],
        }
    )
    await db.refresh(batch, attribute_names=["version"])
    if version != batch.version or version != details.version:
        raise ImportError("settlement_stale", "Import zmienił się; przygotuj podgląd ponownie.")
    return SettlementPreview(
        batch_id=batch_id,
        account_id=account_id,
        version=version,
        fingerprint=fingerprint,
        rows=proposals,
    )


async def confirm_settlement(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: SettlementConfirm, key: str
) -> CommitResult:
    async def prepare() -> CommitRequest:
        await load_batch(db, owner, batch_id, locked=True)
        await lock_accounts(db, owner, {data.account_id}, exclusive=True)
        view = await settlement_preview(db, owner, batch_id, data.account_id)
        if view.fingerprint != data.fingerprint:
            raise ImportError(
                "settlement_stale", "Księga lub import zmieniły się; przygotuj podgląd ponownie."
            )
        available = {row.id: row for row in view.rows}
        decisions = []
        required = set()
        targets: list[uuid.UUID] = []
        for selection in data.selection:
            row = available.get(selection.row_id)
            if row is None or row.status not in {"create", "link"} or row.kind is None:
                raise ImportError(
                    "settlement_selection_invalid", "Wybrany wiersz wymaga odrębnej decyzji.", 422
                )
            action: Literal["link", "create"] = "link" if row.status == "link" else "create"
            category = selection.category_id or row.category_id
            if row.acknowledgement:
                required.add(row.acknowledgement)
            if action == "create" and category is None:
                raise ImportError(
                    "category_unavailable", "Wybierz kategorię dla nowej operacji.", 422
                )
            target = row.target.id if row.target else None
            if target is not None:
                targets.append(target)
            decisions.append(
                ImportDecisionInput(
                    group_id=uuid.uuid4(),
                    row_ids=[row.id],
                    action=action,
                    kind=row.kind,
                    account_id=data.account_id,
                    existing_transaction_id=target,
                    category_id=category if action == "create" else None,
                )
            )
        if repeated_targets(targets):
            raise ImportError(
                "settlement_selection_invalid",
                "Nie można powiązać kilku wierszy z jedną transakcją.",
                422,
            )
        if required != set(data.acknowledgements):
            raise ImportError(
                "settlement_acknowledgement_required", "Potwierdź pokazaną różnicę salda otwarcia."
            )
        reviewed = await save_decisions(
            db, owner, batch_id, DecisionUpdate(expected_version=view.version, decisions=decisions)
        )
        frozen = await prepare_preview(
            db,
            owner,
            batch_id,
            PreviewRequest(
                expected_version=reviewed.version,
                group_ids=[item.group_id for item in decisions],
                acknowledgements=data.acknowledgements,
            ),
        )
        return CommitRequest(preview_id=frozen.id, request_hash=frozen.request_hash)

    return await commit_with_preparation(
        db, owner, batch_id, key, {"statement_settlement": data.model_dump(mode="json")}, prepare
    )
