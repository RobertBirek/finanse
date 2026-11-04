"""Consent is explicit and independent from human approval and rule automation."""

import uuid

import pytest
from sqlalchemy import func, select

from app.finance.models import FinanceCommandReceipt, Posting
from tests.test_finance.test_account_currency import client_for
from tests.test_finance.test_categorization import setup
from tests.test_finance.test_rule_policy import ROOT, configured, mutate

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PATH = "/suggestions/settings"


def fake_configuration(monkeypatch):
    from app.config import settings

    for name, value in {
        "ENABLED": True,
        "PROVIDER": "openai",
        "BASE_URL": "https://api.openai.com/v1",
        "MODEL": "test-only-no-live-model",
        "API_KEY": "fake-never-sent",
    }.items():
        monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_" + name, value)


async def enable_server(db, owner, monkeypatch):
    from app.config import settings
    from app.finance.suggestion_config import get_suggestion_config
    from app.finance.suggestion_policy import set_suggestion_policy

    fake_configuration(monkeypatch)
    config = get_suggestion_config(settings)
    await set_suggestion_policy(
        db, enabled=True, expected_epoch=0, performed_by=owner, config=config
    )
    await db.commit()
    return config


async def optin(client, version=0):
    scope = (await client.get(ROOT + PATH)).json()
    return await mutate(
        client,
        "patch",
        PATH,
        {
            "expected_version": version,
            "enabled": True,
            "expected_server_epoch": scope["server_epoch"],
            "expected_configuration_fingerprint": scope["configuration_fingerprint"],
            "confirm_future_only": True,
            "confirm_data_export": True,
        },
    )


async def test_default_off_read_is_nonmutating(db_session):
    owner, _, _, _, _ = await setup(db_session)
    before = await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt))
    postings = await db_session.scalar(select(func.count()).select_from(Posting))
    async with client_for(db_session, owner) as client:
        response = await client.get(ROOT + PATH)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["enabled"] is False and data["version"] == 0
        assert data["effective_enabled"] is False and data["available"] is False
        assert data["server_epoch"] == 0
        assert "opis" in data["privacy_text"].lower()
        usage = await client.get(ROOT + "/suggestions/usage?date=2026-11-04")
        assert usage.status_code == 200, usage.text
        assert usage.json()["remaining_slots"] == 5
        assert usage.json()["cost_status"] == "unpriced"
        assert usage.json()["known_input_tokens"] is None
    assert (
        await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == before
    )
    assert await db_session.scalar(select(func.count()).select_from(Posting)) == postings


async def test_unavailable_enable_never_grants_future_unknown_provider(db_session):
    owner, _, _, _, _ = await configured(db_session)
    async with client_for(db_session, owner) as client:
        result = await mutate(
            client,
            "patch",
            PATH,
            {
                "expected_version": 0,
                "enabled": True,
                "expected_server_epoch": 0,
                "expected_configuration_fingerprint": "a" * 64,
                "confirm_future_only": True,
                "confirm_data_export": True,
            },
        )
        assert result.status_code == 409, result.text
        assert (await client.get(ROOT + PATH)).json()["version"] == 0


@pytest.mark.parametrize(
    "extra", [{"model": "injected"}, {"enabled": "true"}, {"expected_version": True}]
)
async def test_settings_reject_coercion_and_spoofed_server_fields(db_session, extra):
    owner, _, _, _, _ = await setup(db_session)
    async with client_for(db_session, owner) as client:
        result = await mutate(
            client, "patch", PATH, {"expected_version": 0, "enabled": False, **extra}
        )
        assert result.status_code == 422, result.text


async def test_user_off_is_idempotent_and_does_not_change_rules(db_session):
    owner, _, _, _, _ = await configured(db_session)
    async with client_for(db_session, owner) as client:
        body = {"expected_version": 0, "enabled": False}
        key = uuid.uuid4().hex
        first = await mutate(client, "patch", PATH, body, key)
        assert first.status_code == 200, first.text
        assert first.json()["version"] == 1
        assert (await mutate(client, "patch", PATH, body, key)).json() == first.json()
        conflict = await mutate(client, "patch", PATH, {**body, "expected_version": 1}, key)
        assert conflict.status_code == 409
        assert (await client.get(ROOT + "/settings")).json()["rules_enabled"] is True


async def test_suggestion_settings_require_real_session_csrf(db_session, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.config import settings
    from app.database import get_db
    from app.identity.service import create_session
    from app.main import app

    owner, _, _, _, _ = await setup(db_session)
    token, csrf, _ = await create_session(db_session, owner)
    await db_session.commit()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", ("https://ui.test.invalid",))

    async def database():
        yield db_session

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://ui.test.invalid"
        ) as client:
            common = {
                "Origin": "https://ui.test.invalid",
                "Cookie": f"advisor_session={token}; advisor_csrf={csrf}",
                "Idempotency-Key": "csrf",
            }
            result = await client.patch(
                ROOT + PATH, headers=common, json={"expected_version": 0, "enabled": False}
            )
            assert result.status_code == 403, result.text
            result = await client.patch(
                ROOT + PATH,
                headers={**common, "X-CSRF-Token": csrf},
                json={"expected_version": 0, "enabled": False},
            )
            assert result.status_code == 200, result.text
            assert (await client.get(ROOT + PATH)).status_code == 401
    finally:
        app.dependency_overrides.clear()


