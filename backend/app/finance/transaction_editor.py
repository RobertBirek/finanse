"""Conservative in-place transaction editing.

This is intentionally narrower than transaction creation: a stored row does
not retain enough provenance to safely replay every specialised creation
command.  The editor therefore changes only an unlinked, canonical manual
ledger layout and leaves every protected/historical layout intact.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.finance.annotations import update_annotations
from app.finance.document_guards import lock_document_mutations
from app.finance.ledger_validation import _validate_posting_sum, _validate_transaction_postings
from app.finance.models import (
    ActualImportMapping,
    DocumentPaymentAllocation,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
    TransactionCategorizationState,
)
from app.finance.schemas import TransactionCreate, TransactionEditorUpdate


class TransactionEditorError(ValueError):
    """A conflict that requires the editor to refresh or use a dedicated flow."""


@dataclass(frozen=True)
class LedgerEditability:
    editable: bool
    reason: str | None = None


async def _exists(db: AsyncSession, statement: Select[tuple[uuid.UUID]]) -> bool:
    return await db.scalar(statement) is not None


async def ledger_editability(
    db: AsyncSession, owner: uuid.UUID, txn: FinancialTransaction
) -> LedgerEditability:
    """Return a reason instead of guessing how linked history should be changed."""
    from app.finance.credit_card_models import CardAllocation, CardCharge, CardPlan
    from app.finance.imports.models import ImportEvidence
    from app.finance.opening_balance_models import AccountOpeningBalance
    from app.finance.person_models import PersonTransactionLink
    from app.finance.rule_event_models import TransactionRuleEvent
    from app.finance.rule_models import TransactionCategorizationOrigin
    from app.finance.suggestion_models import CategorizationSuggestionJob

    if await _exists(
        db,
        select(AccountOpeningBalance.id).where(
            AccountOpeningBalance.user_id == owner, AccountOpeningBalance.transaction_id == txn.id
        ),
    ):
        return LedgerEditability(False, "Bilans otwarcia jest chroniony.")
    if txn.source != "manual" or txn.created_by != "human":
        return LedgerEditability(False, "Pochodzenie transakcji jest chronione.")
    if txn.date_metadata is not None:
        return LedgerEditability(False, "Transakcja ma chronione znaczenie dat.")
    if len(txn.postings) != 2:
        return LedgerEditability(
            False, "Podział lub niestandardowy układ zapisów wymaga osobnej korekty."
        )
    if any(
        (posting.account_id is None) == (posting.category_id is None) for posting in txn.postings
    ):
        return LedgerEditability(False, "Niestandardowy układ zapisów jest chroniony.")
    if await _exists(
        db,
        select(ActualImportMapping.id).where(
            ActualImportMapping.user_id == owner,
            ActualImportMapping.entity_type == "transaction",
            ActualImportMapping.entity_id == txn.id,
        ),
    ) or await _exists(
        db,
        select(ImportEvidence.id).where(
            ImportEvidence.user_id == owner, ImportEvidence.transaction_id == txn.id
        ),
    ):
        return LedgerEditability(False, "Dowód importu chroni tożsamość księgową.")
    if await _exists(
        db,
        select(DocumentPaymentAllocation.id)
        .join(Posting, Posting.id == DocumentPaymentAllocation.posting_id)
        .where(Posting.transaction_id == txn.id, DocumentPaymentAllocation.user_id == owner),
    ):
        return LedgerEditability(False, "Płatność jest powiązana z dokumentem.")
    if await _exists(
        db,
        select(LoanPaymentLink.id).where(
            LoanPaymentLink.user_id == owner, LoanPaymentLink.transaction_id == txn.id
        ),
    ):
        return LedgerEditability(False, "Płatność pożyczki jest powiązana z harmonogramem.")
    if await _exists(
        db,
        select(PersonTransactionLink.id).where(
            PersonTransactionLink.user_id == owner, PersonTransactionLink.transaction_id == txn.id
        ),
    ):
        return LedgerEditability(False, "Darowizna jest powiązana z osobą.")
    if (
        await _exists(
            db,
            select(CardPlan.id).where(
                CardPlan.user_id == owner, CardPlan.source_transaction_id == txn.id
            ),
        )
        or await _exists(
            db,
            select(CardAllocation.id).where(
                CardAllocation.user_id == owner, CardAllocation.transaction_id == txn.id
            ),
        )
        or await _exists(
            db,
            select(CardCharge.id).where(
                CardCharge.user_id == owner, CardCharge.transaction_id == txn.id
            ),
        )
    ):
        return LedgerEditability(False, "Transakcja jest powiązana z kartą.")
    if await _exists(
        db,
        select(TransactionCategorizationOrigin.id).where(
            TransactionCategorizationOrigin.user_id == owner,
            TransactionCategorizationOrigin.transaction_id == txn.id,
        ),
    ) or await _exists(
        db,
        select(TransactionCategorizationState.id).where(
            TransactionCategorizationState.user_id == owner,
            TransactionCategorizationState.transaction_id == txn.id,
        ),
    ):
        return LedgerEditability(
            False, "Zachowano historię kategoryzacji; użyj jej dedykowanej korekty."
        )
    if await _exists(
        db,
        select(TransactionRuleEvent.id).where(
            TransactionRuleEvent.user_id == owner, TransactionRuleEvent.transaction_id == txn.id
        ),
    ) or await _exists(
        db,
        select(CategorizationSuggestionJob.id).where(
            CategorizationSuggestionJob.user_id == owner,
            CategorizationSuggestionJob.transaction_id == txn.id,
        ),
    ):
        return LedgerEditability(False, "Transakcja ma historię reguły lub sugestii.")
    return LedgerEditability(True)


async def _locked_transaction(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID
) -> FinancialTransaction | None:
    return await db.scalar(
        select(FinancialTransaction)
        .options(
            selectinload(FinancialTransaction.postings),
            selectinload(FinancialTransaction.date_metadata),
        )
        .where(FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _replace_canonical_ledger(
    db: AsyncSession, owner: uuid.UUID, txn: FinancialTransaction, data: TransactionCreate
) -> None:
    if data.source != "manual":
        raise TransactionEditorError("Edycja nie może zmienić pochodzenia transakcji.")
    if data.purchase_date is not None or data.booking_date is not None:
        raise TransactionEditorError("Edycja dat wymaga dedykowanej korekty dat.")
    if "project_id" in data.model_fields_set and data.project_id != txn.project_id:
        raise TransactionEditorError("Projekt należy zmienić przez oznaczenia transakcji.")
    _validate_posting_sum(data.postings, data.type)
    await _validate_transaction_postings(db, owner, data.postings, data.type)
    postings = sorted(txn.postings, key=lambda posting: str(posting.id))
    for posting, replacement in zip(postings, data.postings, strict=True):
        posting.account_id = replacement.account_id
        posting.category_id = replacement.category_id
        posting.source_amount = replacement.source_amount
        posting.source_currency = replacement.source_currency.upper()
        posting.base_amount_pln = replacement.base_amount_pln
        posting.fx_rate = replacement.fx_rate
        posting.fx_rate_source = replacement.fx_rate_source
        posting.direction = replacement.direction
        posting.is_budget_impact = replacement.is_budget_impact
    txn.date = data.transaction_date or txn.date
    txn.description = data.description
    txn.type = data.type
    txn.is_pending = data.is_pending
    await db.flush()


async def _guard_ledger_replacement(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID
) -> None:
    """Keep dedicated mutation guards authoritative if linked rows appear mid-edit."""
    from app.finance.credit_cards import guard_transaction
    from app.finance.document_guards import guard_allocated_transaction_change
    from app.finance.opening_balance_guards import guard_opening_balance_transaction
    from app.finance.person_guards import guard_person_gift_change

    try:
        await guard_opening_balance_transaction(db, owner, transaction_id)
        await guard_person_gift_change(db, owner, transaction_id, {"ledger"})
        await guard_allocated_transaction_change(db, owner, transaction_id, {"ledger": True})
        await guard_transaction(db, owner, transaction_id)
    except ValueError as error:
        raise TransactionEditorError(str(error)) from error


async def update_editor(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    data: TransactionEditorUpdate,
    *,
    annotation_idempotency_key: str | None,
) -> tuple[FinancialTransaction | None, LedgerEditability]:
    """Apply annotation then ledger changes in the caller's one database transaction."""
    await lock_document_mutations(db, owner)
    txn = await _locked_transaction(db, owner, transaction_id)
    if txn is None:
        return None, LedgerEditability(False)
    if txn.updated_at != data.expected_updated_at:
        raise TransactionEditorError("Transakcja zmieniła się. Odśwież dane przed zapisem.")
    editability = await ledger_editability(db, owner, txn)
    if data.ledger is not None:
        if not editability.editable:
            raise TransactionEditorError(editability.reason or "Edycja księgi jest zablokowana.")
        if data.ledger.kind != "transaction":
            raise TransactionEditorError(
                "Nie można bezpiecznie odtworzyć specjalnego polecenia z zapisanej transakcji."
            )
        await _guard_ledger_replacement(db, owner, transaction_id)
    if data.annotations is not None:
        if annotation_idempotency_key is None:
            raise TransactionEditorError("Nagłówek Idempotency-Key jest wymagany dla oznaczeń.")
        await update_annotations(
            db,
            owner,
            transaction_id,
            data.annotations,
            idempotency_key=annotation_idempotency_key,
        )
    if data.ledger is not None:
        assert isinstance(data.ledger.data, TransactionCreate)
        await _replace_canonical_ledger(db, owner, txn, data.ledger.data)
    await db.refresh(txn, attribute_names=["updated_at", "postings", "date_metadata"])
    return txn, await ledger_editability(db, owner, txn)
