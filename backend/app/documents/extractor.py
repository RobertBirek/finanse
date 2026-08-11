"""Extract structured financial data from document text using OpenAI/DeepSeek."""

import json
import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.inbox.models import InboxItem

EXTRACTION_PROMPT = """Jesteś asystentem do ekstrakcji danych finansowych z dokumentów.

Przeanalizuj poniższy tekst dokumentu i wyciągnij z niego dane finansowe.
Jeśli dokument NIE zawiera żadnych danych finansowych (kwot, transakcji), zwróć detected=false.

Jeśli dokument zawiera dane finansowe, zwróć:
- type: "expense" (wydatek) lub "income" (przychód)
- amount: kwota w groszach/centach (np. 50.00 PLN = 5000)
- currency: "PLN", "EUR" lub "USD"
- description: krótki opis transakcji (np. nazwa sklepu + co kupiono)
- date: data transakcji w formacie YYYY-MM-DD
- category_suggestion: sugerowana kategoria (np. "Jedzenie", "Transport", "Rachunki")

Zwróć TYLKO JSON, bez dodatkowego tekstu."""


def _get_client() -> AsyncOpenAI:
    api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
    return AsyncOpenAI(api_key=api_key, base_url=settings.LLM_BASE_URL)


async def extract_financial_data(text: str) -> dict:
    """Send OCR text to LLM, return structured financial data as dict."""
    client = _get_client()

    # Truncate text to avoid token limits
    truncated = text[:8000] if len(text) > 8000 else text

    response = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": truncated},
        ],
        temperature=0.1,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content or '{"detected": false}'

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {"detected": False}

    # Ensure defaults
    data.setdefault("detected", False)
    return data


async def create_inbox_from_document(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    original_name: str,
    data: dict,
) -> InboxItem:
    """Create an inbox item from extracted document data."""
    amount_pln = data.get("amount", 0) / 100
    description = data.get("description", "Dokument")
    category = data.get("category_suggestion", "")

    content = f"📄 {original_name}: {description}"
    if amount_pln > 0:
        content += f" — {amount_pln:.2f} {data.get('currency', 'PLN')}"
    if category:
        content += f" ({category})"

    item = InboxItem(
        user_id=user_id,
        content=content,
        source_type="document",
        target_type="transaction",
        agent_suggestion={
            "document_id": str(document_id),
            "extracted": data,
        },
        classified_by="openai",
    )
    db.add(item)
    await db.flush()
    return item
