"""Evidence attaches source occurrences without editing historical ledger identity."""

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.contracts import StatementRow
from app.finance.imports.decisions import signed_posting
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportBankIdentity,
    ImportEvidence,
    ImportGroup,
    ImportGroupRow,
    ImportRow,
    ImportSource,
)
from app.finance.models import FinanceCommandReceipt, FinancialTransaction, Posting


async def record_import_evidence(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    row_ids: list[uuid.UUID],
    transaction_id: uuid.UUID,
    posting_id: uuid.UUID,
    receipt_id: uuid.UUID,
    component: Literal["main", "fee", "whole"],
    attributed_source_amount: int,
) -> None:
    posting = await db.scalar(
        select(Posting)
        .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
        .where(
            Posting.id == posting_id,
            Posting.transaction_id == transaction_id,
            FinancialTransaction.user_id == owner,
        )
    )
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.id == receipt_id,
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == "bank_import.commit",
        )
    )
    if posting is None or posting.account_id is None or receipt is None:
        raise ImportError("import_evidence_mismatch", "Dowód nie odpowiada własnej płatności.")
    if (
        not row_ids
        or len(set(row_ids)) != len(row_ids)
        or signed_posting(posting) != attributed_source_amount
    ):
        raise ImportError(
            "import_evidence_mismatch", "Dowód nie odpowiada rzeczywistej kwocie płatności."
        )
    for row_id in row_ids:
        record = (
            await db.execute(
                select(ImportRow, ImportSource, ImportGroup)
                .join(ImportSource, ImportSource.id == ImportRow.source_id)
                .join(ImportGroupRow, ImportGroupRow.row_id == ImportRow.id)
                .join(ImportGroup, ImportGroup.id == ImportGroupRow.group_id)
                .where(
                    ImportRow.id == row_id,
                    ImportRow.user_id == owner,
                    ImportSource.user_id == owner,
                    ImportGroup.user_id == owner,
                )
            )
        ).one_or_none()
        if record is None:
            raise ImportError("row_not_found", "Nie znaleziono wiersza dowodu.", 404)
        row, source, group = record
        value = StatementRow.model_validate(row.fields)
        amount = (
            value.amount
            if component == "whole"
            else -value.fee
            if component == "fee"
            else value.amount + value.fee
        )
        if (
            amount != attributed_source_amount
            or value.currency != posting.source_currency
            or receipt.entity_id != row.batch_id
        ):
            raise ImportError("import_evidence_mismatch", "Komponent dowodu nie odpowiada źródłu.")
        existing = (
            await db.scalars(select(ImportEvidence).where(ImportEvidence.row_id == row_id))
        ).all()
        if any(
            evidence.component in {component, "whole"} or component == "whole"
            for evidence in existing
        ):
            raise ImportError(
                "row_already_committed", "Wiersz ma już rozliczony komponent lub całość."
            )
        # Strong identity is unique per bank+owned account+currency, not row text/hash.
        if value.bank_reference:
            identity = await db.scalar(
                select(ImportBankIdentity).where(
                    ImportBankIdentity.user_id == owner,
                    ImportBankIdentity.bank == source.bank,
                    ImportBankIdentity.account_id == posting.account_id,
                    ImportBankIdentity.currency == value.currency,
                    ImportBankIdentity.strong_reference == value.bank_reference,
                )
            )
            if identity is None:
                if source.bank is None:
                    raise ImportError("source_validation_blocked", "Brak tożsamości banku.")
                db.add(
                    ImportBankIdentity(
                        user_id=owner,
                        batch_id=row.batch_id,
                        group_id=group.id,
                        bank=source.bank,
                        account_id=posting.account_id,
                        currency=value.currency,
                        strong_reference=value.bank_reference,
                    )
                )
            else:
                known = await db.scalar(
                    select(ImportEvidence.id).where(
                        ImportEvidence.group_id == identity.group_id,
                        ImportEvidence.user_id == owner,
                        ImportEvidence.transaction_id == transaction_id,
                        ImportEvidence.posting_id == posting_id,
                    )
                )
                # Main+fee in the identity's own group legitimately use two postings.
                if identity.group_id != group.id and known is None:
                    raise ImportError(
                        "bank_identity_conflict", "Referencja bankowa dotyczy innej płatności."
                    )
        db.add(
            ImportEvidence(
                user_id=owner,
                batch_id=row.batch_id,
                group_id=group.id,
                row_id=row_id,
                transaction_id=transaction_id,
                posting_id=posting_id,
                receipt_id=receipt_id,
                component=component,
                attributed_source_amount=attributed_source_amount,
            )
        )
        await db.flush()
