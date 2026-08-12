import logging
from datetime import date

import httpx

logger = logging.getLogger(__name__)


NBP_API_BASE = "https://api.nbp.pl/api/exchangerates/rates/A"


class NbpRateProvider:
    def __init__(self):
        self._cache: dict[tuple[str, date], float] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def get_rate(self, currency: str, rate_date: date) -> float:
        if currency.upper() == "PLN":
            return 1.0

        cache_key = (currency.upper(), rate_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            date_str = rate_date.strftime("%Y-%m-%d")
            url = f"{NBP_API_BASE}/{currency.upper()}/{date_str}/"
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            rate = float(data["rates"][0]["mid"])
            self._cache[cache_key] = rate
            return rate
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            logger.warning("NBP rate unavailable: %s on %s: %s", currency, rate_date, e)
            return 0.0

    def calculate_base_amount(self, source_amount: int, fx_rate: float) -> int:
        if fx_rate <= 0:
            return source_amount
        return round(source_amount * fx_rate)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
