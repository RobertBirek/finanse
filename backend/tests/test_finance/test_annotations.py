"""A descriptive correction must not become a ledger edit or a source rewrite."""

import uuid

import pytest
from sqlalchemy import delete, func, inspect, select

from app.audit.models import AuditEvent
from app.finance.annotation_models import FinanceTag, TransactionAnnotation
from app.finance.models import ActualImportMapping, FinanceCommandReceipt, Posting
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.suggestion_models import CategorizationSuggestionJob
from app.work.models import Project
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_categorization import columns, setup
from tests.test_finance.test_imported_categorization import imported, rows

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def annotation_path(txn):
    return f"/api/finance/transactions/{inspect(txn).identity[0]}/annotations"


async def context(client, txn):
    response = await client.get(annotation_path(txn))
    assert response.status_code == 200, response.text
    return response.json()


def edit(ctx, **changes):
    values = {key: ctx[key] for key in ["display_description", "note", "project_id"]}
    values.update(
        tags=[t["name"] for t in ctx["tags"]],
        expected_version=ctx["version"],
        expected_context_snapshot=ctx["context_snapshot"],
    )
    values.update(changes)
    return values


async def save(client, txn, data, key=None):
    return await client.put(
        annotation_path(txn), json=data, headers={"Idempotency-Key": key or uuid.uuid4().hex}
    )


async def test_import_annotation_preserves_original_payment_and_provenance(db_session):
    db = db_session
    owner, txn, _, _, _ = await imported(db)
    project = Project(user_id=owner, name="Remont", status="completed")
    db.add(project)
    await db.commit()
    original, postings, mappings = (
        columns(txn),
        await rows(db, Posting),
        await rows(db, ActualImportMapping),
    )
    async with client_for(db, owner) as client:
        ctx = await context(client, txn)
        assert ctx["version"] == 0 and ctx["tags"] == [] and ctx["display_description"] is None
        assert ctx["original_description"] == original["description"]
        assert await db.scalar(select(func.count()).select_from(TransactionAnnotation)) == 0
        result = await save(
            client,
            txn,
            edit(
                ctx,
                display_description="  Zakup do domu  ",
                note="Farba\nPokój",
                tags=[" Remont ", "remont", "Życie"],
                project_id=str(project.id),
            ),
        )
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["display_description"] == "Zakup do domu" and body["note"] == "Farba\nPokój"
        assert {t["name"] for t in body["tags"]} == {"Remont", "Życie"}
        assert body["project_id"] == str(project.id) and body["version"] == 1
    await db.refresh(txn)
    assert {k: v for k, v in columns(txn).items() if k not in {"updated_at", "project_id"}} == {
        k: v for k, v in original.items() if k not in {"updated_at", "project_id"}
    }
    assert await rows(db, Posting) == postings
    assert await rows(db, ActualImportMapping) == mappings
    for model in [TransactionRuleEvent, CategorizationSuggestionJob]:
        assert await db.scalar(select(func.count()).select_from(model)) == 0
    audit = await db.scalar(
        select(AuditEvent).where(AuditEvent.action == "update_transaction_annotations")
    )
    assert audit.old_state["version"] == 0 and audit.new_state["version"] == 1


@pytest.mark.parametrize(
    "kind",
    ["actual", "bank_import", "loan_payment", "fx", "refund", "transfer", "document_payment"],
)
async def test_annotation_allowed_for_protected_sources_without_ledger_authority(db_session, kind):
    owner, txn, _, _, _ = await setup(db_session)
    txn.source = kind if kind not in {"fx", "refund", "transfer"} else "manual"
    if kind == "transfer":
        txn.type = "transfer"
    if kind == "fx":
        for p in txn.postings:
            p.source_currency = "EUR"
    if kind == "refund":
        for p in txn.postings:
            p.direction = "credit" if p.account_id else "debit"
    await db_session.commit()
    postings = await rows(db_session, Posting)
    async with client_for(db_session, owner) as client:
        ctx = await context(client, txn)
        result = await save(client, txn, edit(ctx, note="Only a note"))
        assert result.status_code == 200, result.text
        if kind != "document_payment":
            category = await client.get(f"/api/finance/transactions/{txn.id}/categorization")
            if kind in {"loan_payment", "fx", "refund", "transfer"}:
                assert category.json()["eligibility"]["allowed"] is False
    assert await rows(db_session, Posting) == postings


