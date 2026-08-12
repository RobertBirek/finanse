"""Tests for finance domain — double-entry ledger invariants."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.finance.schemas import PostingCreate
from app.finance.service import _validate_posting_sum
from app.main import app


class TestDoubleEntryInvariant:
    def test_valid_postings_sum_to_zero(self):
        """Debit and credit both use positive base_amount_pln — signs from direction."""
        acc1 = uuid.uuid4()
        acc2 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc2,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "expense")

    def test_invalid_postings_non_zero_raises(self):
        acc1 = uuid.uuid4()
        acc2 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc2,
                source_amount=49999,
                source_currency="PLN",
                base_amount_pln=49999,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        with pytest.raises(ValueError, match="must equal 0"):
            _validate_posting_sum(postings, "expense")

    def test_empty_postings_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            _validate_posting_sum([], "expense")

    def test_single_posting_raises(self):
        acc1 = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc1,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
        ]
        with pytest.raises(ValueError, match="must equal 0"):
            _validate_posting_sum(postings, "expense")

    def test_transfer_with_fee(self):
        """500 PLN transfer + 1 PLN fee = 3 postings, balanced."""
        acc_source = uuid.uuid4()
        acc_dest = uuid.uuid4()
        acc_fees = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc_source,
                source_amount=50000,
                source_currency="PLN",
                base_amount_pln=50000,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc_dest,
                source_amount=49900,
                source_currency="PLN",
                base_amount_pln=49900,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
            PostingCreate(
                account_id=acc_fees,
                source_amount=100,
                source_currency="PLN",
                base_amount_pln=100,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "transfer")

    def test_exchange_pln_to_eur(self):
        """100 EUR * 4.30 = 430 PLN. Debit PLN, credit EUR."""
        acc_pln = uuid.uuid4()
        acc_eur = uuid.uuid4()
        postings = [
            PostingCreate(
                account_id=acc_pln,
                source_amount=430,
                source_currency="PLN",
                base_amount_pln=430,
                fx_rate=4.30,
                fx_rate_source="manual",
                direction="debit",
            ),
            PostingCreate(
                account_id=acc_eur,
                source_amount=100,
                source_currency="EUR",
                base_amount_pln=430,
                fx_rate=4.30,
                fx_rate_source="manual",
                direction="credit",
            ),
        ]
        _validate_posting_sum(postings, "exchange")


class TestFinanceAPI:
    @pytest.mark.asyncio
    async def test_get_accounts_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/finance/accounts")
            assert response.status_code == 401
