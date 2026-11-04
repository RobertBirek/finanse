import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.finance.categorization_context import CategorizationError
from app.finance.categorization_router import Database, Owner, _error
from app.finance.receipt_items import discard_receipt_draft, get_receipt_items, save_receipt_draft
from app.finance.receipt_schemas import (
    ReceiptDraftSave,
    ReceiptHistoryPage,
    ReceiptItemsApprove,
    ReceiptItemsContext,
    ReceiptPaymentApply,
    ReceiptPaymentContext,
    ReceiptPaymentPreview,
    ReceiptPaymentRequest,
    ReceiptPaymentResult,
    ReceiptStoreChange,
    ReceiptStoreCreate,
    ReceiptStorePage,
    ReceiptStoreResponse,
    ReceiptVersion,
)
from app.finance.receipt_stores import (
    change_receipt_store,
    create_receipt_store,
    delete_receipt_store,
    list_receipt_stores,
)
from app.finance.rule_router import Key

router = APIRouter()


@router.get("/bills/{bill_id}/items/payment", response_model=ReceiptPaymentContext)
async def payment_context_get(bill_id: uuid.UUID, current_user: Owner, db: Database):
    from app.finance.receipt_payment import get_receipt_payment_context

    try:
        return await get_receipt_payment_context(db, current_user.id, bill_id)
    except LookupError as error:
        return _error(error)


@router.post("/bills/{bill_id}/items/payment-preview", response_model=ReceiptPaymentPreview)
async def payment_preview_post(
    bill_id: uuid.UUID, data: ReceiptPaymentRequest, current_user: Owner, db: Database
):
    from app.finance.receipt_payment import preview_receipt_payment

    try:
        return await preview_receipt_payment(db, current_user.id, bill_id, data)
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/bills/{bill_id}/items/payment-apply", response_model=ReceiptPaymentResult)
async def payment_apply_post(
    bill_id: uuid.UUID,
    data: ReceiptPaymentApply,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    from app.finance.receipt_payment import apply_receipt_payment

    try:
        result = await apply_receipt_payment(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/bills/{bill_id}/items/history", response_model=ReceiptHistoryPage)
async def item_history_get(
    bill_id: uuid.UUID,
    store_id: uuid.UUID,
    name: Annotated[str, Query(min_length=1, max_length=2000)],
    current_user: Owner,
    db: Database,
):
    from app.finance.receipt_history import get_receipt_history

    try:
        return await get_receipt_history(db, current_user.id, bill_id, store_id=store_id, name=name)
    except (LookupError, CategorizationError) as error:
        return _error(error)


@router.post("/bills/{bill_id}/items/approve", response_model=ReceiptItemsContext)
async def items_approve(
    bill_id: uuid.UUID,
    data: ReceiptItemsApprove,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    from app.finance.receipt_approval import approve_receipt_items

    try:
        result = await approve_receipt_items(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/receipt-stores", response_model=ReceiptStorePage)
async def stores_get(
    current_user: Owner,
    db: Database,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    include_inactive: bool = False,
):
    try:
        return await list_receipt_stores(
            db, current_user.id, cursor=cursor, include_inactive=include_inactive
        )
    except CategorizationError as error:
        return _error(error)


@router.post("/receipt-stores", response_model=ReceiptStoreResponse)
async def store_create(
    data: ReceiptStoreCreate, current_user: Owner, db: Database, idempotency_key: Key
):
    try:
        result = await create_receipt_store(
            db, current_user.id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.patch("/receipt-stores/{store_id}", response_model=ReceiptStoreResponse)
async def store_change(
    store_id: uuid.UUID,
    data: ReceiptStoreChange,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await change_receipt_store(
            db, current_user.id, store_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.delete("/receipt-stores/{store_id}")
async def store_delete(
    store_id: uuid.UUID,
    data: ReceiptVersion,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await delete_receipt_store(
            db, current_user.id, store_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.get("/bills/{bill_id}/items", response_model=ReceiptItemsContext)
async def items_get(bill_id: uuid.UUID, current_user: Owner, db: Database):
    try:
        return await get_receipt_items(db, current_user.id, bill_id)
    except LookupError as error:
        return _error(error)


@router.post("/bills/{bill_id}/items/draft", response_model=ReceiptItemsContext)
async def draft_save(
    bill_id: uuid.UUID,
    data: ReceiptDraftSave,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await save_receipt_draft(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)


@router.post("/bills/{bill_id}/items/discard-draft", response_model=ReceiptItemsContext)
async def draft_discard(
    bill_id: uuid.UUID,
    data: ReceiptVersion,
    current_user: Owner,
    db: Database,
    idempotency_key: Key,
):
    try:
        result = await discard_receipt_draft(
            db, current_user.id, bill_id, data, idempotency_key=idempotency_key
        )
        await db.commit()
        return result
    except (LookupError, CategorizationError) as error:
        await db.rollback()
        return _error(error)
