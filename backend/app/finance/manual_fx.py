"""Value manual foreign expenses and income before using the ordinary ledger service."""

from datetime import date
from decimal import Decimal
from time import monotonic

from app.finance.dates import _local_today
from app.finance.imports.errors import ImportError
from app.finance.imports.valuation import base_amount, validated_rate
from app.finance.nbp_rates import NbpRate, NbpRateProvider
from app.finance.schemas import ManualFxTransactionCreate, PostingCreate, TransactionCreate

_quotes: dict[tuple[str, date], tuple[float, NbpRate]] = {}


async def transaction_fx_quote(currency: str, day: date) -> NbpRate | None:
    if currency not in {"EUR", "USD"} or day > _local_today():
        return None
    key = (currency, day)
    if (cached := _quotes.get(key)) and cached[0] > monotonic():
        return cached[1]
    provider = NbpRateProvider()
    try:
        rate = await provider.get_rate(currency, day, allow_previous_day=True)
    finally:
        await provider.close()
    if rate:
        try:
            validated_rate(Decimal(str(rate.rate)))
        except ImportError:
            return None
        if len(_quotes) >= 256:
            _quotes.pop(next(iter(_quotes)))
        _quotes[key] = (monotonic() + 300, rate)
    return rate


async def valued_transaction(data: ManualFxTransactionCreate) -> TransactionCreate:
    day = data.booking_date or data.transaction_date
    assert day is not None  # enforced by the command schema
    source_name = "manual"
    if data.fx_rate_source == "nbp":
        quote = await transaction_fx_quote(data.currency, day)
        if not quote or Decimal(str(quote.rate)) != data.fx_rate:
            raise ValueError(
                "Kurs NBP zmienił się lub jest niedostępny. Odśwież podgląd albo wpisz kurs ręcznie."
            )
        source_name = quote.source
    source = PostingCreate(
        account_id=data.account_id,
        source_amount=data.amount_minor,
        source_currency=data.currency,
        base_amount_pln=base_amount(data.amount_minor, data.fx_rate),
        fx_rate=float(data.fx_rate),
        fx_rate_source=source_name,
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
