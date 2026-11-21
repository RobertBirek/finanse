import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.decision_explanation import explain_facts
from app.advisor.decision_schemas import AttentionResult, DecisionExplanation
from app.advisor.decision_support import get_attention
from app.advisor.models import Conversation, Message, ToolExecution
from app.advisor.policies import get_policy_engine
from app.advisor.schemas import (
    ConversationResponse,
    MessageResponse,
    SendMessageRequest,
)
from app.advisor.service import (
    ADVISOR_ERROR,
    AdvisorUnavailable,
    ConversationNotFound,
    get_conversation,
    get_conversation_messages,
    get_user_conversations,
    send_message,
)
from app.database import get_db
from app.finance.cashflow import get_cashflow_forecast
from app.finance.cashflow_scenario import (
    CashflowScenarioInput,
    CashflowScenarioResult,
    simulate_expense,
)
from app.finance.spending_comparison import (
    PeriodDays,
    SpendingComparisonResult,
    get_spending_comparison,
)
from app.identity.models import User
from app.identity.router import get_current_user
from app.security.rate_limit import limit_advisor

router = APIRouter()
advisor_rate_limit = limit_advisor(get_current_user)


class _MutationResultError(Exception):
    pass


@router.get("/decisions/attention")
async def attention_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttentionResult:
    return await get_attention(db, current_user.id)


@router.post("/decisions/attention/explain")
async def explain_attention_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(advisor_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionExplanation:
    result = await get_attention(db, current_user.id)
    if not result.items:
        return DecisionExplanation(status="no_facts")
    return await explain_facts(
        db,
        current_user.id,
        {
            "topic": "priorytety",
            "items": [{"kind": item.kind, "reason": item.reason} for item in result.items],
        },
    )


async def _scenario(
    db: AsyncSession, user_id: uuid.UUID, data: CashflowScenarioInput
) -> CashflowScenarioResult:
    forecast = await get_cashflow_forecast(db, user_id)
    try:
        return simulate_expense(
            forecast, expense_date=data.expense_date, amount_pln_minor=data.amount_pln_minor
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.post("/decisions/cashflow-scenario")
async def scenario_endpoint(
    data: CashflowScenarioInput,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CashflowScenarioResult:
    return await _scenario(db, current_user.id, data)


@router.post("/decisions/cashflow-scenario/explain")
async def explain_scenario_endpoint(
    data: CashflowScenarioInput,
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(advisor_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionExplanation:
    scenario = await _scenario(db, current_user.id, data)
    return await explain_facts(
        db,
        current_user.id,
        {
            "topic": "hipotetyczny wydatek; zakres i ograniczenia prognozy płynności",
            "opening_balance_negative": scenario.opening_balance_negative,
            "scenario_negative": scenario.first_negative_date is not None,
            "has_excluded_obligations": bool(scenario.excluded_obligation_reasons),
            "covers_day_before_payday": scenario.covers_day_before_payday,
        },
    )


@router.get("/decisions/spending-comparison")
async def spending_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
) -> SpendingComparisonResult:
    period = _spending_period(days)
    return await get_spending_comparison(db, current_user.id, days=period)


def _spending_period(days: int) -> PeriodDays:
    match days:
        case 14:
            return 14
        case 30:
            return 30
        case 90:
            return 90
        case _:
            raise HTTPException(status_code=422, detail="Wybierz 14, 30 lub 90 dni.")


@router.post("/decisions/spending-comparison/explain")
async def explain_spending_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
    _limit: Annotated[None, Depends(advisor_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = 30,
) -> DecisionExplanation:
    result = await get_spending_comparison(db, current_user.id, days=_spending_period(days))
    if not result.categories and not result.transactions:
        return DecisionExplanation(status="no_facts")
    return await explain_facts(
        db,
        current_user.id,
        {
            "topic": "porównanie zamkniętych okresów wydatków; kwoty w groszach PLN",
            "period_days": days,
            "net_difference_pln_minor": result.delta_pln,
            "category_deltas_pln_minor": [category.delta_pln for category in result.categories],
            "details_truncated": result.truncated,
        },
    )


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
    conversation = await get_conversation(db, current_user.id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


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
    _limit: Annotated[None, Depends(advisor_rate_limit)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        assistant_msg = await send_message(
            db,
            current_user.id,
            data.conversation_id,
            data.content,
        )
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    except AdvisorUnavailable as error:
        raise HTTPException(
            status_code=409 if error.code == "not_configured" else 502,
            detail={"code": error.code, "message": ADVISOR_ERROR},
        ) from None
    except (OpenAIError, SQLAlchemyError, ValueError):
        raise HTTPException(status_code=500, detail=ADVISOR_ERROR) from None

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
        .options(selectinload(ToolExecution.message).selectinload(Message.conversation))
        .join(ToolExecution.message)
        .join(Message.conversation)
        .where(ToolExecution.id == execution_id, Conversation.user_id == current_user.id)
        .with_for_update(of=ToolExecution)
    )
    te = result.scalar_one_or_none()
    if te is None or te.message.conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tool execution not found")
    if te.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="Tool execution is no longer pending")

    tool = get_tool_by_name(te.tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Unknown tool")
    if not get_policy_engine().requires_confirmation(te.tool_name, tool.autonomy_level):
        raise HTTPException(status_code=409, detail="Tool no longer accepts confirmation")

    try:
        async with db.begin_nested():
            exec_result = await tool.executor(db, str(current_user.id), **(te.arguments or {}))
            if "error" in exec_result:
                raise _MutationResultError
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
    except (
        _MutationResultError,
        SQLAlchemyError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ):
        te.result = {"error": "Nie udało się wykonać narzędzia"}
        te.status = "error"
        te.policy_check_passed = False
        await db.flush()

    if te.status == "completed":
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
    from sqlalchemy.orm import selectinload

    from app.audit.service import log_event

    result = await db.execute(
        sa_select(ToolExecution)
        .options(selectinload(ToolExecution.message).selectinload(Message.conversation))
        .join(ToolExecution.message)
        .join(Message.conversation)
        .where(ToolExecution.id == execution_id, Conversation.user_id == current_user.id)
        .with_for_update(of=ToolExecution)
    )
    te = result.scalar_one_or_none()
    if te is None or te.message.conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tool execution not found")
    if te.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="Tool execution is no longer pending")

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
