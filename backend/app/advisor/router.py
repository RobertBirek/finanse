import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.models import Message, ToolExecution
from app.advisor.schemas import (
    ConversationResponse,
    MessageResponse,
    SendMessageRequest,
)
from app.advisor.service import (
    get_conversation_messages,
    get_user_conversations,
    send_message,
)
from app.database import get_db
from app.identity.models import User
from app.identity.router import get_current_user

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_user_conversations(db, current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    conv = await get_user_conversations(db, current_user.id)
    for c in conv:
        if c.id == conversation_id:
            return c
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await get_conversation_messages(db, current_user.id, conversation_id)


@router.post("/messages", response_model=MessageResponse)
async def send_message_endpoint(
    data: SendMessageRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        assistant_msg = await send_message(
            db,
            current_user.id,
            data.conversation_id,
            data.content,
        )
    except (OpenAIError, SQLAlchemyError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from app.advisor.models import Message as MsgModel

    result = await db.execute(
        sa_select(MsgModel)
        .options(selectinload(MsgModel.tool_executions))
        .where(MsgModel.id == assistant_msg.id)
    )
    assistant_msg = result.scalar_one()
    return MessageResponse.model_validate(assistant_msg)


@router.post("/tool-executions/{execution_id}/confirm", response_model=MessageResponse)
async def confirm_tool_execution(
    execution_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):

    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from app.advisor.tools.registry import get_tool_by_name

    result = await db.execute(
        sa_select(ToolExecution)
        .options(selectinload(ToolExecution.message))
        .where(ToolExecution.id == execution_id)
    )
    te = result.scalar_one_or_none()
    if te is None or te.message.conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tool execution not found")

    tool = get_tool_by_name(te.tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown tool")

    try:
        exec_result = await tool.executor(db, str(current_user.id), **(te.arguments or {}))
        te.result = exec_result
        te.status = "completed"
        te.policy_check_passed = True

        from app.audit.service import log_event

        await log_event(
            db,
            current_user.id,
            "tool_execution",
            str(te.id),
            "confirm",
            old_state={"status": "pending_confirmation"},
            new_state={"status": "completed", "result": exec_result},
            performed_by="human",
        )
    except (SQLAlchemyError, ValueError, KeyError) as e:
        te.result = {"error": str(e)}
        te.status = "error"

    await db.flush()

    result = await db.execute(
        sa_select(Message)
        .options(selectinload(Message.tool_executions))
        .where(Message.id == te.message_id)
    )
    return result.scalar_one()


@router.post("/tool-executions/{execution_id}/deny")
async def deny_tool_execution(
    execution_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from sqlalchemy import select as sa_select

    from app.audit.service import log_event

    result = await db.execute(sa_select(ToolExecution).where(ToolExecution.id == execution_id))
    te = result.scalar_one_or_none()
    if te is None:
        raise HTTPException(status_code=404, detail="Tool execution not found")

    te.status = "denied"
    te.result = {"message": "Odrzucone przez użytkownika"}

    await log_event(
        db,
        current_user.id,
        "tool_execution",
        str(te.id),
        "deny",
        old_state={"status": "pending_confirmation"},
        new_state={"status": "denied"},
        performed_by="human",
    )

    await db.flush()
    return {"status": "denied"}
