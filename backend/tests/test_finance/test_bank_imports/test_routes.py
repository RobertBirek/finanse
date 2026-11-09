import uuid

import pytest
from sqlalchemy import func, select

from app.finance.models import FinancialTransaction
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_bank_imports.commit_fixtures import confirmed_import
from tests.test_finance.test_bank_imports.factories import text_pdf_bytes

pytestmark = pytest.mark.integration
ROOT = "/api/finance/imports"


async def test_import_upload_body_is_bounded_before_multipart_parsing(async_client):
    from app.config import settings

    response = await async_client.post(
        f"{ROOT}/{uuid.uuid4()}/sources",
        headers={"Content-Length": str(settings.DOCUMENT_MAX_BODY_BYTES + 1)},
        content=b"x",
    )
    assert response.status_code == 413


async def test_import_routes_require_authentication_and_existing_csrf_policy(
    async_client, db_session, owner, monkeypatch
):
    from app.config import settings
    from app.identity.service import create_session

    assert (await async_client.get(ROOT)).status_code == 401
    # Like the application's CSRF integration tests, enable the production policy.
    # A default development environment deliberately returns before CSRF checks.
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", ("https://app.example.test",))
    async_client.cookies.set("advisor_session", "synthetic-not-a-live-session")
    response = await async_client.post(
        ROOT,
        json={"kind": "statement"},
        headers={"Idempotency-Key": "unauthorized", "Origin": "https://foreign.example.test"},
    )
    assert response.status_code == 403
    session_token, csrf_token, _session = await create_session(db_session, owner.id)
    async_client.cookies.set("advisor_session", session_token)
    async_client.cookies.set("advisor_csrf", csrf_token)
    trusted = {"Idempotency-Key": "real-auth", "Origin": "https://app.example.test"}
    assert (
        await async_client.post(ROOT, json={"kind": "statement"}, headers=trusted)
    ).status_code == 403
    accepted = await async_client.post(
        ROOT, json={"kind": "statement"}, headers=trusted | {"X-CSRF-Token": csrf_token}
    )
    assert accepted.status_code == 201


async def test_create_and_list_imports_are_durable_owner_scoped_and_idempotent(
    db_session, owner, other_owner
):
    async with client_for(db_session, owner.id) as client:
        assert (await client.post(ROOT, json={"kind": "statement"})).status_code == 422
        headers = {"Idempotency-Key": "create-once"}
        first = await client.post(ROOT, json={"kind": "statement"}, headers=headers)
        assert first.status_code == 201
        again = await client.post(ROOT, json={"kind": "statement"}, headers=headers)
        assert first.json() == again.json()
        batch_id = first.json()["id"]
        conflict = await client.post(ROOT, json={"kind": "loan_schedule"}, headers=headers)
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_key_reused"
        listing = await client.get(ROOT)
        assert [item["id"] for item in listing.json()] == [batch_id]
        assert (await client.get(f"{ROOT}/{batch_id}")).status_code == 200
    async with client_for(db_session, other_owner.id) as client:
        assert (await client.get(ROOT)).json() == []
        assert (await client.get(f"{ROOT}/{batch_id}")).status_code == 404


async def test_upload_saves_original_and_replay_never_creates_financial_effects(
    db_session, owner, tmp_path, monkeypatch
):
    from app.documents import service as documents

    monkeypatch.setattr(documents, "UPLOAD_DIR", tmp_path)
    content = text_pdf_bytes("Synthetic original text PDF")
    async with client_for(db_session, owner.id) as client:
        batch = (
            await client.post(
                ROOT, json={"kind": "statement"}, headers={"Idempotency-Key": "batch"}
            )
        ).json()
        url = f"{ROOT}/{batch['id']}/sources"
        uploaded = await client.post(
            url,
            files={"file": ("test.pdf", content, "application/pdf")},
            headers={"Idempotency-Key": "upload"},
        )
        assert uploaded.status_code == 201
        replay = await client.post(
            url,
            files={"file": ("test.pdf", content, "application/pdf")},
            headers={"Idempotency-Key": "upload"},
        )
        assert replay.json() == uploaded.json()
        assert (await client.get(f"{ROOT}/{batch['id']}/rows")).json()["total"] == 0
    assert await db_session.scalar(select(func.count()).select_from(FinancialTransaction)) == 0


async def test_commit_http_replay_and_result_recovery_do_not_take_client_postings(
    db_session, owner, tmp_path, monkeypatch
):
    case, request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    async with client_for(db_session, owner.id) as client:
        url = f"{ROOT}/{case.batch_id}"
        assert (
            await client.post(
                url + "/commit",
                json=request.model_dump(mode="json") | {"postings": []},
                headers={"Idempotency-Key": "bad-shape"},
            )
        ).status_code == 422
        first = await client.post(
            url + "/commit",
            json=request.model_dump(mode="json"),
            headers={"Idempotency-Key": "commit-once"},
        )
        assert first.status_code == 200
        replay = await client.post(
            url + "/commit",
            json=request.model_dump(mode="json"),
            headers={"Idempotency-Key": "commit-once"},
        )
        recovered = await client.get(url + "/commands/commit-once")
        assert replay.json() == recovered.json() == first.json()
        missing = await client.get(url + "/commands/never-issued")
        assert missing.status_code == 404


async def test_public_preview_does_not_disclose_internal_fingerprints_or_storage_paths(
    db_session, owner, tmp_path, monkeypatch
):
    case, _request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    async with client_for(db_session, owner.id) as client:
        response = await client.post(
            f"{ROOT}/{case.batch_id}/preview",
            json={
                "expected_version": 2,
                "group_ids": [str(case.decision.group_id)],
                "acknowledgements": [f"opening_gap:{case.source_id}"],
            },
            headers={"Idempotency-Key": "preview"},
        )
        assert response.status_code == 200
        assert set(response.json()) == {
            "id",
            "batch_id",
            "version",
            "request_hash",
            "groups",
            "quotes",
            "new_transaction_count",
            "linked_count",
            "unresolved_count",
            "warnings",
        }
        text = response.text
        assert (
            "storage_path" not in text
            and "ledger_digest" not in text
            and '"snapshot"' not in text
            and '"payload"' not in text
        )
        assert response.json()["new_transaction_count"] == 1


async def test_archive_is_replayable_and_foreign_source_in_path_cannot_be_prepared(
    db_session, owner, other_owner, tmp_path, monkeypatch
):
    case, _request = await confirmed_import(db_session, owner.id, tmp_path, monkeypatch)
    async with client_for(db_session, other_owner.id) as client:
        foreign = await client.post(
            f"{ROOT}/{uuid.uuid4()}/sources/{case.source_id}/prepare",
            headers={"Idempotency-Key": "foreign-prepare"},
        )
        assert foreign.status_code == 404
    async with client_for(db_session, owner.id) as client:
        url = f"{ROOT}/{case.batch_id}/archive"
        first = await client.post(url, headers={"Idempotency-Key": "archive"})
        assert first.status_code == 200 and first.json()["archived_at"] is not None
        assert (
            await client.post(url, headers={"Idempotency-Key": "archive"})
        ).json() == first.json()
