"""Offline orchestration tests; storage and transport are boundary fakes."""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.documents.category_catalog import CategoryCatalog
from app.documents.review_schemas import ReviewSuggestion
from app.documents.vision_schemas import VisionExtraction


def scalar(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


@pytest.mark.asyncio
async def test_review_can_read_exact_pinned_revision_without_reextracting():
    from app.documents.review_service import get_review

    owner, doc_id, revision_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    db = SimpleNamespace(execute=AsyncMock(return_value=scalar(None)))
    assert await get_review(db, owner, doc_id, revision_id=revision_id) is None
    query = db.execute.call_args.args[0]
    assert revision_id in query.compile().params.values()


@pytest.mark.parametrize("result", ["matched", "no_match", "foreign_revision", "archived"])
@pytest.mark.asyncio
async def test_explicit_category_request_uses_the_owned_saved_read_without_creating_work(
    monkeypatch, result
):
    from app.database import get_db
    from app.documents import extractor, review_router
    from app.identity.router import get_current_user

    owner, doc_id, revision_id, category_id = (uuid.uuid4() for _ in range(4))
    document = SimpleNamespace(
        id=doc_id,
        user_id=owner,
        processing_method="legacy_ocr",
        archived_at="archived" if result == "archived" else None,
    )
    revision = SimpleNamespace(
        id=revision_id,
        document_id=doc_id,
        revision=2,
        status="ready",
        data={
            "document_type": "invoice",
            "fields": {
                "supplier_name": "  Dostawca  ",
                "description": "Internet domowy",
                "total": "39.99",
                "currency": "PLN",
            },
            "provenance": {},
        },
        error_code=None,
        suggested_category_id=None,
        input_method="text",
        warnings=[],
    )
    category = SimpleNamespace(
        id=category_id,
        user_id=owner,
        type="expense",
        is_active=True,
        source="manual",
        parent_id=None,
        name="Internet",
    )
    categories = SimpleNamespace(scalars=lambda: [category])
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                scalar(document),
                scalar(None if result == "foreign_revision" else revision),
                categories,
                categories,
            ]
        ),
        scalar=AsyncMock(return_value=None),
        commit=AsyncMock(),
    )
    provider = AsyncMock(return_value=None if result == "no_match" else "c01")
    monkeypatch.setattr(extractor, "suggest_category_from_review", provider)
    app = FastAPI()
    app.include_router(review_router.router, prefix="/api/documents")
    app.dependency_overrides.update(
        {
            get_current_user: lambda: SimpleNamespace(id=owner),
            get_db: lambda: db,
            review_router.processing_action_rate_limit: lambda: None,
        }
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test.invalid"
    ) as client:
        response = await client.post(
            f"/api/documents/{doc_id}/review/category-suggestion",
            params={"revision_id": revision_id},
        )

    if result in {"archived", "foreign_revision"}:
        assert response.status_code == (409 if result == "archived" else 404)
        provider.assert_not_awaited()
        db.commit.assert_not_awaited()
        return
    assert response.status_code == 200
    assert response.json() == {
        "suggested_category_id": str(category_id) if result == "matched" else None
    }
    provider.assert_awaited_once_with(
        supplier="Dostawca",
        description="Internet domowy",
        catalog=[{"key": "c01", "path": "Internet"}],
    )
    db.commit.assert_awaited_once()
    document_query, review_query = (call.args[0] for call in db.execute.call_args_list[:2])
    assert set(document_query.compile().params.values()) == {doc_id, owner}
    assert {doc_id, owner, revision_id} <= set(review_query.compile().params.values())


