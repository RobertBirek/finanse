import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from openai import AsyncOpenAI, OpenAIError
from openai.types.responses.response_create_params import ResponseCreateParamsNonStreaming
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.ai_provider import OPENAI_ENDPOINT, elapsed_ms, provider_error, record_usage
from app.advisor.ai_settings import (
    AdvisorCredentials,
    CredentialUnavailable,
    ModelUnavailable,
    compose_prompt,
    get_profile,
    prompt_history,
    resolve_credentials,
)
from app.advisor.models import Conversation, Message, ToolExecution
from app.advisor.policies import get_policy_engine
from app.advisor.tools.registry import get_openai_tools, get_tool_by_name
from app.config import settings
from app.openai_client import ResponseOutputError, create_openai_client, response_text

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


def _get_llm_client(credentials: AdvisorCredentials) -> AsyncOpenAI:
    return create_openai_client(
        api_key=credentials.api_key,
        base_url=OPENAI_ENDPOINT,
        timeout=60,
    )


async def get_chat_configuration(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[AdvisorCredentials, str]:
    credentials = resolve_credentials(settings, user_id, await get_profile(db, user_id))
    versions = await prompt_history(db, user_id, limit=1)
    return credentials, compose_prompt(
        SYSTEM_PROMPT, versions[0].instructions if versions else None
    )


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
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, *, limit: int | None = None
) -> list[Message]:
    from sqlalchemy.orm import selectinload

    conv = await get_conversation(db, user_id, conversation_id)
    if conv is None:
        return []
    query = (
        select(Message)
        .options(selectinload(Message.tool_executions))
        .where(Message.conversation_id == conversation_id)
    )
    if limit is None:
        return list(await db.scalars(query.order_by(Message.created_at.asc(), Message.id.asc())))
    newest = await db.scalars(
        query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    )
    return list(reversed(newest.all()))


async def create_conversation(db: AsyncSession, user_id: uuid.UUID) -> Conversation:
    conv = Conversation(user_id=user_id, title="Nowa rozmowa")
    db.add(conv)
    await db.flush()
    return conv


MAX_TOOL_ITERATIONS = 3
logger = logging.getLogger(__name__)
ADVISOR_ERROR = "Nie udało się uzyskać odpowiedzi Doradcy. Spróbuj ponownie."
TOOL_ERROR = "Nie udało się wykonać narzędzia"
INVALID_ARGUMENTS = "Nieprawidłowe argumenty narzędzia"


class AdvisorUnavailable(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(ADVISOR_ERROR)


class ConversationNotFound(Exception):
    pass


def _parse_tool_arguments(raw: str) -> dict[str, Any]:
    try:
        arguments = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(INVALID_ARGUMENTS) from error
    if not isinstance(arguments, dict):
        raise TypeError(INVALID_ARGUMENTS)
    return arguments


async def _execute_read_tool(
    db: AsyncSession, tool: Any, user_id: uuid.UUID, arguments: dict[str, Any]
) -> tuple[dict, str]:
    try:
        # A failed SQL statement must not poison the conversation transaction.
        async with db.begin_nested():
            result = await tool.executor(db, str(user_id), **arguments)
            if not isinstance(result, dict):
                raise TypeError("Invalid tool result")
        return result, "completed"
    except (SQLAlchemyError, ValueError, KeyError, TypeError, RuntimeError) as error:
        logger.warning("Advisor read tool failed (%s)", type(error).__name__)
        return {"error": TOOL_ERROR}, "error"


def _tool_result_content(tool_execution: ToolExecution) -> str:
    if tool_execution.status == "pending_confirmation":
        return "⏳ Oczekuje na zatwierdzenie przez użytkownika."
    return json.dumps(tool_execution.result or {}, ensure_ascii=False, default=str)


def _history_messages(history: list[Message]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for msg in history:
        if msg.role == "tool":
            continue

        if msg.role == "assistant" and msg.tool_calls:
            for tool_call in cast(list[dict[str, Any]], msg.tool_calls):
                function = tool_call.get("function") or {}
                messages.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call.get("id"),
                        "name": function.get("name"),
                        "arguments": function.get("arguments", "{}"),
                    }
                )
        else:
            messages.append({"role": msg.role, "content": msg.content})

        if msg.role != "assistant" or not msg.tool_calls:
            continue

        executions = list(getattr(msg, "tool_executions", None) or [])
        used_execution_ids: set[uuid.UUID] = set()
        for tool_call in cast(list[dict[str, Any]], msg.tool_calls):
            call_id = tool_call.get("id")
            function = tool_call.get("function") or {}
            tool_name = function.get("name")
            try:
                call_arguments = _parse_tool_arguments(function.get("arguments", "{}"))
            except (ValueError, TypeError):
                call_arguments = {}

            execution = next(
                (
                    candidate
                    for candidate in executions
                    if candidate.id not in used_execution_ids
                    and candidate.tool_name == tool_name
                    and (candidate.arguments or {}) == call_arguments
                ),
                None,
            )
            if execution is None:
                execution = next(
                    (
                        candidate
                        for candidate in executions
                        if candidate.id not in used_execution_ids
                    ),
                    None,
                )
            if execution is None:
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(
                            {"error": "Nie udało się odtworzyć wyniku narzędzia"},
                            ensure_ascii=False,
                        ),
                    }
                )
                continue

            used_execution_ids.add(execution.id)
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": _tool_result_content(execution),
                }
            )

    return messages


def _bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode())


