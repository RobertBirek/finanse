from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.finance.imports.errors import ImportError
from app.finance.imports.valuation import freeze_exchange, freeze_quote
from app.finance.nbp_rates import NbpRateProvider


@pytest.mark.parametrize(
    "currency,amount,rate,base",
    [("EUR", 100, "4.25", 425), ("USD", 123, "3.9", 480), ("PLN", 100, "1", 100)],
)
async def test_explicit_quotes_are_exact_frozen_decimal_values(
    currency, amount, rate, base
) -> None:
    quote = await freeze_quote(currency, amount, date(2026, 1, 3), manual_rate=Decimal(rate))
    assert quote.rate == Decimal(rate) and quote.base_amount == base
    assert quote.requested_date == quote.effective_date == date(2026, 1, 3)
    with pytest.raises((AttributeError, TypeError)):
        quote.rate = Decimal(99)


async def test_historical_weekend_quote_uses_existing_nbp_fallback_and_keeps_effective_date(
    monkeypatch,
) -> None:
    urls = []

    async def response(self, url):
        urls.append(url)
        request = httpx.Request("GET", url)
        if "/2026-01-03/" in url and url.endswith("/USD/2026-01-03/"):
            raise httpx.HTTPStatusError(
                "missing weekend", request=request, response=httpx.Response(404, request=request)
            )
        return httpx.Response(
            200, request=request, json={"rates": [{"mid": 3.9, "effectiveDate": "2026-01-02"}]}
        )

    monkeypatch.setattr(NbpRateProvider, "_get_response", response)
    quote = await freeze_quote("USD", 100, date(2026, 1, 3))
    assert len(urls) == 2 and quote.rate == Decimal("3.9")
    assert quote.effective_date == date(2026, 1, 2) and quote.requested_date == date(2026, 1, 3)
    assert quote.source == "nbp_previous_business_day"


async def test_missing_quote_never_substitutes_today_or_one(monkeypatch) -> None:
    async def missing(self, currency, requested):
        return None

    monkeypatch.setattr(NbpRateProvider, "get_rate", missing)
    with pytest.raises(ImportError) as error:
        await freeze_quote("EUR", 100, date(2026, 1, 2))
    assert error.value.code == "fx_quote_missing"


@pytest.mark.parametrize(
    "rate",
    [
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal(0),
        Decimal(-1),
        Decimal("1.1234567"),
        Decimal(1000000),
    ],
)
async def test_invalid_or_unrepresentable_rates_cannot_enter_preview(rate) -> None:
    with pytest.raises(ImportError):
        await freeze_quote("EUR", 100, date(2026, 1, 2), manual_rate=rate)


async def test_actual_pln_leg_anchors_foreign_rate_without_http(monkeypatch) -> None:
    async def forbidden(*args):
        raise AssertionError("Actual PLN leg must not call NBP")

    monkeypatch.setattr(NbpRateProvider, "get_rate", forbidden)
    value = await freeze_exchange("PLN", 425, "EUR", 100, date(2026, 1, 2))
    assert value.base_pln == 425 and value.from_rate == 1 and value.to_rate == Decimal("4.25")
    assert value.to_source == "bank_actual_legs"


async def test_eur_usd_uses_outgoing_anchor_and_actual_implied_incoming_rate(monkeypatch) -> None:
    from app.finance.nbp_rates import NbpRate

    calls = []

    async def quote(self, currency, requested):
        calls.append(currency)
        return NbpRate(4.0, date(2026, 1, 2), "nbp")

    monkeypatch.setattr(NbpRateProvider, "get_rate", quote)
    value = await freeze_exchange("EUR", 100, "USD", 125, date(2026, 1, 2))
    assert calls == ["EUR"] and value.base_pln == 400
    assert value.from_rate == Decimal(4) and value.to_rate == Decimal("3.2")
    assert value.from_source == "nbp" and value.to_source == "bank_implied_cross"


async def test_implied_rate_that_loses_actual_leg_at_six_places_is_blocked() -> None:
    with pytest.raises(ImportError) as error:
        await freeze_exchange("PLN", 1, "EUR", 9007199254740991, date(2026, 1, 2))
    assert error.value.code == "fx_precision_unrepresentable"


@pytest.mark.parametrize(
    "out_currency,out_amount,in_currency,in_amount",
    [("PLN", 425, "EUR", 100), ("EUR", 100, "PLN", 425)],
)
async def test_manual_rate_cannot_silently_contradict_actual_pln_legs(
    out_currency, out_amount, in_currency, in_amount
) -> None:
    with pytest.raises(ImportError) as error:
        await freeze_exchange(
            out_currency,
            out_amount,
            in_currency,
            in_amount,
            date(2026, 1, 2),
            manual_rate=Decimal("4.1"),
        )
    assert error.value.code == "fx_manual_rate_conflict"