@pytest.mark.asyncio
async def test_text_pipeline_publishes_revalidated_category_without_second_extraction(monkeypatch):
    from app.documents import category_catalog, extractor, review_service

    owner, doc_id, category_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    revision = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=owner,
        document_id=doc_id,
        status="pending",
        warnings=[],
        suggested_category_id=None,
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=revision),
        scalar=AsyncMock(return_value=SimpleNamespace(archived_at=None, user_id=owner)),
        execute=AsyncMock(
            side_effect=[scalar(revision), scalar(SimpleNamespace(extracted_text="synthetic"))]
        ),
    )
    packet = CategoryCatalog([{"key": "c01", "path": "Mobile"}], {"c01": category_id})
    monkeypatch.setattr(
        category_catalog, "load_document_category_catalog", AsyncMock(return_value=packet)
    )
    monkeypatch.setattr(category_catalog, "resolve_category", AsyncMock(return_value=category_id))
    extraction = VisionExtraction(
        suggestion=ReviewSuggestion(
            document_type="invoice", fields={"total": "1.23", "currency": "PLN"}, provenance={}
        ),
        warnings=(),
        ready=True,
        category_key="c01",
    )
    enriched = AsyncMock(return_value=extraction)
    legacy = AsyncMock()
    monkeypatch.setattr(extractor, "extract_review_with_categories", enriched)
    monkeypatch.setattr(review_service, "extract_review_data", legacy)
    result = await review_service.process_review_revision(db, revision.id)
    assert result.suggested_category_id == category_id
    assert result.data["total_minor"] == 123
    assert result.status == "ready"
    legacy.assert_not_awaited()
    assert enriched.await_count == 1


@pytest.mark.asyncio
async def test_dispatch_only_delivers_durable_ids_and_processor_commits(monkeypatch):
    from app import worker
    from app.documents import finance_drafts

    intent_id = uuid.uuid4()
    db = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(worker, "async_session_factory", session)
    monkeypatch.setattr(
        finance_drafts, "pending_finance_draft_ids", AsyncMock(return_value=[intent_id])
    )
    prepare = AsyncMock(return_value="succeeded")
    monkeypatch.setattr(finance_drafts, "prepare_pending_finance_draft", prepare)
    redis = SimpleNamespace(enqueue_job=AsyncMock())
    await worker.dispatch_finance_drafts({"redis": redis})
    name, delivered = redis.enqueue_job.call_args.args
    assert name == "prepare_document_finance_draft"
    assert delivered == str(intent_id)
    await worker.prepare_document_finance_draft({}, delivered)
    prepare.assert_awaited_once_with(db, intent_id)
    assert db.commit.await_count >= 1


@pytest.mark.asyncio
async def test_image_publication_resolves_alias_inside_lease_checked_transaction(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from app.documents import job_service
    from app.documents.job_service import JobClaim, JobOutcome
    from app.documents.vision_config import VisionConfig

    now = datetime.now(UTC)
    owner, doc_id, revision_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    config = VisionConfig("test", "https://example.test", "model", "secret", "p", "s")
    claim = JobClaim(uuid.uuid4(), owner, doc_id, revision_id, "vision", uuid.uuid4(), 1, 1)
    revision = SimpleNamespace(id=revision_id, suggested_category_id=None)
    document = SimpleNamespace(id=doc_id, user_id=owner, archived_at=None)
    job = SimpleNamespace(
        state="processing",
        lease_token=claim.lease_token,
        lease_expires_at=now + timedelta(seconds=60),
        policy_epoch=1,
    )
    policy = SimpleNamespace(
        enabled=True, epoch=1, configuration_fingerprint=config.configuration_fingerprint
    )
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[scalar(document), scalar(job), scalar(revision), scalar(revision_id)]
        )
    )
    monkeypatch.setattr(job_service, "_admission_lock", AsyncMock())
    monkeypatch.setattr(job_service, "_locked_policy", AsyncMock(return_value=policy))
    monkeypatch.setattr(job_service, "get_vision_config", lambda _: config)
    monkeypatch.setattr(job_service.settings, "DOCUMENT_VISION_ENABLED", True)
    category_id = uuid.uuid4()
    monkeypatch.setattr(job_service, "resolve_category", AsyncMock(return_value=category_id))
    outcome = JobOutcome(
        suggestion=ReviewSuggestion(document_type="receipt", fields={}, provenance={}),
        category_catalog=CategoryCatalog(),
        category_key="c01",
    )
    assert await job_service.finish_processing_job(db, claim, outcome, now=now)
    assert revision.suggested_category_id == category_id
