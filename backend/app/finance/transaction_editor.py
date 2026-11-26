"""Conservative in-place transaction editing.

This is intentionally narrower than transaction creation: a stored row does
not retain enough provenance to safely replay every specialised creation
command.  The editor therefore changes only an unlinked, canonical manual
ledger layout and leaves every protected/historical layout intact.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.finance.annotations import update_annotations
from app.finance.document_guards import lock_document_mutations
from app.finance.ledger_validation import (
    _validate_posting_sum,
    _validate_transaction_postings,
)
from app.finance.models import (
    ActualImportMapping,
    DocumentPaymentAllocation,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
    TransactionCategorizationState,
)
from app.finance.schemas import (
    ManualFxTransactionCreate,
    TransactionCreate,
    TransactionEditorUpdate,
)
from app.finance.transaction_dates import TransactionDateError, set_editor_manual_dates


class TransactionEditorError(ValueError):
    """A conflict that requires the editor to refresh or use a dedicated flow."""


@dataclass(frozen=True)
class LedgerEditability:
    editable: bool
    reason: str | None = None


def _is_canonical_manual_fx(txn: FinancialTransaction) -> bool:
    """Recognise only the exact persisted shape produced by the manual-rate builder."""
    if txn.source != "manual" or txn.type not in {"expense", "income"} or len(txn.postings) != 2:
        return False
    accounts = [
        posting for posting in txn.postings if posting.account_id and not posting.category_id
    ]
    categories = [
        posting for posting in txn.postings if posting.category_id and not posting.account_id
    ]
    if len(accounts) != 1 or len(categories) != 1:
        return False
    account, category = accounts[0], categories[0]
    currency = str(account.source_currency).upper()
    expected_direction = "debit" if txn.type == "expense" else "credit"
    return bool(
        currency in {"EUR", "USD"}
        and str(category.source_currency).upper() == currency
        and account.source_amount == category.source_amount
        and account.base_amount_pln == category.base_amount_pln
        and Decimal(str(account.fx_rate)) == Decimal(str(category.fx_rate))
        and account.fx_rate_source == category.fx_rate_source == "manual"
        and account.direction == expected_direction
        and category.direction != expected_direction
    )


async def ledger_editabilities(
    db: AsyncSession, owner: uuid.UUID, transactions: list[FinancialTransaction]
) -> dict[uuid.UUID, LedgerEditability]:
    """Return editor decisions for a page of history in a bounded number of queries."""
    from app.finance.credit_card_models import CardAllocation, CardCharge, CardPlan
    from app.finance.imports.models import ImportEvidence
    from app.finance.opening_balance_models import AccountOpeningBalance
    from app.finance.person_models import PersonTransactionLink
    from app.finance.rule_event_models import TransactionRuleEvent
    from app.finance.rule_models import TransactionCategorizationOrigin
    from app.finance.suggestion_models import CategorizationSuggestionJob

    transaction_ids = [transaction.id for transaction in transactions]
    if not transaction_ids:
        return {}

    async def linked_ids(
        statement: Select[tuple[uuid.UUID]] | Select[tuple[uuid.UUID | None]],
    ) -> set[uuid.UUID]:
        return {
            transaction_id
            for transaction_id in (await db.scalars(statement)).all()
            if transaction_id is not None
        }

    opening_ids = await linked_ids(
        select(AccountOpeningBalance.transaction_id).where(
            AccountOpeningBalance.user_id == owner,
            AccountOpeningBalance.transaction_id.in_(transaction_ids),
        )
    )
    actual_import_ids = await linked_ids(
        select(ActualImportMapping.entity_id).where(
            ActualImportMapping.user_id == owner,
            ActualImportMapping.entity_type == "transaction",
            ActualImportMapping.entity_id.in_(transaction_ids),
        )
    )
    bank_import_ids = await linked_ids(
        select(ImportEvidence.transaction_id).where(
            ImportEvidence.user_id == owner,
            ImportEvidence.transaction_id.in_(transaction_ids),
        )
    )
    document_ids = await linked_ids(
        select(Posting.transaction_id)
        .join(
            DocumentPaymentAllocation,
            DocumentPaymentAllocation.posting_id == Posting.id,
        )
        .where(
            Posting.transaction_id.in_(transaction_ids),
            DocumentPaymentAllocation.user_id == owner,
        )
    )
    loan_ids = await linked_ids(
        select(LoanPaymentLink.transaction_id).where(
            LoanPaymentLink.user_id == owner,
            LoanPaymentLink.transaction_id.in_(transaction_ids),
        )
    )
    from app.finance.allegro_pay_models import AllegroPayAllocation, AllegroPayPurchase

    allegro_ids = await linked_ids(
        select(AllegroPayPurchase.transaction_id).where(
            AllegroPayPurchase.user_id == owner,
            AllegroPayPurchase.transaction_id.in_(transaction_ids),
        )
    )
    allegro_ids.update(
        await linked_ids(
            select(AllegroPayAllocation.transaction_id).where(
                AllegroPayAllocation.user_id == owner,
                AllegroPayAllocation.transaction_id.in_(transaction_ids),
            )
        )
    )
    person_ids = await linked_ids(
        select(PersonTransactionLink.transaction_id).where(
            PersonTransactionLink.user_id == owner,
            PersonTransactionLink.transaction_id.in_(transaction_ids),
        )
    )
    card_ids = await linked_ids(
        select(CardPlan.source_transaction_id).where(
            CardPlan.user_id == owner,
            CardPlan.source_transaction_id.in_(transaction_ids),
        )
    )
    card_ids.update(
        await linked_ids(
            select(CardAllocation.transaction_id).where(
                CardAllocation.user_id == owner,
                CardAllocation.transaction_id.in_(transaction_ids),
            )
        )
    )
    card_ids.update(
        await linked_ids(
            select(CardCharge.transaction_id).where(
                CardCharge.user_id == owner,
                CardCharge.transaction_id.in_(transaction_ids),
            )
        )
    )
    categorization_ids = await linked_ids(
        select(TransactionCategorizationOrigin.transaction_id).where(
            TransactionCategorizationOrigin.user_id == owner,
            TransactionCategorizationOrigin.transaction_id.in_(transaction_ids),
        )
    )
    categorization_ids.update(
        await linked_ids(
            select(TransactionCategorizationState.transaction_id).where(
                TransactionCategorizationState.user_id == owner,
                TransactionCategorizationState.transaction_id.in_(transaction_ids),
            )
        )
    )
    rule_or_suggestion_ids = await linked_ids(
        select(TransactionRuleEvent.transaction_id).where(
            TransactionRuleEvent.user_id == owner,
            TransactionRuleEvent.transaction_id.in_(transaction_ids),
        )
    )
    rule_or_suggestion_ids.update(
        await linked_ids(
            select(CategorizationSuggestionJob.transaction_id).where(
                CategorizationSuggestionJob.user_id == owner,
                CategorizationSuggestionJob.transaction_id.in_(transaction_ids),
            )
        )
    )

    decisions: dict[uuid.UUID, LedgerEditability] = {}
    for txn in transactions:
        if txn.id in opening_ids:
            decisions[txn.id] = LedgerEditability(False, "Bilans otwarcia jest chroniony.")
            continue
        if txn.source == "bank_import":
            decisions[txn.id] = LedgerEditability(False, "Import bankowy")
            continue
        if txn.source != "manual" or txn.created_by != "human":
            decisions[txn.id] = LedgerEditability(False, "Pochodzenie transakcji jest chronione.")
            continue
        if txn.date_metadata is not None and (
            txn.type != "expense"
            or txn.date_metadata.purchase_date_source not in {None, "manual"}
            or txn.date_metadata.booking_date_source != "manual"
        ):
            decisions[txn.id] = LedgerEditability(False, "Transakcja ma chronione znaczenie dat.")
            continue
        if len(txn.postings) != 2:
            decisions[txn.id] = LedgerEditability(
                False,
                "Podział lub niestandardowy układ zapisów wymaga osobnej korekty.",
            )
            continue
        if any(
            (posting.account_id is None) == (posting.category_id is None)
            for posting in txn.postings
        ):
            decisions[txn.id] = LedgerEditability(
                False, "Niestandardowy układ zapisów jest chroniony."
            )
            continue
        if txn.type not in {"income", "expense", "transfer"}:
            decisions[txn.id] = LedgerEditability(
                False, "Ten typ transakcji wymaga osobnej korekty."
            )
            continue
        account_legs = [posting for posting in txn.postings if posting.account_id is not None]
        if txn.type == "transfer":
            if (
                len(account_legs) != 2
                or account_legs[0].account_id == account_legs[1].account_id
                or {posting.direction for posting in account_legs} != {"debit", "credit"}
            ):
                decisions[txn.id] = LedgerEditability(
                    False, "Niestandardowy transfer jest chroniony."
                )
                continue
        elif len(account_legs) != 1 or account_legs[0].direction != (
            "debit" if txn.type == "expense" else "credit"
        ):
            decisions[txn.id] = LedgerEditability(
                False, "Niestandardowy zapis lub zwrot jest chroniony."
            )
            continue
        if any(
            posting.source_currency != "PLN" for posting in txn.postings
        ) and not _is_canonical_manual_fx(txn):
            decisions[txn.id] = LedgerEditability(
                False, "Ten zapis walutowy wymaga osobnej korekty."
            )
            continue
        if txn.id in actual_import_ids or txn.id in bank_import_ids:
            decisions[txn.id] = LedgerEditability(False, "Dowód importu chroni tożsamość księgową.")
            continue
        if txn.id in document_ids:
            decisions[txn.id] = LedgerEditability(False, "Płatność jest powiązana z dokumentem.")
            continue
        if txn.id in loan_ids:
            decisions[txn.id] = LedgerEditability(
                False, "Płatność pożyczki jest powiązana z harmonogramem."
            )
            continue
        if txn.id in allegro_ids:
            decisions[txn.id] = LedgerEditability(False, "Transakcja jest powiązana z Allegro Pay.")
            continue
        if txn.id in person_ids:
            decisions[txn.id] = LedgerEditability(False, "Darowizna jest powiązana z osobą.")
            continue
        if txn.id in card_ids:
            decisions[txn.id] = LedgerEditability(False, "Transakcja jest powiązana z kartą.")
            continue
        if txn.id in categorization_ids:
            decisions[txn.id] = LedgerEditability(
                False, "Zachowano historię kategoryzacji; użyj jej dedykowanej korekty."
            )
            continue
        if txn.id in rule_or_suggestion_ids:
            decisions[txn.id] = LedgerEditability(
                False, "Transakcja ma historię reguły lub sugestii."
            )
            continue
        decisions[txn.id] = LedgerEditability(True)
    return decisions


async def ledger_editability(
    db: AsyncSession, owner: uuid.UUID, txn: FinancialTransaction
) -> LedgerEditability:
    """Return the same decision used by the batched history read."""
    return (await ledger_editabilities(db, owner, [txn]))[txn.id]


async def _locked_transaction(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID
) -> FinancialTransaction | None:
    return await db.scalar(
        select(FinancialTransaction)
        .options(
            selectinload(FinancialTransaction.postings),
            selectinload(FinancialTransaction.date_metadata),
        )
        .where(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == owner,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _replace_canonical_ledger(
    db: AsyncSession,
    owner: uuid.UUID,
    txn: FinancialTransaction,
    data: TransactionCreate,
    *,
    allows_explicit_dates: bool,
) -> None:
    if data.source != "manual":
        raise TransactionEditorError("Edycja nie może zmienić pochodzenia transakcji.")
    if not allows_explicit_dates and (
        data.purchase_date is not None or data.booking_date is not None
    ):
        raise TransactionEditorError("Edycja dat wymaga dedykowanej korekty dat.")
    if "project_id" in data.model_fields_set and data.project_id != txn.project_id:
        raise TransactionEditorError("Projekt należy zmienić przez oznaczenia transakcji.")
    if len(data.postings) != 2:
        raise TransactionEditorError("Edycja wymaga dwóch zapisów księgowych.")
    if txn.date_metadata is not None and (
        data.type != "expense" or not allows_explicit_dates or data.is_pending != txn.is_pending
    ):
        raise TransactionEditorError("Nie można zmienić znaczenia istniejących dat.")
    if data.type not in {"expense", "income", "transfer"}:
        raise TransactionEditorError("Ten typ wymaga osobnej korekty.")
    if data.type == "transfer" and (
        any(
            posting.account_id is None
            or posting.category_id is not None
            or posting.source_currency.upper() != "PLN"
            for posting in data.postings
        )
        or data.postings[0].account_id == data.postings[1].account_id
    ):
        raise TransactionEditorError("Transfer wymaga dwóch różnych kont PLN.")
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
    if not allows_explicit_dates:
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
        if data.ledger.kind == "manual_fx" and not _is_canonical_manual_fx(txn):
            raise TransactionEditorError(
                "Zapis nie jest rozpoznawalną ręczną operacją walutową z kursem ręcznym."
            )
        if data.ledger.kind not in {"transaction", "manual_fx"}:
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
        if data.ledger.kind == "manual_fx":
            assert isinstance(data.ledger.data, ManualFxTransactionCreate)
            if data.ledger.data.fx_rate_source != "manual":
                raise TransactionEditorError("Edycja walutowa wymaga jawnego kursu ręcznego.")
            if data.ledger.data.type != txn.type:
                raise TransactionEditorError("Edycja walutowa nie może zmienić typu transakcji.")
            if txn.type == "expense" and txn.date_metadata is None:
                raise TransactionEditorError(
                    "Ręczny wydatek walutowy wymaga zachowanych dat zakupu i księgowania."
                )
            from app.finance.manual_fx import valued_transaction

            replacement = await valued_transaction(data.ledger.data)
        else:
            assert isinstance(data.ledger.data, TransactionCreate)
            replacement = data.ledger.data
            if any(posting.source_currency.upper() != "PLN" for posting in replacement.postings):
                raise TransactionEditorError("Waluty obce wymagają polecenia z jawnym kursem.")
        has_explicit_dates = replacement.booking_date is not None
        if has_explicit_dates:
            assert replacement.booking_date is not None
            if data.expected_date_version is None:
                raise TransactionEditorError(
                    "Wersja dat jest wymagana przy zmianie dat zakupu i księgowania."
                )
            try:
                await set_editor_manual_dates(
                    db,
                    owner,
                    txn,
                    purchase_date=replacement.purchase_date,
                    booking_date=replacement.booking_date,
                    expected_version=data.expected_date_version,
                )
            except TransactionDateError as error:
                raise TransactionEditorError(str(error)) from error
        await _replace_canonical_ledger(
            db, owner, txn, replacement, allows_explicit_dates=has_explicit_dates
        )
    await db.refresh(txn, attribute_names=["updated_at", "postings", "date_metadata"])
    return txn, await ledger_editability(db, owner, txn)
