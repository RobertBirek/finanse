"""Explicit owner-local shop identities; never inferred from supplier name or tax ID."""

import base64
import json
import uuid

from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import CategorizationError
from app.finance.receipt_commands import ReceiptCommandOutcome, receipt_locks, run_receipt_command
from app.finance.receipt_models import ReceiptItemRevision, ReceiptStore
from app.finance.receipt_schemas import (
    ReceiptStoreChange,
    ReceiptStoreCreate,
    ReceiptStorePage,
    ReceiptStoreResponse,
    ReceiptVersion,
    normalize_receipt_name,
)


def project_store(row: ReceiptStore) -> ReceiptStoreResponse:
    return ReceiptStoreResponse(id=row.id, name=row.name, active=row.active, version=row.version)


async def own_store(db: AsyncSession, owner: uuid.UUID, store_id: uuid.UUID) -> ReceiptStore:
    row = await db.scalar(
        select(ReceiptStore)
        .where(ReceiptStore.id == store_id, ReceiptStore.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise LookupError("Sklep nie istnieje.")
    return row


async def list_receipt_stores(
    db: AsyncSession, owner: uuid.UUID, *, cursor: str | None = None, include_inactive: bool = False
) -> ReceiptStorePage:
    q = select(ReceiptStore).where(ReceiptStore.user_id == owner)
    if not include_inactive:
        q = q.where(ReceiptStore.active.is_(True))
    if cursor:
        try:
            raw = json.loads(base64.urlsafe_b64decode(cursor))
            if (
                not isinstance(raw, list)
                or len(raw) != 3
                or raw[0] is not include_inactive
                or not isinstance(raw[1], str)
            ):
                raise ValueError("Invalid cursor")
            q = q.where(tuple_(ReceiptStore.name, ReceiptStore.id) > (raw[1], uuid.UUID(raw[2])))
        except (ValueError, TypeError, IndexError) as error:
            raise CategorizationError(
                "invalid_cursor", "Nieprawidłowa strona sklepów.", 422
            ) from error
    size = settings.FINANCE_RECEIPT_STORE_PAGE_SIZE
    rows = list(
        (await db.scalars(q.order_by(ReceiptStore.name, ReceiptStore.id).limit(size + 1))).all()
    )
    more = len(rows) > size
    rows = rows[:size]
    cursor = (
        base64.urlsafe_b64encode(
            json.dumps([include_inactive, rows[-1].name, str(rows[-1].id)]).encode()
        ).decode()
        if more
        else None
    )
    return ReceiptStorePage(items=[project_store(r) for r in rows], next_cursor=cursor)


async def create_receipt_store(
    db: AsyncSession, owner: uuid.UUID, data: ReceiptStoreCreate, *, idempotency_key: str
) -> ReceiptStoreResponse:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        from app.finance.receipt_schemas import validate_receipt_store_limit

        try:
            validate_receipt_store_limit(data.name)
        except ValueError as error:
            raise CategorizationError("store_limit", str(error), 422) from error
        await receipt_locks(db, owner)
        normalized = normalize_receipt_name(data.name)
        if await db.scalar(
            select(ReceiptStore.id).where(
                ReceiptStore.user_id == owner, ReceiptStore.normalized_name == normalized
            )
        ):
            raise CategorizationError(
                "store_exists", "Taki sklep już istnieje; wybierz go lub doprecyzuj nazwę oddziału."
            )
        row = ReceiptStore(user_id=owner, name=data.name, normalized_name=normalized, version=1)
        db.add(row)
        await db.flush()
        return ReceiptCommandOutcome(project_store(row), row.id, row.version, [row.id])

    return ReceiptStoreResponse.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="create_receipt_store",
            key=idempotency_key,
            payload=data.model_dump(mode="json"),
            operation=operation,
        )
    )


async def change_receipt_store(
    db: AsyncSession,
    owner: uuid.UUID,
    store_id: uuid.UUID,
    data: ReceiptStoreChange,
    *,
    idempotency_key: str,
) -> ReceiptStoreResponse:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        await receipt_locks(db, owner)
        row = await own_store(db, owner, store_id)
        if row.version != data.expected_version:
            raise CategorizationError("version_conflict", "Sklep zmienił się.")
        if data.name is not None:
            from app.finance.receipt_schemas import validate_receipt_store_limit

            try:
                validate_receipt_store_limit(data.name)
            except ValueError as error:
                raise CategorizationError("store_limit", str(error), 422) from error
            normalized = normalize_receipt_name(data.name)
            if await db.scalar(
                select(ReceiptStore.id).where(
                    ReceiptStore.user_id == owner,
                    ReceiptStore.id != row.id,
                    ReceiptStore.normalized_name == normalized,
                )
            ):
                raise CategorizationError("store_exists", "Taki sklep już istnieje.")
            row.name, row.normalized_name = data.name, normalized
        if data.active is not None:
            row.active = data.active
        row.version += 1
        await db.flush()
        return ReceiptCommandOutcome(project_store(row), row.id, row.version, [row.id])

    return ReceiptStoreResponse.model_validate(
        await run_receipt_command(
            db,
            owner,
            action="change_receipt_store",
            key=idempotency_key,
            payload={"store_id": str(store_id), **data.model_dump(mode="json", exclude_unset=True)},
            operation=operation,
        )
    )


class StoreDeletion(BaseModel):
    id: uuid.UUID
    deleted: bool = True


async def delete_receipt_store(
    db: AsyncSession,
    owner: uuid.UUID,
    store_id: uuid.UUID,
    data: ReceiptVersion,
    *,
    idempotency_key: str,
) -> dict[str, object]:
    async def operation(receipt_id: uuid.UUID) -> ReceiptCommandOutcome:
        await receipt_locks(db, owner)
        row = await own_store(db, owner, store_id)
        if row.version != data.expected_version:
            raise CategorizationError("version_conflict", "Sklep zmienił się.")
        if await db.scalar(
            select(ReceiptItemRevision.id).where(ReceiptItemRevision.store_id == store_id).limit(1)
        ):
            raise CategorizationError(
                "store_referenced", "Sklep ma historię; zarchiwizuj go zamiast usuwać."
            )
        await db.delete(row)
        await db.flush()
        return ReceiptCommandOutcome(
            StoreDeletion(id=store_id), store_id, data.expected_version, []
        )

    return await run_receipt_command(
        db,
        owner,
        action="delete_receipt_store",
        key=idempotency_key,
        payload={"store_id": str(store_id), **data.model_dump(mode="json")},
        operation=operation,
    )
