"""Read-only adapter for conservative recurring-expense proposals from statement rows."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    NewScheduleProposal,
    RecurrenceAnalysis,
    RecurrenceEvidence,
    VerifiedExpenseObservation,
    analyze_new_recurring_schedule,
)
from app.finance.models import Account, FinancialTransaction, Posting, ScheduledFinanceItem

MAX_HISTORY_OBSERVATIONS = 30


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

    schedule_exists = await db.scalar(
        select(ScheduledFinanceItem.id).where(
            ScheduledFinanceItem.user_id == owner,
            ScheduledFinanceItem.account_id == account_id,
            ScheduledFinanceItem.currency == current.currency,
            ScheduledFinanceItem.is_active.is_(True),
        )
    )
    if schedule_exists is not None:
        return proposal_response(_uncertain("existing_schedule_overlap_uncertain", current))

    verified_rows = (
        await db.execute(
            select(
                ImportEvidence,
                FinancialTransaction,
                Posting,
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
            )
            .order_by(FinancialTransaction.date.desc(), FinancialTransaction.id)
            .limit(MAX_HISTORY_OBSERVATIONS + 1)
        )
    ).all()
    if len(verified_rows) > MAX_HISTORY_OBSERVATIONS:
        return proposal_response(_uncertain("history_limit_reached", current))

    historical: list[VerifiedExpenseObservation] = []
    verified_transaction_ids: set[uuid.UUID] = set()
    for evidence, transaction, posting, row, source, identity in verified_rows:
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
        verified_transaction_ids.add(transaction.id)

    all_expenses = (
        (
            await db.execute(
                select(FinancialTransaction.id)
                .join(Posting, Posting.transaction_id == FinancialTransaction.id)
                .where(
                    FinancialTransaction.user_id == owner,
                    FinancialTransaction.type == "expense",
                    FinancialTransaction.is_pending.is_(False),
                    Posting.account_id == account_id,
                )
                .distinct()
                .order_by(FinancialTransaction.id)
                .limit(MAX_HISTORY_OBSERVATIONS + 1)
            )
        )
        .scalars()
        .all()
    )
    if len(all_expenses) > MAX_HISTORY_OBSERVATIONS:
        return proposal_response(_uncertain("history_limit_reached", current))
    if any(transaction_id not in verified_transaction_ids for transaction_id in all_expenses):
        return proposal_response(_uncertain("historical_identity_uncertain", current))

    return proposal_response(analyze_new_recurring_schedule(current, historical))
