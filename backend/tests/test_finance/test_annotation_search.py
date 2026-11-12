"""User labels are discoverable without changing source-based categorization."""

import pytest
from sqlalchemy import event

from app.finance import service
from app.finance.schemas import TransactionSearch
from app.work.models import Project
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_annotations import context, edit, save
from tests.test_finance.test_categorization import setup
from tests.test_finance.test_transaction_search import seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_annotations_return_on_list_account_detail_search(db_session):
    owner, txn, account, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        result = await save(
            client,
            txn,
            edit(
                await context(client, txn),
                display_description="Własna nazwa",
                note="Szczegóły",
                tags=["Remont"],
            ),
        )
        assert result.status_code == 200
        paths = [
            ("/api/finance/transactions", False),
            (f"/api/finance/accounts/{account.id}/transactions", False),
            (f"/api/finance/transactions/{txn.id}", None),
            ("/api/finance/transactions/search", True),
        ]
        for path, search in paths:
            response = await client.get(path)
            assert response.status_code == 200, response.text
            item = (
                response.json()
                if search is None
                else (response.json()["items"][0] if search else response.json()[0])
            )
            assert item["effective_description"] == "Własna nazwa"
            assert item["description"] == txn.description
            assert item["annotations"]["note"] == "Szczegóły"
            assert item["annotations"]["tags"][0]["name"] == "Remont"


async def test_search_finds_source_and_overlay_without_duplicate_count(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    project = Project(user_id=owner, name="Qwerty projekt", status="completed")
    db_session.add(project)
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        result = await save(
            client,
            txn,
            edit(
                await context(client, txn),
                display_description="Qwerty title",
                note="Qwerty note 100%_",
                tags=["Qwerty tag", "Another"],
                project_id=str(project.id),
            ),
        )
        assert result.status_code == 200
        for term in [
            "Qwerty title",
            "Qwerty note",
            "Qwerty tag",
            "Qwerty projekt",
            "Qwerty",
            "100%_",
            txn.description,
        ]:
            response = await client.get(
                "/api/finance/transactions/search", params={"q": term, "limit": 1}
            )
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 1, (term, response.json())
            assert response.json()["items"][0]["id"] == str(txn.id)
        response = await client.get(
            "/api/finance/transactions/search", params={"q": "Qwerty", "offset": 1}
        )
        assert response.json()["total"] == 1 and response.json()["items"] == []


async def test_annotation_read_is_batched_and_owner_scoped(db_session):
    owner, first, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        assert (
            await save(client, first, edit(await context(client, first), note="One"))
        ).status_code == 200
    for index in range(7):
        await seed(db_session, owner, description=f"Other {index}")
    await db_session.commit()
    statements = []
    engine = db_session.bind.sync_engine

    def observe(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", observe)
    try:
        small = await service.get_transactions(db_session, owner, limit=1)
        small_count = len(statements)
        statements.clear()
        large = await service.get_transactions(db_session, owner, limit=20)
        large_count = len(statements)
        assert len(small) == 1 and len(large) == 8
        annotated = next(t for t in large if t.id == first.id)
        assert annotated.annotations.note == "One"
        assert large_count <= small_count + 1, (small_count, large_count)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    another, other, _, _, _ = await setup(db_session)
    assert another != owner
    async with client_for(db_session, another) as client:
        result = await save(
            client,
            other,
            edit(await context(client, other), note="Secret tag note", tags=["Secret"]),
        )
        assert result.status_code == 200
    found = await service.search_transactions(db_session, owner, TransactionSearch(q="Secret"))
    assert found.total == 0


async def test_source_rules_and_actual_replay_ignore_user_labels(db_session):
    from scripts.migrate_actual import check_idempotent
    from tests.test_finance.test_imported_categorization import imported

    owner, txn, _, _, _ = await imported(db_session)
    original = txn.description
    async with client_for(db_session, owner) as client:
        assert (
            await save(
                client,
                txn,
                edit(await context(client, txn), display_description="Overlay only", tags=["Mine"]),
            )
        ).status_code == 200
    current = await service.get_transaction(db_session, owner, txn.id)
    assert current.description == original
    assert current.effective_description == "Overlay only"
    assert await check_idempotent(db_session, owner, "category-edit-fixture") is True
