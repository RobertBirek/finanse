import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user
from app.inbox.schemas import (
    InboxItemCreate,
    InboxItemResponse,
    InboxItemUpdate,
    ProcessInboxItem,
)
from app.inbox.service import (
    classify_inbox_item,
    create_inbox_item,
    delete_inbox_item,
    get_inbox_item,
    get_inbox_items,
    process_inbox_item,
    update_inbox_item,
)
from app.work.schemas import TaskResponse

router = APIRouter()


@router.post("/items", response_model=InboxItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    data: InboxItemCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await create_inbox_item(db, current_user.id, data)


@router.get("/items", response_model=list[InboxItemResponse])
async def list_items(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    is_processed: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await get_inbox_items(
        db, current_user.id, is_processed=is_processed, limit=limit, offset=offset
    )


@router.get("/items/{item_id}", response_model=InboxItemResponse)
async def get_item(
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await get_inbox_item(db, current_user.id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")
    return item


@router.patch("/items/{item_id}", response_model=InboxItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: InboxItemUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    item = await update_inbox_item(db, current_user.id, item_id, data)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    deleted = await delete_inbox_item(db, current_user.id, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inbox item not found")


@router.post("/items/{item_id}/classify", response_model=InboxItemResponse)
async def classify_item(
    item_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        return await classify_inbox_item(db, current_user.id, item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


class ProcessResponse(BaseModel):
    inbox_item: InboxItemResponse
    created_task: TaskResponse | None = None


@router.post("/items/{item_id}/process", response_model=ProcessResponse)
async def process_item(
    item_id: uuid.UUID,
    data: ProcessInboxItem,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        inbox_item, created_entity = await process_inbox_item(db, current_user.id, item_id, data)
        return {
            "inbox_item": inbox_item,
            "created_task": created_entity,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
