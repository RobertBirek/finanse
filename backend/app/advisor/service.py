import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.models import Conversation, Message


async def get_or_create_conversation(db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None = None) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(user_id=user_id, title="New Conversation")
    db.add(conv)
    await db.flush()
    return conv


async def add_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    tool_calls: dict | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
    )
    db.add(message)
    await db.flush()
    return message


async def get_conversation_messages(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .join(Conversation)
        .where(Message.conversation_id == conversation_id, Conversation.user_id == user_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())