def bounded_history(history: list[Message], *, max_bytes: int) -> list[dict[str, Any]]:
    selected: list[list[dict[str, Any]]] = []
    for message in reversed(history):
        group = _history_messages([message])
        size = _bytes(group)
        if size > max_bytes:
            break
        selected.append(group)
        max_bytes -= size
    return [item for group in reversed(selected) for item in group]


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    content: str,
) -> Message:
    if conversation_id:
        conv = await get_conversation(db, user_id, conversation_id)
        if conv is None:
            raise ConversationNotFound
    else:
        conv = await create_conversation(db, user_id)
        conversation_id = conv.id

    try:
        credentials, prompt = await get_chat_configuration(db, user_id)
        if not credentials.model or not credentials.api_key:
            raise AdvisorUnavailable("not_configured")
    except (CredentialUnavailable, ModelUnavailable):
        raise AdvisorUnavailable("not_configured") from None
    history = await get_conversation_messages(
        db, user_id, conversation_id, limit=settings.ADVISOR_HISTORY_MAX_MESSAGES
    )
    current = {"role": "user", "content": content}
    protected = {"role": "developer", "content": prompt}
    remaining = settings.ADVISOR_CONTEXT_MAX_BYTES - _bytes([protected, current]) - 2
    if remaining < 0:
        raise AdvisorUnavailable("context_limit")
    messages: list[dict[str, Any]] = [
        protected,
        *bounded_history(history, max_bytes=remaining),
        current,
    ]
    db.add(
        Message(
            conversation_id=conversation_id,
            role="user",
            content=content,
            created_at=datetime.now(UTC),
        )
    )
    await db.flush()

    try:
        client = _get_llm_client(credentials)
    except ValueError:
        raise AdvisorUnavailable("not_configured") from None
    tools = get_openai_tools()

    pending_confirmation = False
    try:
        for _iteration in range(MAX_TOOL_ITERATIONS):
            if _bytes(messages) > settings.ADVISOR_CONTEXT_MAX_BYTES:
                raise AdvisorUnavailable("context_limit")
            start = time.monotonic()
            response = None
            try:
                request = cast(
                    ResponseCreateParamsNonStreaming,
                    {
                        "model": credentials.model,
                        "input": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "include": ["reasoning.encrypted_content"],
                        "reasoning": {"effort": settings.LLM_REASONING_EFFORT},
                        "max_output_tokens": settings.LLM_MAX_OUTPUT_TOKENS,
                        "store": False,
                    },
                )
                response = await client.responses.create(**request)
                if response.status != "completed" or any(
                    item.type not in ("message", "function_call", "reasoning")
                    or (
                        item.type == "message"
                        and any(part.type == "refusal" for part in item.content)
                    )
                    for item in response.output
                ):
                    raise ResponseOutputError("response was not usable")
                function_calls = [item for item in response.output if item.type == "function_call"]
                answer = None if function_calls else response_text(response, allow_reasoning=True)
            except (OpenAIError, ValueError, RuntimeError) as error:
                status = (
                    "unusable_response"
                    if isinstance(error, ResponseOutputError)
                    else provider_error(error)
                    if isinstance(error, OpenAIError)
                    else "provider_error"
                )
                await record_usage(
                    user_id, credentials.model, "chat", status, elapsed_ms(start), response
                )
                raise AdvisorUnavailable(status) from None

            await record_usage(
                user_id, credentials.model, "chat", "ok", elapsed_ms(start), response
            )
            if answer is not None:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                    created_at=datetime.now(UTC),
                )
                db.add(assistant_msg)
                await db.flush()
                _update_conversation_title(conv, content, len(history) + 1)
                return assistant_msg

            raw_tool_calls = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in function_calls
            ]
            assistant_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content="",
                created_at=datetime.now(UTC),
                tool_calls=raw_tool_calls,
                tool_executions=[],
            )
            db.add(assistant_msg)
            await db.flush()

            for item in response.output:
                dumped = item.model_dump(mode="json")
                messages.append(dumped)

            for tc in function_calls:
                tool_name = tc.name
                tool = get_tool_by_name(tool_name)

                invalid_arguments = False
                try:
                    arguments = _parse_tool_arguments(tc.arguments)
                except (ValueError, TypeError):
                    arguments = {}
                    invalid_arguments = True

                if invalid_arguments:
                    result = {"error": INVALID_ARGUMENTS}
                    status_val = "error"
                elif tool is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                    status_val = "error"
                elif get_policy_engine().requires_confirmation(tool_name, tool.autonomy_level):
                    result = {**arguments, "tool": tool_name}
                    status_val = "pending_confirmation"
                    pending_confirmation = True
                else:
                    result, status_val = await _execute_read_tool(db, tool, user_id, arguments)

                tool_exec = ToolExecution(
                    message_id=assistant_msg.id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    status=status_val,
                    autonomy_level=tool.autonomy_level if tool else 0,
                )
                assistant_msg.tool_executions.append(tool_exec)
                db.add(tool_exec)

                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": tc.call_id,
                        "output": json.dumps(result, ensure_ascii=False, default=str)
                        if status_val != "pending_confirmation"
                        else "⏳ Oczekuje na zatwierdzenie przez użytkownika.",
                    }
                )

            await db.flush()

            if pending_confirmation:
                _update_conversation_title(conv, content, len(history) + 1)
                return assistant_msg

        assistant_msg = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="Przetworzyłem dane. Czy potrzebujesz dodatkowych informacji?",
            created_at=datetime.now(UTC),
        )
        db.add(assistant_msg)
        _update_conversation_title(conv, content, len(history) + 1)
        await db.flush()
        return assistant_msg
    finally:
        await client.close()


def _update_conversation_title(conv: Conversation, first_message: str, history_length: int):
    if conv.title == "Nowa rozmowa" and history_length <= 1:
        title = first_message[:60] + ("..." if len(first_message) > 60 else "")
        conv.title = title