async def test_optin_binds_current_server_scope_and_explicit_export_consent(
    db_session, monkeypatch
):
    owner, _, _, _, _ = await configured(db_session)
    await enable_server(db_session, owner, monkeypatch)
    async with client_for(db_session, owner) as client:
        scope = (await client.get(ROOT + PATH)).json()
        assert scope["available"] is True and scope["effective_enabled"] is False
        missing = await mutate(client, "patch", PATH, {"expected_version": 0, "enabled": True})
        assert missing.status_code == 422
        result = await optin(client)
        assert result.status_code == 200, result.text
        assert result.json()["effective_enabled"] is True
        from app.config import settings

        monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_MODEL", "different-test-model")
        changed = (await client.get(ROOT + PATH)).json()
        assert changed["enabled"] is True and changed["effective_enabled"] is False
        assert changed["available"] is False
        disabled = await mutate(client, "patch", PATH, {"expected_version": 1, "enabled": False})
        assert disabled.status_code == 200 and disabled.json()["version"] == 2


async def test_rotated_policy_requires_new_consent_and_foreign_marker_cannot_enable(
    db_session, monkeypatch
):
    from app.finance.suggestion_policy import set_suggestion_policy
    from tests.test_finance.test_bill_payments import create_owner

    owner, _, _, marker, _ = await configured(db_session)
    config = await enable_server(db_session, owner, monkeypatch)
    async with client_for(db_session, owner) as client:
        assert (await optin(client)).json()["effective_enabled"] is True
        await set_suggestion_policy(
            db_session, enabled=False, expected_epoch=1, performed_by=owner, config=config
        )
        await db_session.commit()
        await set_suggestion_policy(
            db_session, enabled=True, expected_epoch=2, performed_by=owner, config=config
        )
        await db_session.commit()
        assert (await client.get(ROOT + PATH)).json()["effective_enabled"] is False
        assert (await optin(client, 1)).json()["effective_enabled"] is True
        marker.user_id = await create_owner(db_session)
        await db_session.commit()
        assert (await optin(client, 2)).status_code == 422


async def test_approved_llm_origin_never_projects_as_manual(db_session):
    from datetime import UTC, datetime, timedelta

    from app.finance.categorization_context import load_context
    from app.finance.rule_models import TransactionCategorizationOrigin as Origin
    from app.finance.rule_origin_reads import attach_assignment_origins
    from app.finance.suggestion_models import (
        CategorizationProposalItem as Item,
    )
    from app.finance.suggestion_models import (
        CategorizationSuggestionJob as Job,
    )

    owner, txn, _, marker, target = await setup(db_session)
    job = Job(
        user_id=owner,
        transaction_id=txn.id,
        source_context_sha256="a" * 64,
        marker_id=marker.id,
        settings_version=1,
        user_epoch=1,
        server_epoch=1,
        configuration_fingerprint="a" * 64,
    )
    db_session.add(job)
    await db_session.flush()
    item = Item(
        user_id=owner,
        job_id=job.id,
        transaction_id=txn.id,
        source_context_sha256="a" * 64,
        request_sha256="b" * 64,
        taxonomy_sha256="c" * 64,
        generated_description="Test",
        private_key_map={},
        decision="existing_category",
        target_category_id=target.id,
        explanation="Test reason",
        confidence="high",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db_session.add(item)
    await db_session.flush()
    receipt = FinanceCommandReceipt(
        user_id=owner,
        action="apply_reviewed_category_proposal",
        key="evidence",
        request_hash="a" * 64,
        entity_id=txn.id,
        result_ids=[str(txn.id)],
        version=1,
        response_json={"grant": {"display_description": "Test", "target_path": "Test target"}},
    )
    db_session.add(receipt)
    await db_session.flush()
    origin = Origin(
        transaction_id=txn.id,
        user_id=owner,
        origin="approved_llm",
        version=1,
        proposal_item_id=item.id,
        approval_receipt_id=receipt.id,
        approval_snapshot_sha256="a" * 64,
        assignment_sha256="b" * 64,
    )
    db_session.add(origin)
    await db_session.flush()
    projected = (await attach_assignment_origins(db_session, owner, [txn]))[0].assignment_origin
    assert projected.origin == "approved_llm" and projected.proposal_item_id == item.id
    ctx = await load_context(db_session, owner, txn.id)
    assert ctx.response().assignment_origin.origin == "approved_llm"


async def test_observed_config_drift_revokes_server_epoch_without_get_writes(
    db_session, monkeypatch
):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.config import settings
    from app.finance import suggestion_worker
    from app.finance.suggestion_policy import current_policy, set_suggestion_policy

    owner, _, _, _, _ = await configured(db_session)
    config = await enable_server(db_session, owner, monkeypatch)
    async with client_for(db_session, owner) as client:
        assert (await optin(client)).json()["effective_enabled"]
        monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_MODEL", "changed-scope-test")
        assert not (await client.get(ROOT + PATH)).json()["available"]
        assert (await current_policy(db_session)).epoch == 1  # GET is nonmutating.
        await db_session.commit()

        async def unexpected(*args):
            pytest.fail("No historical generation on reconciliation")

        monkeypatch.setattr(
            suggestion_worker,
            "async_session_factory",
            async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False),
        )
        await suggestion_worker.dispatch_suggestion_jobs(
            {"redis": type("NoJobs", (), {"enqueue_job": unexpected})()}
        )
        row = await current_policy(db_session)
        assert not row.enabled and row.epoch == 2
        monkeypatch.setattr(settings, "FINANCE_SUGGESTIONS_MODEL", config.model)
        assert not (await client.get(ROOT + PATH)).json()["effective_enabled"]
        await set_suggestion_policy(
            db_session, enabled=True, expected_epoch=2, performed_by=owner, config=config
        )
        await db_session.commit()
        assert not (await client.get(ROOT + PATH)).json()["effective_enabled"]
