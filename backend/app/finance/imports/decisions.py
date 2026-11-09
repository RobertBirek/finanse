"""Owner-scoped review decisions. Validation and grouping have no ledger side effects."""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.card_statements import validate_card_header
from app.finance.imports.contracts import ParsedStatement, StatementRow
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBatch,
    ImportDecision,
    ImportEvidence,
    ImportGroup,
    ImportGroupRow,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.queries import get_batch
from app.finance.imports.schemas import BatchDTO, DecisionUpdate, ImportDecisionInput
from app.finance.models import Account, Category, FinancialTransaction, Posting


@dataclass
class ReviewedRow:
    row: ImportRow
    source: ImportSource
    revision: ImportRevision
    value: StatementRow
    account: Account | None


def normalized_reference(value: str) -> str:
    text = re.sub(r"\s", "", value).upper()
    return text.removeprefix("PL")


async def load_batch(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, *, locked: bool = False
) -> ImportBatch:
    statement = select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == owner)
    if locked:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    batch = await db.scalar(statement)
    if batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    if batch.archived_at is not None:
        raise ImportError("import_archived", "Import jest zarchiwizowany.")
    if batch.kind != "statement":
        raise ImportError("import_kind_mismatch", "To nie jest import wyciągu.", 422)
    return batch


async def _account(
    db: AsyncSession, owner: uuid.UUID, account_id: uuid.UUID | None, *, creating: bool
) -> Account:
    account = await db.scalar(
        select(Account).where(Account.id == account_id, Account.user_id == owner)
    )
    if account is None:
        raise ImportError("account_not_found", "Nie znaleziono rachunku.", 404)
    if creating and not account.is_active:
        raise ImportError("account_inactive", "Rachunek jest nieaktywny.")
    return account


async def _category(
    db: AsyncSession, owner: uuid.UUID, category_id: uuid.UUID | None, kind: str
) -> None:
    category = await db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == owner)
    )
    if category is None:
        raise ImportError("category_not_found", "Nie znaleziono kategorii.", 404)
    if not category.is_active or category.type != kind:
        raise ImportError(
            "category_type_mismatch", "Kategoria nie pasuje do rodzaju operacji.", 422
        )


def signed_posting(posting: Posting) -> int:
    return -posting.source_amount if posting.direction == "debit" else posting.source_amount


async def validate_link(
    db: AsyncSession, owner: uuid.UUID, decision: ImportDecisionInput, rows: list[ReviewedRow]
) -> list[Posting]:
    transaction = await db.scalar(
        select(FinancialTransaction).where(
            FinancialTransaction.id == decision.existing_transaction_id,
            FinancialTransaction.user_id == owner,
        )
    )
    if transaction is None:
        raise ImportError("transaction_not_found", "Nie znaleziono operacji.", 404)
    if transaction.is_pending:
        raise ImportError(
            "link_pending_transaction", "Nie można powiązać niezaksięgowanej operacji."
        )
    expected_type = "expense" if decision.kind == "expense_refund" else decision.kind
    if transaction.type != expected_type:
        raise ImportError(
            "link_kind_mismatch", "Rodzaj istniejącej operacji nie pasuje do decyzji."
        )
    postings = list(
        (await db.scalars(select(Posting).where(Posting.transaction_id == transaction.id))).all()
    )
    selected = []
    for row in rows:
        assert row.account is not None
        matches = [
            posting
            for posting in postings
            if posting.account_id == row.account.id
            and posting.source_currency == row.value.currency
            and signed_posting(posting) == row.value.amount
        ]
        if len(matches) != 1:
            raise ImportError(
                "link_posting_mismatch",
                "Konto, waluta, kierunek lub rzeczywista kwota nie pasują do istniejącego zapisu.",
            )
        if (
            transaction.date != row.value.booking_date
            and "link_date_difference" not in decision.acknowledgements
        ):
            raise ImportError(
                "link_date_confirmation_required", "Potwierdź różnicę dat księgowania obu źródeł."
            )
        selected.append(matches[0])
    return selected


