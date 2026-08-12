import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inbox.models import InboxItem
from app.inbox.schemas import InboxItemCreate, InboxItemUpdate, ProcessInboxItem
from app.work.models import Task as WorkTask


async def create_inbox_item(db: AsyncSession, user_id: uuid.UUID, data: InboxItemCreate) -> InboxItem:
    item = InboxItem(user_id=user_id, **data.model_dump())
    db.add(item)
    await db.flush()
    return item


async def get_inbox_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    is_processed: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[InboxItem]:
    stmt = select(InboxItem).where(InboxItem.user_id == user_id)
    if is_processed is not None:
        stmt = stmt.where(InboxItem.is_processed == is_processed)
    stmt = stmt.order_by(InboxItem.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_inbox_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> InboxItem | None:
    result = await db.execute(
        select(InboxItem).where(InboxItem.id == item_id, InboxItem.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_inbox_item(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, data: InboxItemUpdate
) -> InboxItem | None:
    item = await get_inbox_item(db, user_id, item_id)
    if item is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    await db.flush()
    return item


async def delete_inbox_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
    item = await get_inbox_item(db, user_id, item_id)
    if item is None:
        return False
    await db.delete(item)
    await db.flush()
    return True


async def classify_inbox_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> InboxItem:
    item = await get_inbox_item(db, user_id, item_id)
    if item is None:
        raise ValueError(f"InboxItem {item_id} not found")

    # Placeholder AI classification — in future this will call an LLM
    keywords_to_type = {
        "kup": "transaction",
        "wyd": "transaction",
        "zadanie": "task",
        "projekt": "project",
        "dokument": "document",
        "decyzja": "decision",
    }
    content_lower = item.content.lower()
    suggested_type = "reference"
    for keyword, ttype in keywords_to_type.items():
        if keyword in content_lower:
            suggested_type = ttype
            break

    item.target_type = suggested_type
    item.classified_by = "keyword"
    item.agent_suggestion = {"suggested_type": suggested_type, "confidence": "low"}
    await db.flush()
    return item


async def process_inbox_item(
    db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, data: ProcessInboxItem
) -> tuple[InboxItem, WorkTask | None]:
    """Process an inbox item: create the target entity and mark as processed."""
    item = await get_inbox_item(db, user_id, item_id)
    if item is None:
        raise ValueError(f"InboxItem {item_id} not found")
    if item.is_processed:
        raise ValueError("Inbox item already processed")

    created_entity = None

    if data.target_type == "task":
        task = WorkTask(
            user_id=user_id,
            title=item.content,
            source="inbox",
        )
        db.add(task)
        await db.flush()
        item.target_id = task.id
        created_entity = task

    item.target_type = data.target_type
    item.is_processed = True
    item.classified_by = "human"
    await db.flush()
    await db.refresh(item)
    if created_entity:
        await db.refresh(created_entity)

    return item, created_entity