async def test_annotation_clearing_restores_original_title(db_session):
    owner, txn, _, _, _ = await imported(db_session)
    original = txn.description
    async with client_for(db_session, owner) as client:
        first = await save(
            client,
            txn,
            edit(
                await context(client, txn), display_description="My title", note="Keep", tags=["x"]
            ),
        )
        assert first.status_code == 200
        cleared = await save(
            client, txn, edit(first.json(), display_description="  ", note="", tags=[])
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["display_description"] is None and cleared.json()["tags"] == []
        assert cleared.json()["original_description"] == original
        assert cleared.json()["version"] == 2
        noop = await save(client, txn, edit(cleared.json()))
        assert noop.json()["version"] == 2
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "update_transaction_annotations")
        )
        == 2
    )


async def test_annotation_validation_rolls_back_new_tags(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        ctx = await context(client, txn)
        for changes in [
            {"note": "x" * 5001},
            {"tags": ["x" * 61]},
            {"tags": [""]},
            {"note": "NUL\0text"},
            {"source": "manual"},
            {"amount_minor": 100},
            {"tags": ["new"], "project_id": str(uuid.uuid4())},
        ]:
            result = await save(client, txn, edit(ctx, **changes))
            assert result.status_code == 422, result.text
    assert await db_session.scalar(select(func.count()).select_from(FinanceTag)) == 0
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


async def test_duplicate_retry_returns_receipt_without_rewriting_newer_annotation(db_session):
    owner, txn, _, _, _ = await imported(db_session)
    async with client_for(db_session, owner) as client:
        data = edit(await context(client, txn), note="first")
        first = await save(client, txn, data, "first")
        assert first.status_code == 200
        second = await save(client, txn, edit(first.json(), note="second"), "second")
        assert second.status_code == 200
        replay = await save(client, txn, data, "first")
        assert replay.json() == first.json()
        assert (await context(client, txn))["note"] == "second"
        conflict = await save(client, txn, {**data, "note": "different"}, "first")
        assert conflict.status_code == 409


async def test_stale_annotation_rejected_without_partial_write(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        ctx = await context(client, txn)
        assert (await save(client, txn, edit(ctx, note="winner"))).status_code == 200
        rejected = await save(client, txn, edit(ctx, note="loser", tags=["must not exist"]))
        assert rejected.status_code == 409
        assert (await context(client, txn))["note"] == "winner"
    assert await db_session.scalar(select(func.count()).select_from(FinanceTag)) == 0


async def test_project_deleted_after_open_conflicts(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    project = Project(user_id=owner, name="Old")
    db_session.add(project)
    await db_session.flush()
    txn.project_id = project.id
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        ctx = await context(client, txn)
        await db_session.execute(delete(Project).where(Project.id == project.id))
        await db_session.commit()
        result = await save(client, txn, edit(ctx, project_id=None, note="stale"))
        assert result.status_code == 409, result.text


async def test_foreign_tags_and_project_are_invisible(db_session):
    owner, txn, _, _, _ = await setup(db_session)
    other = uuid.uuid4()
    tag = FinanceTag(user_id=other, name="private", normalized_name="private")
    project = Project(user_id=other, name="private")
    db_session.add_all([tag, project])
    await db_session.commit()
    async with client_for(db_session, owner) as client:
        listed = await client.get("/api/finance/tags?q=private")
        assert listed.status_code == 200 and listed.json() == []
        ctx = await context(client, txn)
        rejected = await save(client, txn, edit(ctx, tags=["new"], project_id=str(project.id)))
        assert rejected.status_code == 422
        result = await save(client, txn, edit(await context(client, txn), tags=["private"]))
        assert result.status_code == 200, result.text
        assert result.json()["tags"][0]["id"] != str(inspect(tag).identity[0])
    async with client_for(db_session, other) as client:
        assert (await client.get(annotation_path(txn))).status_code == 404


@pytest.mark.parametrize("source", ["actual", "bank_import"])
async def test_legacy_patch_cannot_rewrite_imported_original_description(db_session, source):
    owner, txn, _, _, _ = await imported(db_session, source)
    async with client_for(db_session, owner) as client:
        response = await client.patch(
            f"/api/finance/transactions/{txn.id}", json={"description": "overwrite source"}
        )
        assert response.status_code in {400, 409, 422}, response.text
