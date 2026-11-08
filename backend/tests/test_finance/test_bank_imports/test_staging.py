import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.imports.errors import ImportError
from app.finance.imports.service import create_batch, get_batch, list_rows
from app.identity.models import User
from tests.test_finance.test_bank_imports.factories import (
    ledger_snapshot,
    ready_statement,
    seed_legacy_transfer,
)
from tests.test_finance.test_bank_imports.test_contracts import parsed_statement

pytestmark = pytest.mark.integration


async def test_empty_batch_has_no_ledger_effect(db_session: AsyncSession, owner: User) -> None:
    await seed_legacy_transfer(db_session, owner.id)
    before = await ledger_snapshot(db_session)
    batch = await create_batch(db_session, owner.id, "statement")
    assert batch.version == 1 and batch.commit_state == "not_committed"
    assert batch.sources == [] and batch.unresolved_count == 0
    assert await ledger_snapshot(db_session) == before


async def test_batch_is_persisted_and_read_owner_scoped(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    batch = await create_batch(db_session, owner.id, "statement")
    owner_id, other_owner_id = owner.id, other_owner.id
    await db_session.commit()
    db_session.expire_all()
    restored = await get_batch(db_session, owner_id, batch.id)
    assert restored is not None and restored.id == batch.id
    assert restored.kind == "statement" and restored.version == 1
    assert await get_batch(db_session, other_owner_id, batch.id) is None
    assert await get_batch(db_session, owner_id, uuid.uuid4()) is None


async def test_schedule_batch_is_not_a_loan_creation(db_session: AsyncSession, owner: User) -> None:
    before = await ledger_snapshot(db_session)
    batch = await create_batch(db_session, owner.id, "loan_schedule")
    assert batch.kind == "loan_schedule" and batch.sources == []
    assert await ledger_snapshot(db_session) == before


async def test_foreign_batch_rows_are_not_an_empty_owned_result(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    batch = await create_batch(db_session, owner.id, "statement")
    with pytest.raises(ImportError) as error:
        await list_rows(db_session, other_owner.id, batch.id, source_id=None, offset=0, limit=10)
    assert error.value.http_status == 404


async def test_empty_owned_batch_has_stable_pagination(
    db_session: AsyncSession, owner: User
) -> None:
    batch = await create_batch(db_session, owner.id, "statement")
    page = await list_rows(db_session, owner.id, batch.id, source_id=None, offset=0, limit=10)
    assert page.items == [] and page.total == 0
    assert page.offset == 0 and page.limit == 10


@pytest.mark.parametrize("offset,limit", [(-1, 10), (0, 0), (0, -1)])
async def test_invalid_pagination_is_rejected(
    db_session: AsyncSession,
    owner: User,
    offset: int,
    limit: int,
) -> None:
    batch = await create_batch(db_session, owner.id, "statement")
    with pytest.raises(ImportError) as error:
        await list_rows(db_session, owner.id, batch.id, source_id=None, offset=offset, limit=limit)
    assert error.value.http_status == 422


async def test_ready_rows_keep_occurrence_order_and_typed_source_fields(
    db_session: AsyncSession,
    owner: User,
    other_owner: User,
) -> None:
    batch_id = await ready_statement(db_session, owner.id, parsed_statement())
    batch = await get_batch(db_session, owner.id, batch_id)
    assert batch is not None and batch.unresolved_count == 2
    assert len(batch.sources) == 1
    source = batch.sources[0]
    assert source.original_name == "synthetic.pdf" and source.validation_state == "passed"
    assert source.checks[0].actual == 800
    page = await list_rows(db_session, owner.id, batch_id, source_id=source.id, offset=1, limit=1)
    assert page.total == 2 and len(page.items) == 1
    item = page.items[0]
    assert item.source_key == "row-2" and item.bank_fields is not None
    assert item.bank_fields.balance_after == 800 and item.schedule_fields is None
    assert await get_batch(db_session, other_owner.id, batch_id) is None


async def test_source_filter_from_other_batch_is_not_silently_accepted(
    db_session: AsyncSession,
    owner: User,
) -> None:
    first = await ready_statement(db_session, owner.id, parsed_statement())
    second = await create_batch(db_session, owner.id, "statement")
    batch = await get_batch(db_session, owner.id, first)
    assert batch is not None
    with pytest.raises(ImportError) as error:
        await list_rows(
            db_session, owner.id, second.id, source_id=batch.sources[0].id, offset=0, limit=10
        )
    assert error.value.http_status == 404
