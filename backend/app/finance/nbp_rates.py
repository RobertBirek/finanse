import logging
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)


NBP_API_BASE = "https://api.nbp.pl/api/exchangerates/rates/A"


@dataclass(frozen=True)
class NbpRate:
    rate: float
    effective_date: date
    source: str


class NbpRateProvider:
    def __init__(self):
        self._cache: dict[tuple[str, date], NbpRate] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def get_rate(self, currency: str, rate_date: date) -> NbpRate | None:
        currency = currency.upper()
        if currency == "PLN":
            return NbpRate(rate=1.0, effective_date=rate_date, source="manual")

        cache_key = (currency, rate_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            response = await self._get_response(f"{NBP_API_BASE}/{currency}/{rate_date}/")
            quote = self._parse_rate(response, "nbp", expected_date=rate_date)
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 404 or rate_date.weekday() not in (5, 6):
                logger.warning("NBP rate unavailable: %s on %s: %s", currency, rate_date, error)
                return None
            fallback_quote = await self._get_previous_business_day_rate(currency, rate_date)
            if fallback_quote is None:
                return None
            quote = fallback_quote
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as error:
            logger.warning("NBP rate unavailable: %s on %s: %s", currency, rate_date, error)
            return None

        self._cache[cache_key] = quote
        return quote

    async def _get_response(self, url: str) -> httpx.Response:
        client = await self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response

    async def _get_previous_business_day_rate(
        self, currency: str, rate_date: date
    ) -> NbpRate | None:
        try:
            range_start = rate_date - timedelta(days=7)
            response = await self._get_response(
                f"{NBP_API_BASE}/{currency}/{range_start}/{rate_date}/"
            )
            return self._parse_rate(response, "nbp_previous_business_day", before=rate_date)
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as error:
            logger.warning(
                "NBP fallback rate unavailable: %s on %s: %s", currency, rate_date, error
            )
            return None

    @staticmethod
    def _parse_rate(
        response: httpx.Response,
        source: str,
        *,
        expected_date: date | None = None,
        before: date | None = None,
    ) -> NbpRate:
        data = response.json()
        rates = [
            NbpRate(
                rate=float(rate["mid"]),
                effective_date=date.fromisoformat(rate["effectiveDate"]),
                source=source,
            )
            for rate in data["rates"]
        ]
        if expected_date is not None:
            rates = [rate for rate in rates if rate.effective_date == expected_date]
        if before is not None:
            rates = [rate for rate in rates if rate.effective_date < before]
        if not rates:
            raise ValueError("NBP response has no usable rate")
        quote = max(rates, key=lambda rate: rate.effective_date)
        if quote.rate <= 0:
            raise ValueError("NBP response has a non-positive rate")
        return quote

    def calculate_base_amount(self, source_amount: int, fx_rate: float) -> int:
        if fx_rate <= 0:
            return source_amount
        return round(source_amount * fx_rate)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
