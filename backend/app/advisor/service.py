import json
import uuid
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.models import Conversation, Message, ToolExecution
from app.advisor.tools.registry import get_openai_tools, get_tool_by_name
from app.config import settings

SYSTEM_PROMPT = """Jesteś osobistym doradcą. Pomagasz użytkownikowi zarządzać czasem, pieniędzmi i projektami.

Masz dostęp do narzędzi, które pozwalają Ci odczytywać dane użytkownika:
- get_accounts — lista kont z saldami
- get_financial_summary — podsumowanie finansowe za bieżący miesiąc
- get_transactions — lista transakcji (filtruj po type: income/expense/transfer)
- get_today_schedule — dzisiejszy kalendarz (time blocki) i zadania
- get_tasks — lista zadań (filtruj po status, project_id)
- get_projects — lista projektów z ich statusami

Masz też dostęp do narzędzi mutujących (wymagają potwierdzenia użytkownika):
- create_task — tworzy nowe zadanie (title, priority, due_date, project_id)
- create_time_block — tworzy blok czasu (title, start_time, end_time, block_type)
- create_transaction — tworzy transakcję (type, amount w groszach, currency, description, account_name, category_name)

Zasady:
- Odpowiadasz po polsku, zwięźle i konkretnie
- ZAWSZE używasz narzędzi gdy użytkownik pyta o dane ze swojego konta
- Nigdy nie wymyślasz liczb — pobierasz je przez narzędzia
- Formatujesz kwoty czytelnie: "1 234,56 PLN" (nie "123456")
- Gdy użytkownik prosi o podsumowanie, użyj get_financial_summary
- Sugerujesz działania, ale nie podejmujesz decyzji za użytkownika
- Jesteś pomocny, ale nie nachalny
- Gdy użytkownik prosi o utworzenie czegoś (zadania, bloku, transakcji), ZAWSZE użyj odpowiedniego narzędzia mutującego
- Kwoty w transakcjach podajesz w groszach (50 PLN = 5000)"""


def _get_llm_client() -> AsyncOpenAI:
    api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
    return AsyncOpenAI(api_key=api_key, base_url=settings.LLM_BASE_URL)


async def get_user_conversations(db: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_conversation(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def get_conversation_messages(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[Message]:
    from sqlalchemy.orm import selectinload

    conv = await get_conversation(db, user_id, conversation_id)
    if conv is None:
        return []
    result = await db.execute(
        select(Message)
        .options(selectinload(Message.tool_executions))
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def create_conversation(db: AsyncSession, user_id: uuid.UUID) -> Conversation:
    conv = Conversation(user_id=user_id, title="Nowa rozmowa")
    db.add(conv)
    await db.flush()
    return conv


MAX_TOOL_ITERATIONS = 3


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    content: str,
) -> Message:
    if conversation_id:
        conv = await get_conversation(db, user_id, conversation_id)
        if conv is None:
            conv = await create_conversation(db, user_id)
            conversation_id = conv.id
    else:
        conv = await create_conversation(db, user_id)
        conversation_id = conv.id

    user_msg = Message(conversation_id=conversation_id, role="user", content=content)
    db.add(user_msg)
    await db.flush()

    history = await get_conversation_messages(db, user_id, conversation_id)
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        if msg.role == "tool":
            continue
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        messages.append(entry)

    client = _get_llm_client()
    tools = get_openai_tools()

    pending_confirmation = False
    for _iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=cast(list[ChatCompletionMessageParam], messages),
                tools=cast(list[ChatCompletionToolParam], tools),
                tool_choice="auto",
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception as e:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=f"Przepraszam, wystąpił błąd: {str(e)[:200]}",
            )
            db.add(assistant_msg)
            await db.flush()
            return assistant_msg

        choice = response.choices[0]
        llm_message = choice.message

        if not llm_message.tool_calls:
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=llm_message.content or "",
            )
            db.add(assistant_msg)
            await db.flush()
            _update_conversation_title(conv, content, len(history))
            return assistant_msg

        raw_tool_calls = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in llm_message.tool_calls
        ]
        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=llm_message.content,
            tool_calls=raw_tool_calls,
        )
        db.add(assistant_msg)
        await db.flush()

        messages.append(
            {
                "role": "assistant",
                "content": llm_message.content,
                "tool_calls": raw_tool_calls,
            }
        )

        for tc in llm_message.tool_calls:
            tool_name = tc.function.name
            tool = get_tool_by_name(tool_name)

            try:
                arguments = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            if tool is None:
                result = {"error": f"Unknown tool: {tool_name}"}
                status_val = "error"
            elif tool.autonomy_level >= 2:
                result = {**arguments, "tool": tool_name}
                status_val = "pending_confirmation"
                pending_confirmation = True
            else:
                try:
                    result = await tool.executor(db, str(user_id), **arguments)
                    status_val = "completed"
                except Exception as e:
                    result = {"error": str(e)}
                    status_val = "error"

            tool_exec = ToolExecution(
                message_id=assistant_msg.id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status=status_val,
                autonomy_level=tool.autonomy_level if tool else 0,
            )
            db.add(tool_exec)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)
                    if status_val != "pending_confirmation"
                    else "⏳ Oczekuje na zatwierdzenie przez użytkownika.",
                }
            )

        await db.flush()

        if pending_confirmation:
            _update_conversation_title(conv, content, len(history))
            return assistant_msg

    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content="Przetworzyłem dane. Czy potrzebujesz dodatkowych informacji?",
    )
    db.add(assistant_msg)
    _update_conversation_title(conv, content, len(history))
    await db.flush()
    return assistant_msg


def _update_conversation_title(conv: Conversation, first_message: str, history_length: int):
    if conv.title == "Nowa rozmowa" and history_length <= 1:
        title = first_message[:60] + ("..." if len(first_message) > 60 else "")
        conv.title = title
