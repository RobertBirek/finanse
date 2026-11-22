"""The category operator must retain new document references, still failing closed."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database import Base
from scripts import category_tree_guard as guard


def model_category_refs():
    return [
        (table.name, fk.parent.name)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.target_fullname == "categories.id"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", [False, True])
async def test_registered_document_category_ref_is_recognized_but_unknown_refs_block(unexpected):
    refs = model_category_refs()
    assert ("document_extraction_revisions", "suggested_category_id") in refs
    if unexpected:
        refs.append(("unknown_future_table", "category_id"))
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: refs)),
        scalar=AsyncMock(return_value=0),
    )
    result = await guard._integrity_blockers(db, uuid.uuid4(), [uuid.uuid4()])
    assert ("unregistered_category_reference" in result) is unexpected


@pytest.mark.asyncio
async def test_foreign_document_suggestion_reference_still_blocks():
    async def scalar(statement):
        return int("document_extraction_revisions" in str(statement))

    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=model_category_refs)),
        scalar=scalar,
    )
    result = await guard._integrity_blockers(db, uuid.uuid4(), [uuid.uuid4()])
    assert "foreign_reference" in result


@pytest.mark.asyncio
async def test_draft_registration_intents_are_retained_in_owner_snapshot():
    owner = uuid.uuid4()
    row = {"id": uuid.uuid4(), "user_id": owner, "state": "pending"}

    async def execute(statement):
        name = statement.get_final_froms()[0].name
        return SimpleNamespace(
            mappings=lambda: SimpleNamespace(
                all=lambda: [dict(row)] if name == "document_finance_draft_intents" else [],
            )
        )

    db = SimpleNamespace(execute=execute)
    plan = SimpleNamespace(patches=[], source=[])
    before, counts, _ = await guard._references(db, owner, plan)
    assert counts["document_finance_draft_intents"] == 1
    row["state"] = "succeeded"
    after, _, _ = await guard._references(db, owner, plan)
    assert after["document_finance_draft_intents"] != before["document_finance_draft_intents"]


@pytest.mark.asyncio
async def test_pending_finance_draft_registration_is_active_work():
    async def scalar(statement):
        return int("document_finance_draft_intents" in str(statement))

    db = SimpleNamespace(
        scalar=scalar,
        execute=AsyncMock(return_value=SimpleNamespace(first=lambda: None)),
    )
    counts = {name: 0 for name in guard._OWNER_TABLES | guard._GLOBAL_TABLES}
    result = await guard._work_blockers(db, uuid.uuid4(), counts)
    assert "active_work" in result


@pytest.mark.asyncio
async def test_queued_statement_auto_post_is_active_work():
    async def scalar(statement):
        return int("bank_import_auto_post_jobs" in str(statement))

    db = SimpleNamespace(
        scalar=scalar,
        execute=AsyncMock(return_value=SimpleNamespace(first=lambda: None)),
    )
    counts = {name: 0 for name in guard._OWNER_TABLES | guard._GLOBAL_TABLES}
    assert "active_work" in await guard._work_blockers(db, uuid.uuid4(), counts)


@pytest.mark.asyncio
async def test_configured_statement_categories_block_category_tree_apply():
    async def scalar(statement):
        return int("bank_import_auto_post_settings" in str(statement))

    db = SimpleNamespace(
        scalar=scalar,
        execute=AsyncMock(return_value=SimpleNamespace(first=lambda: None)),
    )
    counts = {name: 0 for name in guard._OWNER_TABLES | guard._GLOBAL_TABLES}
    assert "statement_auto_post_configured" in await guard._work_blockers(db, uuid.uuid4(), counts)
