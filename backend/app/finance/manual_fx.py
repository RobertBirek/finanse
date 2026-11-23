"""Value manual foreign expenses and income before using the ordinary ledger service."""

from app.finance.imports.valuation import freeze_quote
from app.finance.schemas import ManualFxTransactionCreate, PostingCreate, TransactionCreate


async def valued_transaction(data: ManualFxTransactionCreate) -> TransactionCreate:
    day = data.booking_date or data.transaction_date
    assert day is not None  # enforced by the command schema
    quote = await freeze_quote(data.currency, data.amount_minor, day, manual_rate=data.fx_rate)
    source = PostingCreate(
        account_id=data.account_id,
        source_amount=data.amount_minor,
        source_currency=data.currency,
        base_amount_pln=quote.base_amount,
        fx_rate=float(quote.rate),
        fx_rate_source=quote.source,
        direction="debit" if data.type == "expense" else "credit",
    )
    category = source.model_copy(
        update={
            "account_id": None,
            "category_id": data.category_id,
            "direction": "credit" if data.type == "expense" else "debit",
        }
    )
    return TransactionCreate(
        type=data.type,
        description=data.description,
        transaction_date=data.transaction_date,
        purchase_date=data.purchase_date,
        booking_date=data.booking_date,
        postings=[source, category],
    )
