"""Owner-scoped durable command receipt; receipt and operation share one savepoint."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.document_guards import lock_document_mutations
from app.finance.imports.errors import ImportError
from app.finance.imports.models import ImportBatch
from app.finance.imports.preview import digest
from app.finance.models import FinanceCommandReceipt


@dataclass
class ImportCommandOutcome:
    response: BaseModel
    entity_id: uuid.UUID
    version: int | None
    result_ids: list[uuid.UUID]


def _action(kind: str) -> str:
    return "bank_import.commit" if kind == "statement" else "loan_schedule.activate"


async def run_import_command(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    action: str,
    key: str,
    batch_id: uuid.UUID,
    payload: dict[str, object],
    operation: Callable[[uuid.UUID], Awaitable[ImportCommandOutcome]],
) -> dict[str, object]:
    if action not in {"bank_import.commit", "loan_schedule.activate"}:
        raise ValueError("Unsupported import command action")
    if not key.strip() or len(key) > 200:
        raise ImportError("idempotency_key_invalid", "Wymagany klucz decyzji do 200 znaków.", 422)
    # A failed command must not leave partial postings/receipts even when caught by HTTP.
    async with db.begin_nested():
        await db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtext(f"import-command:{owner}:{action}:{key}"))
            )
        )
        batch = await db.scalar(
            select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == owner)
        )
        if batch is None:
            raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
        if action != _action(batch.kind):
            raise ImportError(
                "import_kind_mismatch", "Polecenie nie pasuje do rodzaju importu.", 422
            )
        hashed = digest({"batch_id": str(batch_id), "action": action, "payload": payload})
        receipt = await db.scalar(
            select(FinanceCommandReceipt)
            .where(
                FinanceCommandReceipt.user_id == owner,
                FinanceCommandReceipt.action == action,
                FinanceCommandReceipt.key == key,
            )
            .execution_options(populate_existing=True)
        )
        if receipt is not None:
            if receipt.request_hash != hashed or receipt.entity_id != batch_id:
                raise ImportError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
            return receipt.response_json
        await lock_document_mutations(db, owner)
        receipt = FinanceCommandReceipt(
            id=uuid.uuid4(),
            user_id=owner,
            action=action,
            key=key,
            request_hash=hashed,
            entity_id=batch_id,
            response_json={},
        )
        db.add(receipt)
        await db.flush([receipt])
        outcome = await operation(receipt.id)
        response = outcome.response.model_dump(mode="json")
        if (
            outcome.entity_id != batch_id
            or response.get("batch_id") != str(batch_id)
            or not isinstance(response.get("request_hash"), str)
        ):
            raise ValueError("Import command returned an unbound result")
        receipt.version = outcome.version
        receipt.result_ids = [str(value) for value in outcome.result_ids]
        receipt.response_json = response
        await log_event(
            db,
            owner,
            "bank_import_batch" if batch.kind == "statement" else "loan_schedule_batch",
            str(batch_id),
            action,
            new_state={
                "version": outcome.version,
                "result_ids": receipt.result_ids,
                "request_hash": response["request_hash"],
            },
        )
        await db.flush()
        return response


async def get_command_result(
    db: AsyncSession, owner: uuid.UUID, batch_id: uuid.UUID, key: str
) -> dict[str, object] | None:
    batch = await db.scalar(
        select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == owner)
    )
    if batch is None:
        raise ImportError("import_not_found", "Nie znaleziono importu.", 404)
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.entity_id == batch_id,
            FinanceCommandReceipt.action == _action(batch.kind),
            FinanceCommandReceipt.key == key,
        )
    )
    return receipt.response_json if receipt else None


async def run_preparation_command(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    action: str,
    key: str,
    batch_id: uuid.UUID | None,
    payload: dict[str, object],
    operation: Callable[[], Awaitable[BaseModel]],
) -> dict[str, object]:
    """Durable nonfinancial intents; never expand run_import_command's action allowlist."""
    if action not in {
        "bank_import.create",
        "bank_import.attach",
        "bank_import.decisions",
        "bank_import.preview",
        "bank_import.archive",
    }:
        raise ValueError("Unsupported preparation action")
    if not key.strip() or len(key) > 200:
        raise ImportError("idempotency_key_invalid", "Wymagany klucz decyzji do 200 znaków.", 422)
    hashed = digest(
        {"action": action, "batch_id": str(batch_id) if batch_id else None, "payload": payload}
    )
    async with db.begin_nested():
        await db.execute(
            select(
                func.pg_advisory_xact_lock(func.hashtext(f"import-command:{owner}:{action}:{key}"))
            )
        )
        receipt = await db.scalar(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.user_id == owner,
                FinanceCommandReceipt.action == action,
                FinanceCommandReceipt.key == key,
            )
        )
        if receipt is not None:
            if receipt.request_hash != hashed:
                raise ImportError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
            return receipt.response_json
        response = (await operation()).model_dump(mode="json")
        entity_id = batch_id or uuid.UUID(response["id"])
        receipt = FinanceCommandReceipt(
            user_id=owner,
            action=action,
            key=key,
            request_hash=hashed,
            entity_id=entity_id,
            response_json=response,
        )
        db.add(receipt)
        await log_event(
            db,
            owner,
            "bank_import_batch",
            str(entity_id),
            action,
            new_state={"request_hash": hashed},
        )
        await db.flush()
        return response
