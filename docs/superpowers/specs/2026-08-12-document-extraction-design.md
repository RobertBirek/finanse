# Document Data Extraction with OpenAI — Design Spec

Data: 2026-08-12 | Status: approved

## Overview

After OCR extracts text from a document, OpenAI analyzes it to find structured financial data (amounts, dates, counterparties, categories) and creates an inbox item with a transaction suggestion. User processes the inbox item to create a real transaction.

## Flow

```
Upload → OCR → text
                   ↓
            Extraction (OpenAI)
                   ↓
            Inbox item with agent_suggestion
                   ↓
            User clicks "Utwórz transakcję" in Inbox
                   ↓
            Transaction created with suggested data
```

## OpenAI Prompt

Model: DeepSeek v4-pro (same as Advisor). Structured output: JSON with these fields:

```json
{
  "detected": true,
  "type": "expense|income",
  "amount": 5000,
  "currency": "PLN|EUR|USD",
  "description": "Biedronka — zakupy spożywcze",
  "date": "2026-08-10",
  "category_suggestion": "Jedzenie",
  "confidence": "high|medium|low"
}
```

If the document doesn't contain financial data, `detected: false`.

## Inbox Item

```python
inbox_item = InboxItem(
    user_id=doc.user_id,
    content=f"📄 {doc.original_name}: {data['description']} — {data['amount']/100:.2f} {data['currency']}",
    source_type="document",
    target_type="transaction",
    agent_suggestion=data,
    classified_by="openai",
)
```

## Implementation

### New file: `backend/app/documents/extractor.py`

```python
async def extract_financial_data(text: str) -> dict:
    """Send OCR text to OpenAI, return structured financial data."""
    # Prompt + OpenAI call + JSON parsing
```

### Modified: `backend/app/worker.py`

After OCR text extraction in `process_document`, add step:
```python
# Step 3: Extract financial data via OpenAI
data = await extract_financial_data(text)
if data.get("detected"):
    # Create inbox item
    await create_inbox_item(db, doc.user_id, doc, data)
```

### Modified: `backend/app/config.py`

No changes needed — LLM_API_KEY already available.

## Excluded

- Manual correction UI for extraction results
- Multi-document batch extraction
- Invoice-specific fields (VAT, NIP, invoice number)
- Learning from user corrections

## Files

| File | Action |
|------|--------|
| `backend/app/documents/extractor.py` | Create — OpenAI prompt + extraction logic |
| `backend/app/worker.py` | Modify — add extraction step after OCR |
