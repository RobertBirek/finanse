import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.manual_fx import transaction_fx_quote, valued_transaction
from app.finance.nbp_rates import NbpRateProvider
from app.finance.schemas import (
    AccountCreate,
    CategoryCreate,
    ManualFxTransactionCreate,
    TransactionCreate,
)
from app.finance.service import create_account, create_category
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bill_payments import create_owner


async def test_nbp_holiday_uses_previous_quote_and_caches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []
    day = date(2025, 12, 25)

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if len(requests) == 1:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "rates": [
                    {"mid": 4.25, "effectiveDate": "2025-12-23"},
                    {"mid": 4.30, "effectiveDate": "2025-12-24"},
                    {"mid": 9, "effectiveDate": "2025-12-25"},
                ]
            },
        )

    async def client(self: NbpRateProvider) -> httpx.AsyncClient:
        assert self._client is None
        self._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        return self._client

    async def reused_client(self: NbpRateProvider) -> httpx.AsyncClient:
        return self._client or await client(self)

    monkeypatch.setattr(NbpRateProvider, "_get_client", reused_client)
    quote = await transaction_fx_quote("EUR", day)
    assert quote is not None
    assert (quote.rate, quote.effective_date, quote.source) == (
        4.30,
        date(2025, 12, 24),
        "nbp_previous_business_day",
    )
    assert await transaction_fx_quote("EUR", day) == quote
    assert len(requests) == 2


def fx_payload(account_id: uuid.UUID, category_id: uuid.UUID) -> dict[str, object]:
    return {
        "type": "expense",
        "currency": "EUR",
        "account_id": str(account_id),
        "category_id": str(category_id),
        "amount_minor": 1234,
        "fx_rate": "4.25",
        "description": "Syntetyczny Revolut",
        "booking_date": "2026-01-05",
    }


@pytest.mark.parametrize(
    ("kind", "currency", "direction"), [("expense", "EUR", "debit"), ("income", "USD", "credit")]
)
async def test_manual_fx_values_both_postings_in_pln(
    kind: str, currency: str, direction: str
) -> None:
    data = ManualFxTransactionCreate.model_validate(
        {
            "type": kind,
            "currency": currency,
            "account_id": uuid.uuid4(),
            "category_id": uuid.uuid4(),
            "amount_minor": 1234,
            "fx_rate": Decimal("4.25"),
            "description": "Syntetyczny Revolut",
            "booking_date" if kind == "expense" else "transaction_date": date(2026, 1, 5),
        }
    )
    tx = await valued_transaction(data)
    account, category = tx.postings
    assert tx.type == kind and tx.source == "manual"
    assert account.account_id == data.account_id and category.category_id == data.category_id
    assert account.direction == direction and category.direction != direction
    assert all(
        x.source_amount == 1234
        and x.source_currency == currency
        and x.base_amount_pln == 5244
        and x.fx_rate_source == "manual"
        for x in tx.postings
    )


@pytest.mark.parametrize(
    "patch",
    [{"fx_rate": "4.1234567"}, {"fx_rate": "0"}, {"amount_minor": 1.5}, {"base_amount_pln": 100}],
)
def test_fx_intent_rejects_invalid_rate_or_client_valuation(patch: dict[str, object]) -> None:
    command = TypeAdapter(ManualFxTransactionCreate | TransactionCreate)
    with pytest.raises(ValidationError):
        command.validate_python(fx_payload(uuid.uuid4(), uuid.uuid4()) | patch)


@pytest.mark.integration
async def test_manual_fx_endpoint_keeps_wallet_currency_and_supports_replay(
    db_session: AsyncSession,
) -> None:
    owner = await create_owner(db_session)
    account = await create_account(
        db_session,
        owner,
        AccountCreate(name="Syntetyczny Revolut EUR", type="checking", currency="EUR"),
    )
    category = await create_category(
        db_session, owner, CategoryCreate(name="Wydatek syntetyczny", type="expense")
    )
    payload = fx_payload(account.id, category.id)
    async with client_for(db_session, owner) as client:
        first = await client.post(
            "/api/finance/transactions", json=payload, headers={"Idempotency-Key": "manual-fx-1"}
        )
        assert first.status_code == 201
        replay = await client.post(
            "/api/finance/transactions", json=payload, headers={"Idempotency-Key": "manual-fx-1"}
        )
        assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
        mismatch = await client.post(
            "/api/finance/transactions", json=payload | {"currency": "USD"}
        )
        assert mismatch.status_code == 422
    postings = first.json()["postings"]
    assert {x["direction"] for x in postings} == {"debit", "credit"}
    assert all(
        (x["source_amount"], x["source_currency"], x["base_amount_pln"]) == (1234, "EUR", 5244)
        for x in postings
    )