async def validate_decision(
    db: AsyncSession, owner: uuid.UUID, batch: ImportBatch, decision: ImportDecisionInput
) -> list[ReviewedRow]:
    records = (
        await db.execute(
            select(ImportRow, ImportSource, ImportRevision)
            .join(
                ImportSource,
                (ImportSource.id == ImportRow.source_id) & (ImportSource.user_id == owner),
            )
            .join(
                ImportRevision,
                (ImportRevision.id == ImportRow.revision_id) & (ImportRevision.user_id == owner),
            )
            .where(
                ImportRow.id.in_(decision.row_ids),
                ImportRow.user_id == owner,
                ImportRow.batch_id == batch.id,
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    if len(records) != len(decision.row_ids):
        raise ImportError("row_not_found", "Nie znaleziono wszystkich wybranych wierszy.", 404)
    ordered = {row.id: (row, source, revision) for row, source, revision in records}
    rows = [
        ReviewedRow(*ordered[row_id], StatementRow.model_validate(ordered[row_id][0].fields), None)
        for row_id in decision.row_ids
    ]
    if any(row.source.current_revision_id != row.revision.id for row in rows):
        raise ImportError("source_revision_conflict", "Wiersz należy do innego odczytu źródła.")
    consumed = await db.scalar(
        select(ImportEvidence.id).where(ImportEvidence.row_id.in_(decision.row_ids)).limit(1)
    )
    if consumed is not None:
        raise ImportError("row_already_committed", "Wiersz ma już dowód księgowania.")
    if decision.action == "defer":
        return rows
    candidates: dict[uuid.UUID, ImportRevision | None] = {}
    for row in rows:
        if row.source.id not in candidates:
            candidates[row.source.id] = await db.scalar(
                select(ImportRevision)
                .where(
                    ImportRevision.source_id == row.source.id,
                    ImportRevision.user_id == owner,
                )
                .order_by(ImportRevision.number.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
        candidate = candidates[row.source.id]
        if (
            candidate is not None
            and candidate.id != row.revision.id
            and "reparse_requires_comparison" in candidate.warnings
        ):
            token = f"reparse_comparison:{row.source.id}:{candidate.id}"
            if token not in decision.acknowledgements:
                raise ImportError(
                    "reparse_comparison_required",
                    "Porównaj ponowny odczyt z zachowaną wersją: " + token,
                )
            parsed_candidate = ParsedStatement.model_validate(candidate.result)
            matches = [value for value in parsed_candidate.rows if value.key == row.value.key]
            if (
                candidate.source_sha256 != row.revision.source_sha256
                or len(matches) != 1
                or matches[0] != row.value
            ):
                raise ImportError(
                    "reparse_row_conflict",
                    "Nowy odczyt różni się od zachowanego wiersza; nie można go zatwierdzić przez pominięcie różnicy.",
                )
            if any(
                check.required and check.result != "passed" for check in parsed_candidate.checks
            ):
                raise ImportError(
                    "source_validation_blocked", "Kontrole ponownego odczytu blokują import."
                )
    if any(row.value.state != "posted" or row.value.amount == row.value.fee == 0 for row in rows):
        raise ImportError(
            "row_not_postable",
            "Nieksięgowane lub informacyjne wiersze pozostają bez transakcji.",
            422,
        )
    if any(
        row.source.processing_state != "ready"
        or row.source.validation_state == "blocked"
        or any(
            check.get("required") is True and check.get("result") != "passed"
            for check in row.revision.checks
        )
        for row in rows
    ):
        raise ImportError("source_validation_blocked", "Kontrole źródła blokują import.")
    internal = decision.kind in {"transfer", "exchange"}
    if not internal and len(rows) != 1:
        raise ImportError(
            "group_shape_invalid", "Płatność zewnętrzna wymaga jednego wiersza źródłowego.", 422
        )
    if internal and len(rows) not in {1, 2}:
        raise ImportError(
            "group_shape_invalid", "Wybierz kompletny transfer lub parę wymiany.", 422
        )
    if decision.kind == "exchange" and len(rows) != 2:
        raise ImportError(
            "exchange_leg_missing", "Wymiana wymaga obu rzeczywistych nóg bankowych.", 422
        )
    primary = await _account(db, owner, decision.account_id, creating=decision.action == "create")
    other = (
        await _account(db, owner, decision.other_account_id, creating=decision.action == "create")
        if decision.other_account_id
        else None
    )
    if internal and decision.action == "create" and other is None:
        raise ImportError("transfer_account_missing", "Wybierz drugi własny rachunek.", 422)
    for row in rows:
        main = row.value.amount + row.value.fee
        account = other if internal and len(rows) == 2 and main > 0 else primary
        if account is None or account.currency != row.value.currency:
            raise ImportError(
                "account_currency_mismatch", "Waluta źródła nie pasuje do wybranego rachunku.", 422
            )
        reference = row.source.account_reference or (row.revision.result or {}).get(
            "account_reference"
        )
        if (
            isinstance(reference, str)
            and account.iban
            and normalized_reference(reference) != normalized_reference(account.iban)
        ):
            raise ImportError(
                "account_reference_mismatch", "Rachunek źródła nie pasuje do wybranego konta."
            )
        bank = re.sub(r"[^a-z]", "", (account.bank_name or "").lower())
        if bank and row.source.bank and row.source.bank not in bank:
            raise ImportError("account_bank_mismatch", "Bank źródła nie pasuje do wybranego konta.")
        row.account = account
        if row.value.fee < 0 and decision.kind != "expense_refund":
            raise ImportError(
                "fee_refund_classification_required",
                "Zwrot prowizji wymaga jawnej klasyfikacji zwrotu wydatku.",
                422,
            )
        if decision.action == "create":
            if (
                decision.kind == "expense"
                and main >= 0
                and not (main == 0 and row.value.fee > 0)
                or decision.kind == "income"
                and main <= 0
                or decision.kind == "expense_refund"
                and main <= 0
                and not (main == 0 and row.value.fee < 0)
            ):
                raise ImportError(
                    "movement_direction_mismatch",
                    "Znak bankowej kwoty nie pasuje do klasyfikacji.",
                    422,
                )
            if row.value.fee:
                await _category(db, owner, decision.fee_category_id, "expense")
            kind_text = " ".join(
                str(row.value.raw.get(key, "")) for key in ["Rodzaj", "type"]
            ).lower()
            if any(word in kind_text for word in ["wypłata", "cash withdrawal", "atm"]) and (
                decision.kind != "transfer" or other is None or other.type != "cash"
            ):
                raise ImportError(
                    "cash_account_required",
                    "Wypłata gotówki wymaga wskazania własnego konta gotówki.",
                    422,
                )
    if internal and len(rows) == 2:
        mains = [row.value.amount + row.value.fee for row in rows]
        if not (sum(amount < 0 for amount in mains) == sum(amount > 0 for amount in mains) == 1):
            raise ImportError(
                "transfer_legs_invalid", "Para musi obejmować rzeczywisty wypływ i wpływ.", 422
            )
        if len({row.account.id for row in rows if row.account}) != 2:
            raise ImportError(
                "transfer_accounts_invalid", "Nogi muszą należeć do dwóch różnych rachunków.", 422
            )
    if internal and other is not None:
        if decision.kind == "transfer" and (
            primary.currency != other.currency
            or len(rows) == 2
            and sum(row.value.amount + row.value.fee for row in rows) != 0
        ):
            raise ImportError(
                "transfer_amount_mismatch",
                "Transfer tej samej waluty musi zachować obie kwoty.",
                422,
            )
        if decision.kind == "exchange" and primary.currency == other.currency:
            raise ImportError("exchange_currencies_invalid", "Wymiana wymaga różnych walut.", 422)
    if decision.action == "link":
        await validate_link(db, owner, decision, rows)
    elif not internal:
        await _category(
            db, owner, decision.category_id, "income" if decision.kind == "income" else "expense"
        )
    if decision.card_header is not None:
        if primary.type != "credit_card" or decision.card_header.account_id != primary.id:
            raise ImportError(
                "card_account_mismatch", "Potwierdzenie wyciągu dotyczy innego konta karty.", 422
            )
        validate_card_header(
            ParsedStatement.model_validate(rows[0].revision.result), decision.card_header
        )
    return rows


async def save_decisions(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: DecisionUpdate
) -> BatchDTO:
    await lock_document_mutations(db, owner)
    batch = await load_batch(db, owner, batch_id, locked=True)
    if batch.version != data.expected_version:
        raise ImportError("import_version_conflict", "Import zmienił się; odśwież podgląd.")
    # Validate the entire update before touching any group/membership.
    for decision in data.decisions:
        await validate_decision(db, owner, batch, decision)
        group = await db.get(ImportGroup, decision.group_id)
        if group is not None and (group.user_id != owner or group.batch_id != batch_id):
            raise ImportError("group_not_found", "Nie znaleziono grupy.", 404)
        if group is not None and group.state == "committed":
            raise ImportError("group_already_committed", "Zatwierdzonej grupy nie można zmienić.")
        memberships = (
            await db.scalars(
                select(ImportGroupRow).where(ImportGroupRow.row_id.in_(decision.row_ids))
            )
        ).all()
        selected_ids = {item.group_id for item in data.decisions}
        if any(member.group_id not in selected_ids for member in memberships):
            raise ImportError(
                "row_group_conflict", "Wiersz należy do innej grupy; zmień obie decyzje jawnie."
            )
    group_ids = [item.group_id for item in data.decisions]
    await db.execute(
        delete(ImportGroupRow).where(
            ImportGroupRow.user_id == owner,
            ImportGroupRow.batch_id == batch_id,
            ImportGroupRow.group_id.in_(group_ids),
        )
    )
    for decision in data.decisions:
        group = await db.get(ImportGroup, decision.group_id)
        if group is None:
            group = ImportGroup(id=decision.group_id, user_id=owner, batch_id=batch_id, version=1)
            db.add(group)
            await db.flush([group])
        else:
            group.version += 1
        group.state = "deferred" if decision.action == "defer" else "ready"
        db.add(
            ImportDecision(
                user_id=owner,
                batch_id=batch_id,
                group_id=group.id,
                version=group.version,
                data=decision.model_dump(mode="json"),
            )
        )
        for row_id in decision.row_ids:
            db.add(
                ImportGroupRow(user_id=owner, batch_id=batch_id, group_id=group.id, row_id=row_id)
            )
    batch.version += 1
    await log_event(
        db,
        owner,
        "bank_import_batch",
        str(batch_id),
        "save_decisions",
        new_state={"version": batch.version, "group_ids": [str(item) for item in group_ids]},
    )
    await db.flush()
    result = await get_batch(db, owner, batch_id)
    if result is None:
        raise RuntimeError("Reviewed import disappeared")
    return result
