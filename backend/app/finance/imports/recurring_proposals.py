"""Read-only adapter for conservative recurring-expense proposals from statement rows."""

from __future__ import annotations

import re
import uuid
from calendar import monthrange
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.finance.imports.contracts import StatementRow
from app.finance.imports.decisions import normalized_reference
from app.finance.imports.models import (
    ImportBankIdentity,
    ImportEvidence,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.recurring_detection import (
    DAY_TOLERANCE,
    NewScheduleProposal,
    RecurrenceAnalysis,
    RecurrenceEvidence,
    VerifiedExpenseObservation,
    _merchant_key,
    analyze_new_recurring_schedule,
)
from app.finance.models import Account, FinancialTransaction, Posting, ScheduledFinanceItem

MAX_CANDIDATE_HISTORY_OBSERVATIONS = 26
HISTORY_LOOKBACK_YEARS = 2


def _normalized_description_expression() -> ColumnElement[str]:
    # PostgreSQL NORMALIZE takes a grammar keyword rather than a bound string.
    return func.lower(
        func.normalize(ImportRow.fields["description"].as_string(), literal_column("NFKC"))
    )


class RecurringProposalResponse(BaseModel):
    """Advisory result only; neither a schedule nor a ledger entry is created."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    reason: str | None = None
    proposal: NewScheduleProposal | None = None
    evidence: tuple[RecurrenceEvidence, ...] = ()


def proposal_response(analysis: RecurrenceAnalysis) -> RecurringProposalResponse:
    return RecurringProposalResponse(
        status=analysis.status,
        reason=analysis.reason,
        proposal=analysis.proposal,
        evidence=analysis.evidence,
    )


def _uncertain(
    reason: str, current: VerifiedExpenseObservation | None = None
) -> RecurrenceAnalysis:
    evidence = (
        (
            RecurrenceEvidence(
                strong_identity=current.strong_identity,
                economic_identity=current.economic_identity,
                source=current.source,
                occurred_on=current.occurred_on,
                amount_minor=current.amount_minor,
                currency=current.currency,
            ),
        )
        if current is not None
        else ()
    )
    return RecurrenceAnalysis(status="uncertain", reason=reason, evidence=evidence)


def _source_binds_account(
    source: ImportSource, revision_result: dict[str, object] | None, account: Account
) -> bool:
    """Require the same source/account provenance as statement review decisions."""
    reference = source.account_reference or (revision_result or {}).get("account_reference")
    bank = re.sub(r"[^a-z]", "", (account.bank_name or "").lower())
    return bool(
        isinstance(reference, str)
        and reference
        and account.iban
        and normalized_reference(reference) == normalized_reference(account.iban)
        and source.bank
        and bank
        and source.bank in bank
    )


def _historical_reference_matches_identity(
    value: StatementRow, strong_reference: str | None
) -> bool:
    """A group identity is usable only for the exact parsed source reference."""
    return bool(
        value.bank_reference and strong_reference and value.bank_reference == strong_reference
    )


def _history_start(observed_on: date) -> date:
    """Keep candidate history finite while retaining evidence for annual cadence."""
    year = observed_on.year - HISTORY_LOOKBACK_YEARS
    anniversary = date(
        year, observed_on.month, min(observed_on.day, monthrange(year, observed_on.month)[1])
    )
    return anniversary - timedelta(days=DAY_TOLERANCE)


def _history_end(observed_on: date) -> date:
    """Include the same bounded tolerance after the current observation."""
    return observed_on + timedelta(days=DAY_TOLERANCE)


async def _current_observation(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    row_id: uuid.UUID,
    account_id: uuid.UUID,
) -> tuple[VerifiedExpenseObservation | None, str | None]:
    """Read an immutable *current* source row; no row ID is treated as transaction identity."""
    record = (
        await db.execute(
            select(ImportRow, ImportSource, ImportRevision, Account)
            .join(
                ImportSource,
                (ImportSource.id == ImportRow.source_id) & (ImportSource.user_id == owner),
            )
            .join(
                ImportRevision,
                (ImportRevision.id == ImportRow.revision_id) & (ImportRevision.user_id == owner),
            )
            .join(Account, (Account.id == account_id) & (Account.user_id == owner))
            .where(
                ImportRow.id == row_id,
                ImportRow.batch_id == batch_id,
                ImportRow.user_id == owner,
                ImportRow.kind == "statement",
                ImportSource.batch_id == batch_id,
                ImportSource.kind == "statement",
                ImportSource.current_revision_id == ImportRow.revision_id,
                ImportSource.processing_state == "ready",
                ImportSource.validation_state == "passed",
            )
        )
    ).one_or_none()
    if record is None:
        return None, "current_row_not_found_or_not_current"
    row, source, revision, account = record
    try:
        value = StatementRow.model_validate(row.fields)
    except ValueError:
        return None, "current_row_invalid"
    if (
        source.bank is None
        or value.state != "posted"
        or value.booking_date is None
        or value.fee != 0
        or value.amount >= 0
        or value.currency != account.currency
        or not value.bank_reference
    ):
        return None, "current_row_not_eligible"
    if not _source_binds_account(source, revision.result, account):
        return None, "current_source_account_uncertain"
    already_imported = await db.scalar(
        select(ImportEvidence.id).where(
            ImportEvidence.user_id == owner, ImportEvidence.row_id == row.id
        )
    )
    if already_imported is not None:
        return None, "current_row_already_imported"
    identity = f"{source.bank}:{account.id}:{value.currency}:{value.bank_reference}"
    return (
        VerifiedExpenseObservation(
            owner_id=owner,
            account_id=account_id,
            currency=value.currency,
            source="bank_import",
            strong_identity=identity,
            economic_identity=identity,
            economic_identity_state="canonical",
            occurred_on=value.booking_date,
            description=value.description,
            amount_minor=value.amount,
        ),
        None,
    )


async def propose_recurring_expense(
    db: AsyncSession,
    owner: uuid.UUID,
    batch_id: uuid.UUID,
    row_id: uuid.UUID,
    account_id: uuid.UUID,
) -> RecurringProposalResponse:
    """Return a bounded, fail-closed read of a possible *new* schedule."""
    current, current_reason = await _current_observation(db, owner, batch_id, row_id, account_id)
    if current is None:
        return proposal_response(_uncertain(current_reason or "current_row_uncertain"))

    # A current source's external reference may be duplicated by overlapping
    # statements. A distinct staging-row UUID is not proof of another payment.
    reference = current.strong_identity.split(":", 3)[3]
    overlapping = await db.scalar(
        select(ImportRow.id)
        .join(ImportSource, ImportSource.id == ImportRow.source_id)
        .where(
            ImportRow.user_id == owner,
            ImportRow.kind == "statement",
            ImportRow.id != row_id,
            ImportSource.user_id == owner,
            ImportSource.bank == current.strong_identity.split(":", 1)[0],
            ImportSource.current_revision_id == ImportRow.revision_id,
            ImportRow.fields["bank_reference"].as_string() == reference,
        )
        .limit(1)
    )
    if overlapping is not None:
        return proposal_response(_uncertain("statement_overlap_uncertain", current))

    # A schedule name has no immutable source identity.  Keep its label for
    # review, but never use a different label as proof that there is no duplicate.
    active_schedule_names = (
        (
            await db.execute(
                select(ScheduledFinanceItem.name).where(
                    ScheduledFinanceItem.user_id == owner,
                    ScheduledFinanceItem.account_id == account_id,
                    ScheduledFinanceItem.currency == current.currency,
                    ScheduledFinanceItem.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    merchant = _merchant_key(current.description)
    # PostgreSQL's normalize/lower expression below is only relied on for an
    # ASCII canonical key. For any other key we cannot prove parity with Python
    # Unicode casing, so do not risk hiding historical occurrences.
    if not merchant or not merchant.isascii():
        return proposal_response(_uncertain("merchant_normalization_uncertain", current))

    history_start = _history_start(current.occurred_on)
    history_end = _history_end(current.occurred_on)
    normalized_description = _normalized_description_expression()
    verified_rows = (
        await db.execute(
            select(
                ImportEvidence,
                ImportRow,
                ImportSource,
                ImportBankIdentity,
            )
            .join(FinancialTransaction, FinancialTransaction.id == ImportEvidence.transaction_id)
            .join(Posting, Posting.id == ImportEvidence.posting_id)
            .join(ImportRow, ImportRow.id == ImportEvidence.row_id)
            .join(ImportSource, ImportSource.id == ImportRow.source_id)
            .join(
                ImportBankIdentity,
                (ImportBankIdentity.group_id == ImportEvidence.group_id)
                & (ImportBankIdentity.user_id == owner)
                & (ImportBankIdentity.account_id == account_id),
            )
            .where(
                ImportEvidence.user_id == owner,
                FinancialTransaction.user_id == owner,
                FinancialTransaction.type == "expense",
                FinancialTransaction.is_pending.is_(False),
                Posting.account_id == account_id,
                ImportRow.kind == "statement",
                ImportSource.kind == "statement",
                ImportSource.current_revision_id == ImportRow.revision_id,
                ImportSource.processing_state == "ready",
                ImportSource.validation_state == "passed",
                normalized_description == merchant,
                ImportRow.fields["booking_date"].as_string() >= history_start.isoformat(),
                ImportRow.fields["booking_date"].as_string() <= history_end.isoformat(),
            )
            .order_by(ImportRow.fields["booking_date"].as_string().desc(), FinancialTransaction.id)
            .limit(MAX_CANDIDATE_HISTORY_OBSERVATIONS + 1)
        )
    ).all()
    if len(verified_rows) > MAX_CANDIDATE_HISTORY_OBSERVATIONS:
        return proposal_response(_uncertain("candidate_history_limit_reached", current))

    historical: list[VerifiedExpenseObservation] = []
    for evidence, row, source, identity in verified_rows:
        try:
            value = StatementRow.model_validate(row.fields)
        except ValueError:
            return proposal_response(_uncertain("historical_source_invalid", current))
        if (
            source.bank != identity.bank
            or value.state != "posted"
            or value.booking_date is None
            or value.fee != 0
            or value.amount >= 0
            or value.currency != current.currency
            or evidence.component not in {"whole", "main"}
            or not _historical_reference_matches_identity(value, identity.strong_reference)
        ):
            return proposal_response(_uncertain("historical_identity_uncertain", current))
        if _merchant_key(value.description) != merchant:
            return proposal_response(
                _uncertain("historical_merchant_normalization_uncertain", current)
            )
        external_identity = (
            f"{identity.bank}:{account_id}:{value.currency}:{identity.strong_reference}"
        )
        historical.append(
            VerifiedExpenseObservation(
                owner_id=owner,
                account_id=account_id,
                currency=value.currency,
                source="bank_import",
                strong_identity=external_identity,
                economic_identity=external_identity,
                economic_identity_state="canonical",
                occurred_on=value.booking_date,
                description=value.description,
                amount_minor=value.amount,
            )
        )

    analysis = analyze_new_recurring_schedule(current, historical)
    if active_schedule_names:
        reason = (
            "existing_schedule_same_merchant"
            if current.description in active_schedule_names
            else "existing_schedule_identity_uncertain"
        )
        return proposal_response(
            RecurrenceAnalysis(status="uncertain", reason=reason, evidence=analysis.evidence)
        )
    return proposal_response(analysis)
