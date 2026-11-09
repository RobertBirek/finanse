"""Commit selected frozen groups atomically. No parsing, repricing or inferred matches."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.bank_transactions import BankTransactionInput, create_bank_transaction
from app.finance.credit_card_schemas import StatementCreate
from app.finance.credit_cards import create_statement
from app.finance.imports.commands import ImportCommandOutcome, run_import_command
from app.finance.imports.contracts import StatementRow
from app.finance.imports.decisions import load_batch, signed_posting
from app.finance.imports.errors import ImportError
from app.finance.imports.models import (
    ImportDecision,
    ImportEvidence,
    ImportGroup,
    ImportGroupRow,
    ImportPreview,
    ImportRevision,
    ImportRow,
    ImportSource,
)
from app.finance.imports.preview import canonical_preview_payload
from app.finance.imports.provenance import record_import_evidence
from app.finance.imports.queries import get_batch
from app.finance.imports.schemas import CommitRequest, CommitResult
from app.finance.models import Category, FinancialTransaction, Posting
from app.finance.queries import lock_accounts


async def _locked_payload(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, request: CommitRequest
) -> dict[str, Any]:
    batch = await load_batch(db, owner, batch_id, locked=True)
    for model in (ImportSource, ImportRevision, ImportGroup, ImportDecision):
        await db.execute(
            select(model)
            .where(model.batch_id == batch.id, model.user_id == owner)
            .order_by(model.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    preview = await db.scalar(
        select(ImportPreview)
        .where(
            ImportPreview.id == request.preview_id,
            ImportPreview.user_id == owner,
            ImportPreview.batch_id == batch_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if preview is None:
        raise ImportError("preview_not_found", "Nie znaleziono podglądu tego importu.", 404)
    if preview.request_hash != request.request_hash:
        raise ImportError("preview_stale", "Potwierdzenie nie odpowiada podglądowi.")
    payload: dict[str, Any] = preview.payload
    # All selected accounts (including the unseen side of a one-source transfer).
    account_ids = {uuid.UUID(value["id"]) for value in payload["snapshot"]["accounts"]}
    category_ids = {uuid.UUID(value["id"]) for value in payload["snapshot"]["categories"]}
    await lock_accounts(db, owner, account_ids, exclusive=True)
    await db.execute(
        select(Category)
        .where(Category.user_id == owner, Category.id.in_(category_ids))
        .order_by(Category.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    transaction_ids = select(Posting.transaction_id).where(Posting.account_id.in_(account_ids))
    await db.execute(
        select(FinancialTransaction)
        .where(FinancialTransaction.user_id == owner, FinancialTransaction.id.in_(transaction_ids))
        .order_by(FinancialTransaction.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    await db.execute(
        select(Posting)
        .where(Posting.account_id.in_(account_ids))
        .order_by(Posting.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # Re-read after waiting for exclusive account locks. Manual creations use FOR SHARE.
    return dict(await canonical_preview_payload(db, owner, request.preview_id))


async def commit_import(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, data: CommitRequest, key: str
) -> CommitResult:
    async def operation(receipt_id: uuid.UUID) -> ImportCommandOutcome:
        payload = await _locked_payload(db, owner, batch_id, data)
        transactions: list[uuid.UUID] = []
        linked: list[uuid.UUID] = []
        for plan in payload["plans"]:
            group_id = uuid.UUID(plan["group_id"])
            if plan["action"] == "link":
                for link in plan["links"]:
                    row_id = uuid.UUID(link["row_id"])
                    await record_import_evidence(
                        db,
                        owner,
                        row_ids=[row_id],
                        transaction_id=uuid.UUID(plan["transaction_id"]),
                        posting_id=uuid.UUID(link["posting_id"]),
                        receipt_id=receipt_id,
                        component="whole",
                        attributed_source_amount=link["attributed_source_amount"],
                    )
                    linked.append(row_id)
            else:
                members = (
                    await db.scalars(
                        select(ImportRow)
                        .join(ImportGroupRow, ImportGroupRow.row_id == ImportRow.id)
                        .where(ImportGroupRow.group_id == group_id, ImportRow.user_id == owner)
                    )
                ).all()
                group_snapshot = next(
                    item
                    for item in payload["snapshot"]["groups"]
                    if item["group"]["id"] == str(group_id)
                )
                decision = group_snapshot["decision"]["data"]
                for operation_plan in plan["operations"]:
                    transaction_data = BankTransactionInput.model_validate(
                        {
                            field: operation_plan[field]
                            for field in (
                                "kind",
                                "booking_date",
                                "purchase_date",
                                "description",
                                "postings",
                            )
                        }
                    )
                    txn = await create_bank_transaction(db, owner, transaction_data)
                    transactions.append(txn.id)
                    for row in members:
                        if str(row.id) not in operation_plan["row_ids"]:
                            continue
                        value = StatementRow.model_validate(row.fields)
                        account_id = (
                            decision["other_account_id"]
                            if decision["kind"] in {"exchange", "transfer"}
                            and len(members) == 2
                            and value.amount + value.fee > 0
                            else decision["account_id"]
                        )
                        posting = next(
                            item for item in txn.postings if str(item.account_id) == account_id
                        )
                        await record_import_evidence(
                            db,
                            owner,
                            row_ids=[row.id],
                            transaction_id=txn.id,
                            posting_id=posting.id,
                            receipt_id=receipt_id,
                            component=operation_plan["component"],
                            attributed_source_amount=signed_posting(posting),
                        )
            if "card_statement" in plan:
                metadata = plan["card_statement"]
                statement = dict(metadata["data"])
                # Stable per source, independent of retries, preview IDs or selected groups.
                statement["request_id"] = str(
                    uuid.uuid5(uuid.UUID(metadata["source_id"]), "bank-import-card-statement")
                )
                await create_statement(
                    db,
                    owner,
                    uuid.UUID(metadata["account_id"]),
                    StatementCreate.model_validate(statement),
                )
            group = await db.get(ImportGroup, group_id)
            assert group is not None
            group.state = "committed"
        await db.flush()
        # Verify source-component conservation before writing the durable receipt.
        selected_ids = [uuid.UUID(value) for value in payload["group_ids"]]
        rows = (
            await db.scalars(
                select(ImportRow)
                .join(ImportGroupRow, ImportGroupRow.row_id == ImportRow.id)
                .where(ImportRow.user_id == owner, ImportGroupRow.group_id.in_(selected_ids))
            )
        ).all()
        for row in rows:
            amounts = (
                await db.scalars(
                    select(ImportEvidence.attributed_source_amount).where(
                        ImportEvidence.row_id == row.id
                    )
                )
            ).all()
            if sum(amounts) != StatementRow.model_validate(row.fields).amount:
                raise ImportError(
                    "import_evidence_mismatch",
                    "Komponenty nie zachowują rzeczywistej zmiany salda źródła.",
                )
        batch = await load_batch(db, owner, batch_id)
        batch.version += 1
        dto = await get_batch(db, owner, batch_id)
        assert dto is not None
        batch.commit_state = "partial" if dto.unresolved_count else "committed"
        remaining = [group.id for group in dto.groups if group.state != "committed"]
        result = CommitResult(
            receipt_id=receipt_id,
            batch_id=batch_id,
            request_hash=data.request_hash,
            transaction_ids=transactions,
            linked_row_ids=linked,
            remaining_group_ids=remaining,
            commit_state="partial" if dto.unresolved_count else "committed",
        )
        return ImportCommandOutcome(result, batch_id, batch.version, transactions)

    response = await run_import_command(
        db,
        owner,
        action="bank_import.commit",
        key=key,
        batch_id=batch_id,
        payload=data.model_dump(mode="json"),
        operation=operation,
    )
    return CommitResult.model_validate(response)
