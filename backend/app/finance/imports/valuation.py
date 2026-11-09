"""Frozen historical quotes and actual-leg FX valuations; all arithmetic is Decimal."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from app.finance.imports.contracts import MAX_MINOR_UNITS
from app.finance.imports.errors import ImportError
from app.finance.nbp_rates import NbpRateProvider


@dataclass(frozen=True)
class FrozenQuote:
    currency: str
    requested_date: date
    effective_date: date
    rate: Decimal
    source: str
    base_amount: int


@dataclass(frozen=True)
class ExchangeValuation:
    base_pln: int
    from_rate: Decimal
    to_rate: Decimal
    from_source: str
    to_source: str
    quote_date: date


def validated_rate(rate: Decimal) -> Decimal:
    try:
        if (
            not rate.is_finite()
            or not 0 < rate < 1000000
            or rate != rate.quantize(Decimal("0.000001"))
        ):
            raise ValueError("invalid rate")
    except (InvalidOperation, ValueError) as error:
        raise ImportError(
            "fx_rate_invalid", "Kurs nie mieści się w precyzji księgi.", 422
        ) from error
    return rate


def base_amount(amount: int, rate: Decimal) -> int:
    if type(amount) is not int or not 0 < amount <= MAX_MINOR_UNITS:
        raise ImportError("fx_amount_invalid", "Wycena wymaga dodatniej rzeczywistej kwoty.", 422)
    value = int(
        (Decimal(amount) * validated_rate(rate)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    )
    if not 0 < value <= MAX_MINOR_UNITS:
        raise ImportError(
            "fx_amount_invalid", "Wycena przekracza zakres księgi lub zaokrągla się do zera.", 422
        )
    return value


async def freeze_quote(
    currency: str, amount: int, requested_date: date, *, manual_rate: Decimal | None = None
) -> FrozenQuote:
    if currency not in {"PLN", "EUR", "USD"}:
        raise ImportError("currency_unsupported", "Nieobsługiwana waluta.", 422)
    effective = requested_date
    source = "manual"
    if currency == "PLN":
        if manual_rate is not None and manual_rate != 1:
            raise ImportError("fx_rate_invalid", "PLN wymaga kursu 1.", 422)
        rate = Decimal(1)
        source = "pln"
    elif manual_rate is not None:
        rate = validated_rate(manual_rate)
    else:
        provider = NbpRateProvider()
        try:
            quote = await provider.get_rate(currency, requested_date)
        finally:
            await provider.close()
        if quote is None:
            raise ImportError(
                "fx_quote_missing", "Brak historycznego kursu; uzupełnij go jawnie.", 422
            )
        rate = validated_rate(Decimal(str(quote.rate)))
        effective, source = quote.effective_date, quote.source
    return FrozenQuote(currency, requested_date, effective, rate, source, base_amount(amount, rate))


def _implied(base: int, amount: int) -> Decimal:
    if type(amount) is not int or not 0 < amount <= MAX_MINOR_UNITS:
        raise ImportError("fx_amount_invalid", "Brak pełnej rzeczywistej nogi wymiany.", 422)
    rate = (Decimal(base) / amount).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    if rate <= 0 or rate >= 1000000:
        raise ImportError(
            "fx_precision_unrepresentable",
            "Rzeczywistej nogi nie można zachować przy precyzji księgi.",
            422,
        )
    forward = int((Decimal(amount) * rate).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    reverse = int((Decimal(base) / rate).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    if forward != base and reverse != amount:
        raise ImportError(
            "fx_precision_unrepresentable",
            "Rzeczywistej nogi nie można zachować przy precyzji księgi.",
            422,
        )
    return rate


async def freeze_exchange(
    from_currency: str,
    from_amount: int,
    to_currency: str,
    to_amount: int,
    booking_date: date,
    *,
    manual_rate: Decimal | None = None,
) -> ExchangeValuation:
    if from_currency == to_currency or {from_currency, to_currency} - {"PLN", "EUR", "USD"}:
        raise ImportError(
            "fx_pair_invalid", "Wymiana wymaga dwóch różnych obsługiwanych walut.", 422
        )
    if any(
        type(amount) is not int or not 0 < amount <= MAX_MINOR_UNITS
        for amount in (from_amount, to_amount)
    ):
        raise ImportError("fx_amount_invalid", "Wymiana wymaga obu rzeczywistych kwot.", 422)
    if from_currency == "PLN":
        rate = _implied(from_amount, to_amount)
        if manual_rate is not None and validated_rate(manual_rate) != rate:
            raise ImportError(
                "fx_manual_rate_conflict",
                "Kurs ręczny jest sprzeczny z rzeczywistymi nogami bankowymi.",
                422,
            )
        return ExchangeValuation(
            from_amount,
            Decimal(1),
            rate,
            "pln",
            "bank_actual_legs",
            booking_date,
        )
    if to_currency == "PLN":
        rate = _implied(to_amount, from_amount)
        if manual_rate is not None and validated_rate(manual_rate) != rate:
            raise ImportError(
                "fx_manual_rate_conflict",
                "Kurs ręczny jest sprzeczny z rzeczywistymi nogami bankowymi.",
                422,
            )
        return ExchangeValuation(
            to_amount,
            rate,
            Decimal(1),
            "bank_actual_legs",
            "pln",
            booking_date,
        )
    quote = await freeze_quote(from_currency, from_amount, booking_date, manual_rate=manual_rate)
    return ExchangeValuation(
        quote.base_amount,
        quote.rate,
        _implied(quote.base_amount, to_amount),
        quote.source,
        "bank_implied_cross",
        quote.effective_date,
    )
