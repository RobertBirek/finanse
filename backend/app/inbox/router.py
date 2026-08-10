import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user
from app.inbox.schemas import InboxItemCreate, InboxItemResponse, InboxItemUpdate
from app.inbox.service import (
    classify_inbox_item,
    create_inbox_item,
    delete_inbox_item,
    get_inbox_item,
    get_inbox_items,
    update_inbox_item,
)

router = APIRouter()


@router.post("/items", response_model=InboxItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: InboxItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_inbox_item(db, current_user.id, data)


@router.get("/items", response_model=list[InboxItemResponse])
async def list_items(
    is_processed: bool | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_inbox_items(db, current_user.id, is_processed=is_processed, limit=limit, offset=offset)


@router.get("/items/{item_id}", response_model=InboxItemResponse)
async def get_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_inbox_item(db, current_user.id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")
    return item


@router.patch("/items/{item_id}", response_model=InboxItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: InboxItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await update_inbox_item(db, current_user.id, item_id, data)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_inbox_item(db, current_user.id, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")


@router.post("/items/{item_id}/classify", response_model=InboxItemResponse)
async def classify_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await classify_inbox_item(db, current_user.id, item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
