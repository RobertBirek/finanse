import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user
from app.advisor.schemas import (
    ChatRequest,
    MessageResponse,
    ConversationResponse,
    SendMessageRequest,
)
from app.advisor.service import (
    get_user_conversations,
    get_conversation_messages,
    send_message,
)

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_conversations(db, current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await get_user_conversations(db, current_user.id)
    for c in conv:
        if c.id == conversation_id:
            return c
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_conversation_messages(db, current_user.id, conversation_id)


@router.post("/messages", response_model=MessageResponse)
async def send_message_endpoint(
    data: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        assistant_msg = await send_message(
            db,
            current_user.id,
            data.conversation_id,
            data.content,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload
    from app.advisor.models import Message as MsgModel
    result = await db.execute(
        sa_select(MsgModel).options(
            selectinload(MsgModel.tool_executions)
        ).where(MsgModel.id == assistant_msg.id)
    )
    assistant_msg = result.scalar_one()
    return MessageResponse.model_validate(assistant_msg)
