"""Approved additive API contracts for the finance UI."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance import service
from app.finance.models import FinancialTransaction
from app.finance.schemas import (
    AccountCreate,
    AccountUpdate,
    CategoryBudgetCreate,
    CategoryCreate,
    CategoryUpdate,
    PostingCreate,
    TransactionCreate,
    TransactionSearch,
)


def _iban_with_checksum(country: str, bban: str) -> str:
    suffix = "".join(str(ord(char) - 55) for char in country) + "00"
    digits = "".join(char if char.isdigit() else str(ord(char) - 55) for char in bban)
    return f"{country}{98 - int(digits + suffix) % 97:02d}{bban}"


async def test_polish_iban_requires_numeric_bank_and_account_digits() -> None:
    with pytest.raises(ValidationError):
        AccountCreate(name="Bank", type="checking", iban=_iban_with_checksum("PL", "A" + "1" * 23))


@pytest.mark.parametrize(
    "value",
    [
        _iban_with_checksum("PL", "12345678901234567890123"),
        _iban_with_checksum("US", "12345678901234567890"),
    ],
)
async def test_iban_rejects_checksum_valid_unknown_country_or_wrong_country_length(
    value: str,
) -> None:
    with pytest.raises(ValidationError):
        AccountCreate(name="Bank", type="checking", iban=value)


async def test_summary_exposes_current_active_scope_balances_without_changing_period(
    db_session: AsyncSession,
) -> None:
    owner = uuid.uuid4()
    category = await service.create_category(
        db_session, owner, CategoryCreate(name="Spend", type="expense")
    )
    budget_account = await service.create_account(
        db_session, owner, AccountCreate(name="Budget", type="cash")
    )
    off_account = await service.create_account(
        db_session, owner, AccountCreate(name="Off", type="cash", is_budget_account=False)
    )
    await _expense(db_session, owner, budget_account.id, category.id, 200)
    await _expense(db_session, owner, off_account.id, category.id, 300)
    summary = await service.get_financial_summary(db_session, owner, month=8, year=2026)
    assert summary.balance_all_pln == -500
    assert summary.balance_budget_pln == -200


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _expense(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID, category_id: uuid.UUID, amount: int
) -> FinancialTransaction:
    return await service.create_transaction(
        db,
        user_id,
        TransactionCreate(
            transaction_date=date(2026, 8, 10),
            description="Expense",
            type="expense",
            postings=[
                PostingCreate(
                    account_id=account_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category_id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        ),
    )


async def test_account_metadata_normalizes_nrb_preserves_omitted_and_clears_null(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    account = await service.create_account(
        db_session,
        user_id,
        AccountCreate(
            name="Bank",
            type="checking",
            bank_name="Example Bank",
            account_holder="Owner",
            iban="61 1090 1014 0000 0712 1981 2874",
            bic="WBKPPLPP",
            notes="private",
        ),
    )
    assert account.iban == "PL61109010140000071219812874"
    await service.update_account(db_session, user_id, account.id, AccountUpdate(name="Renamed"))
    assert account.bank_name == "Example Bank"
    await service.update_account(
        db_session, user_id, account.id, AccountUpdate(bank_name=None, iban=None)
    )
    assert account.bank_name is None and account.iban is None


async def test_account_metadata_rejects_invalid_iban_and_bic() -> None:
    with pytest.raises(ValidationError):
        AccountCreate(name="Bank", type="checking", iban="PL00109010140000071219812874")
    with pytest.raises(ValidationError):
        AccountCreate(name="Bank", type="checking", bic="not valid")


async def test_account_balance_source_uses_source_currency_ledger_sign(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    account = await service.create_account(
        db_session, user_id, AccountCreate(name="EUR", type="checking", currency="EUR")
    )
    income = await service.create_category(
        db_session, user_id, CategoryCreate(name="Income", type="income")
    )
    await service.create_transaction(
        db_session,
        user_id,
        TransactionCreate(
            description="Income",
            type="income",
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=1_000,
                    source_currency="EUR",
                    base_amount_pln=4_000,
                    fx_rate=4,
                    direction="credit",
                ),
                PostingCreate(
                    category_id=income.id,
                    source_amount=1_000,
                    source_currency="EUR",
                    base_amount_pln=4_000,
                    fx_rate=4,
                    direction="debit",
                ),
            ],
        ),
    )
    found = await service.get_account(db_session, user_id, account.id)
    assert found is not None
    assert found.balance_pln == 4_000
    assert found.balance_source == 1_000


async def test_category_tree_rolls_up_deep_spend_and_includes_inactive_ancestor(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    account = await service.create_account(
        db_session, user_id, AccountCreate(name="Cash", type="cash")
    )
    root = await service.create_category(
        db_session, user_id, CategoryCreate(name="Root", type="expense")
    )
    child = await service.create_category(
        db_session, user_id, CategoryCreate(name="Child", type="expense", parent_id=root.id)
    )
    leaf = await service.create_category(
        db_session, user_id, CategoryCreate(name="Leaf", type="expense", parent_id=child.id)
    )
    await service.update_category(db_session, user_id, root.id, CategoryUpdate(is_active=False))
    await _expense(db_session, user_id, account.id, leaf.id, 500)
    summary = await service.get_category_summary(db_session, user_id, month=8, year=2026)
    assert len(summary.tree) == 1
    assert summary.tree[0].category_id == root.id
    assert summary.tree[0].total_pln == 500 and summary.tree[0].direct_total_pln == 0
    assert summary.tree[0].children[0].children[0].direct_total_pln == 500


async def test_descendant_search_and_budget_aggregate_do_not_double_count(
    db_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    account = await service.create_account(
        db_session, user_id, AccountCreate(name="Cash", type="cash")
    )
    parent = await service.create_category(
        db_session, user_id, CategoryCreate(name="Parent", type="expense")
    )
    child = await service.create_category(
        db_session, user_id, CategoryCreate(name="Child", type="expense", parent_id=parent.id)
    )
    sibling = await service.create_category(
        db_session, user_id, CategoryCreate(name="Sibling", type="expense")
    )
    txn = await _expense(db_session, user_id, account.id, child.id, 200)
    await service.create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=parent.id, amount_pln=1_000)
    )
    await service.create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=child.id, amount_pln=300)
    )
    await service.create_budget(
        db_session, user_id, CategoryBudgetCreate(category_id=sibling.id, amount_pln=400)
    )
    assert (
        await service.search_transactions(
            db_session, user_id, TransactionSearch(category_id=parent.id)
        )
    ).total == 0
    found = await service.search_transactions(
        db_session, user_id, TransactionSearch(category_id=parent.id, include_descendants=True)
    )
    assert found.total == 1 and found.items[0].id == txn.id
    status = await service.get_budget_status(db_session, user_id, month=8, year=2026)
    assert (status.total_budget_pln, status.total_spent_pln, status.remaining_pln) == (
        1_400,
        200,
        1_200,
    )


async def test_report_drilldown_keeps_same_budget_account_scope(db_session: AsyncSession) -> None:
    owner = uuid.uuid4()
    category = await service.create_category(
        db_session, owner, CategoryCreate(name="Food", type="expense")
    )
    budget_account = await service.create_account(
        db_session, owner, AccountCreate(name="Budget", type="cash")
    )
    off_account = await service.create_account(
        db_session, owner, AccountCreate(name="Off", type="cash", is_budget_account=False)
    )
    txn = await _expense(db_session, owner, budget_account.id, category.id, 200)
    await _expense(db_session, owner, off_account.id, category.id, 300)
    found = await service.search_transactions(
        db_session,
        owner,
        TransactionSearch(
            category_id=category.id, include_descendants=True, budget_accounts_only=True
        ),
    )
    assert found.total == 1
    assert found.items[0].id == txn.id
