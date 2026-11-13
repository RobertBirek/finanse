"""Gift totals must not be ledger totals or page totals."""

import pytest

from tests.test_finance.test_people import gift, link, person

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_person_summary_counts_each_gift_once_across_pages_and_currencies(db_session):
    from app.finance.person_reads import get_person_gifts, get_person_summary

    owner, first, _, _ = await gift(db_session)
    _, second, _, _ = await gift(db_session, owner=owner, currency="EUR", amount=20000, base=90000)
    p = await person(db_session, owner)
    await link(db_session, owner, first.id, p.id)
    await link(db_session, owner, second.id, p.id)
    from app.finance.annotation_models import FinanceTag, TransactionTag

    for name in ["Gift", "Family"]:
        tag = FinanceTag(user_id=owner, name=name, normalized_name=name.lower())
        db_session.add(tag)
        await db_session.flush()
        db_session.add(TransactionTag(user_id=owner, transaction_id=first.id, tag_id=tag.id))
    await db_session.flush()
    summary = await get_person_summary(db_session, owner, p.id)
    assert summary.gift_count == 2 and summary.received_gifts_pln == 100000
    assert summary.received_by_currency == {"PLN": 10000, "EUR": 20000}
    first_page = await get_person_gifts(db_session, owner, p.id, limit=1)
    second_page = await get_person_gifts(db_session, owner, p.id, limit=1, offset=1)
    assert first_page.total == second_page.total == 2
    assert len(first_page.items) == len(second_page.items) == 1
    assert first_page.items[0].id != second_page.items[0].id


async def test_person_empty_archive_and_navigation_filter(db_session):
    from app.finance import service
    from app.finance.people import update_person
    from app.finance.person_reads import get_person_summary, list_people
    from app.finance.person_schemas import PersonUpdate
    from app.finance.schemas import AccountCreate

    owner, _, _, _ = await gift(db_session)
    ref = await service.create_account(
        db_session, owner, AccountCreate(name="Reference", type="checking", is_budget_account=False)
    )
    p = await person(db_session, owner, reference_account_id=ref.id)
    empty = await get_person_summary(db_session, owner, p.id)
    assert (
        empty.gift_count == 0 and empty.received_gifts_pln == 0 and empty.received_by_currency == {}
    )
    assert (await list_people(db_session, owner, reference_account_id=ref.id)).total == 1
    await update_person(db_session, owner, p.id, PersonUpdate(expected_version=1, is_active=False))
    assert (await list_people(db_session, owner)).total == 0
    assert (await list_people(db_session, owner, include_archived=True)).total == 1
    assert await get_person_summary(db_session, owner, p.id) == empty
