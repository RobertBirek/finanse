"""Fast ledger guard checks which do not require a database."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.finance.schemas import PostingCreate, TransactionCreate
from app.finance.transaction_editor import _replace_canonical_ledger


async def test_unbalanced_editor_command_does_not_mutate_existing_postings() -> None:
    account_id, category_id = uuid.uuid4(), uuid.uuid4()
    postings = [
        SimpleNamespace(id=uuid.uuid4(), source_amount=100),
        SimpleNamespace(id=uuid.uuid4(), source_amount=100),
    ]
    transaction = SimpleNamespace(
        project_id=None, date_metadata=None, is_pending=False, postings=postings,
        description="Original", type="expense",
    )
    command = TransactionCreate(
        description="Changed",
        type="expense",
        postings=[
            PostingCreate(account_id=account_id, source_amount=200, base_amount_pln=200, direction="debit"),
            PostingCreate(category_id=category_id, source_amount=100, base_amount_pln=100, direction="credit"),
        ],
    )
    database = AsyncMock()
    with pytest.raises(ValueError, match="Sum of posting"):
        await _replace_canonical_ledger(
            database, uuid.uuid4(), transaction, command, allows_explicit_dates=False
        )
    assert [posting.source_amount for posting in postings] == [100, 100]
    assert transaction.description == "Original"
    database.flush.assert_not_awaited()
