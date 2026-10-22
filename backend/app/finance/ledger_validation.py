"""Ledger invariants shared by manual, scheduled, imported and AI transactions."""

import uuid
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.entities import SUPPORTED_CURRENCIES
from app.finance.models import Account, Category


def _validate_posting_sum(postings: list, txn_type: str) -> None:
    """Validate that sum of postings' base_amount_pln equals 0, respecting debit/credit signs."""
    total = 0
    for p in postings:
        signed_amount = p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
        total += signed_amount

    if total != 0:
        raise ValueError(
            f"Sum of posting base amounts must equal 0 (got {total}). "
            "Debits = Credits (double-entry accounting invariant)."
        )

    if txn_type in ("income", "expense") and len(postings) < 2:
        raise ValueError(
            "Income/expense transactions must have at least 2 postings (source + destination)"
        )

    if len(postings) < 2:
        raise ValueError("Transactions must have at least 2 postings")


async def _validate_transaction_postings(
    db: AsyncSession,
    user_id: uuid.UUID,
    postings: list,
    txn_type: str,
    *,
    allow_category_reversal: bool = False,
) -> None:
    account_ids = {posting.account_id for posting in postings if posting.account_id is not None}
    accounts: dict[uuid.UUID, Account] = {}
    if account_ids:
        account_result = await db.execute(
            select(Account).where(Account.user_id == user_id, Account.id.in_(account_ids))
        )
        accounts = {account.id: account for account in account_result.scalars().all()}

    category_ids = {posting.category_id for posting in postings if posting.category_id is not None}
    categories: dict[uuid.UUID, Category] = {}
    if category_ids:
        category_result = await db.execute(
            select(Category).where(Category.user_id == user_id, Category.id.in_(category_ids))
        )
        categories = {category.id: category for category in category_result.scalars().all()}

    for posting in postings:
        if posting.account_id is None and posting.category_id is None:
            raise ValueError("Posting must have at least an account or category")
        account = accounts.get(posting.account_id) if posting.account_id is not None else None
        if posting.account_id is not None and account is None:
            raise ValueError("Account not found")
        if account is not None and not account.is_active:
            raise ValueError("Account is inactive")
        category = categories.get(posting.category_id) if posting.category_id is not None else None
        if posting.category_id is not None and category is None:
            raise ValueError("Category not found")
        if category is not None and not category.is_active:
            raise ValueError("Category is inactive")

        source_currency = str(posting.source_currency).upper()
        if source_currency not in SUPPORTED_CURRENCIES:
            raise ValueError("Unsupported currency")
        if account is not None:
            account_currency = str(account.currency).upper()
            if account_currency not in SUPPORTED_CURRENCIES:
                raise ValueError("Unsupported currency")
            if source_currency != account_currency:
                raise ValueError(
                    f"Posting currency {source_currency} does not match account currency "
                    f"{account_currency}"
                )
        if posting.source_amount <= 0 or posting.base_amount_pln <= 0:
            raise ValueError("Posting amounts must be positive")
        if posting.fx_rate <= 0:
            raise ValueError("FX rate must be positive")

        if posting.account_id is not None and posting.category_id is not None:
            raise ValueError("Posting must reference either an account or a category, not both")
        rate = Decimal(str(posting.fx_rate))
        if not rate.is_finite() or rate <= 0 or rate >= Decimal(1000000):
            raise ValueError("FX rate must be finite, positive and fit the ledger precision")
        if rate != rate.quantize(Decimal("0.000001")):
            raise ValueError("FX rate must have at most 6 decimal places")
        if source_currency == "PLN":
            if rate != 1 or posting.source_amount != posting.base_amount_pln:
                raise ValueError("PLN posting must use rate 1 and identical source/base amounts")
        else:
            expected = int(
                (Decimal(posting.source_amount) * rate).quantize(
                    Decimal(1), rounding=ROUND_HALF_EVEN
                )
            )
            # A converted receipt is rounded to one foreign minor unit. Its PLN
            # book value may differ from revaluing that rounded receipt.
            exchange_rounding = txn_type == "exchange" and posting.source_amount == int(
                (Decimal(posting.base_amount_pln) / rate).quantize(
                    Decimal(1), rounding=ROUND_HALF_EVEN
                )
            )
            if posting.base_amount_pln != expected and not exchange_rounding:
                raise ValueError("Base amount does not match source amount and FX rate")

    if txn_type not in {"income", "expense"}:
        return

    account_side_postings = [
        posting
        for posting in postings
        if posting.account_id is not None and posting.category_id is None
    ]
    if len(account_side_postings) != 1:
        raise ValueError("Income/expense transactions require exactly one account-side posting")

    account_posting = account_side_postings[0]
    expected_direction = "credit" if txn_type == "income" else "debit"
    if account_posting.direction != expected_direction:
        raise ValueError("Account posting direction does not match transaction type")
    account = accounts[account_posting.account_id]
    for posting in postings:
        if posting.category_id is not None:
            category_type = categories[posting.category_id].type
            if category_type != txn_type and not (
                allow_category_reversal and category_type in {"income", "expense"}
            ):
                raise ValueError("Category type must match transaction type")
            if posting.direction == expected_direction:
                raise ValueError("Category posting must oppose the account posting")
            posting.is_budget_impact = account.is_budget_account
