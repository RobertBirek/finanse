import uuid
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.advisor.models import Conversation, Message

SYSTEM_PROMPT = """Jesteś osobistym doradcą. Pomagasz użytkownikowi zarządzać czasem, pieniędzmi i projektami.

Zasady:
- Odpowiadasz po polsku, zwięźle i konkretnie
- Jeśli nie znasz odpowiedzi, mów o tym wprost
- Nie wymyślasz danych finansowych — jeśli potrzebujesz konkretnych liczb, powiedz że nie masz do nich dostępu
- Sugerujesz działania, ale nie podejmujesz decyzji za użytkownika
- Jesteś pomocny, ale nie nachalny"""


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
    conv = await get_conversation(db, user_id, conversation_id)
    if conv is None:
        return []
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def create_conversation(db: AsyncSession, user_id: uuid.UUID) -> Conversation:
    conv = Conversation(user_id=user_id, title="Nowa rozmowa")
    db.add(conv)
    await db.flush()
    return conv


async def send_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    content: str,
) -> Message:
    # Get or create conversation
    if conversation_id:
        conv = await get_conversation(db, user_id, conversation_id)
        if conv is None:
            conv = await create_conversation(db, user_id)
            conversation_id = conv.id
    else:
        conv = await create_conversation(db, user_id)
        conversation_id = conv.id

    # Save user message
    user_msg = Message(
        conversation_id=conversation_id, role="user", content=content
    )
    db.add(user_msg)
    await db.flush()

    # Get chat history
    history = await get_conversation_messages(db, user_id, conversation_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # Call DeepSeek
    client = _get_llm_client()
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        assistant_content = response.choices[0].message.content or ""
    except Exception as e:
        assistant_content = f"Przepraszam, wystąpił błąd połączenia z asystentem. Spróbuj ponownie później. ({str(e)[:100]})"

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation_id, role="assistant", content=assistant_content
    )
    db.add(assistant_msg)

    # Update conversation title from first message
    if conv.title == "Nowa rozmowa" and len(history) <= 1:
        title = content[:60] + ("..." if len(content) > 60 else "")
        conv.title = title

    await db.flush()

    return assistant_msg
