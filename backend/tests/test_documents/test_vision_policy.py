import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.config import Settings, settings
from app.documents.job_models import DocumentVisionPolicy
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.processing_policy import set_vision_policy
from app.documents.router import upload_capabilities
from app.documents.vision_config import get_vision_config
from app.identity.models import User
from scripts import document_vision_policy as cli


def _configure_cli_environment(monkeypatch, database_url: str, *, configured: bool) -> None:
    """Point the CLI at the already-guarded database bound to this test session."""
    monkeypatch.setenv("DOCUMENT_VISION_POLICY_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    for name, value in {
        "DOCUMENT_VISION_PROVIDER": "test-provider",
        "DOCUMENT_VISION_BASE_URL": "https://vision.example.test/v1",
        "DOCUMENT_VISION_MODEL": "test-model",
        "DOCUMENT_VISION_API_KEY": "test-only-key",
        "DOCUMENT_VISION_PROMPT_VERSION": "p1",
        "DOCUMENT_VISION_SCHEMA_VERSION": "s1",
    }.items():
        if configured:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


@pytest.mark.integration
async def test_cli_dry_run_and_epoch_mismatch_do_not_mutate(db_session, monkeypatch):
    _configure_cli_environment(
        monkeypatch, db_session.bind.url.render_as_string(hide_password=False), configured=False
    )
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()
    assert await cli.run(False, 4, False) == 0
    assert await cli.run(False, 3, True) == 2
    policy = await db_session.get(DocumentVisionPolicy, 1)
    assert (policy.enabled, policy.epoch) == (False, 4)


@pytest.mark.integration
async def test_policy_expected_epoch_is_checked_under_transition_lock(db_session, monkeypatch):
    _configure_cli_environment(
        monkeypatch, db_session.bind.url.render_as_string(hide_password=False), configured=True
    )
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()

    winner = await set_vision_policy(
        db_session,
        enabled=True,
        performed_by="test",
        config=get_vision_config(Settings()),
        expected_epoch=4,
    )
    await db_session.commit()
    assert winner.epoch == 5

    with pytest.raises(ValueError, match="expected_epoch_mismatch"):
        await set_vision_policy(db_session, enabled=False, performed_by="test", expected_epoch=4)
    await db_session.rollback()
    policy = await db_session.get(DocumentVisionPolicy, 1)
    assert policy is not None and (policy.enabled, policy.epoch) == (True, 5)


@pytest.mark.integration
async def test_stale_epoch_does_not_create_an_absent_policy_row(db_session):
    with pytest.raises(ValueError, match="expected_epoch_mismatch"):
        await set_vision_policy(db_session, enabled=False, performed_by="test", expected_epoch=2)
    await db_session.rollback()
    assert await db_session.get(DocumentVisionPolicy, 1) is None


@pytest.mark.integration
async def test_competing_cli_apply_has_one_epoch_transition_and_one_stale_refusal(
    db_session, monkeypatch
):
    """Both CLI sessions pass the old epoch barrier; only the locked winner may transition."""
    _configure_cli_environment(
        monkeypatch, db_session.bind.url.render_as_string(hide_password=False), configured=True
    )
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()
    real_transition = cli.set_vision_policy
    loser_reached_transition = asyncio.Event()
    allow_winner_transition = asyncio.Event()
    winner_finished = asyncio.Event()

    async def controlled_transition(db, **kwargs):
        if kwargs["enabled"]:
            await allow_winner_transition.wait()
        else:
            loser_reached_transition.set()
            await winner_finished.wait()
        return await real_transition(db, **kwargs)

    monkeypatch.setattr(cli, "set_vision_policy", controlled_transition)
    winner = asyncio.create_task(cli.run(True, 4, True))
    loser = asyncio.create_task(cli.run(False, 4, True))
    await asyncio.wait_for(loser_reached_transition.wait(), timeout=5)
    allow_winner_transition.set()
    assert await asyncio.wait_for(winner, timeout=5) == 0
    winner_finished.set()
    assert await asyncio.wait_for(loser, timeout=5) == 2

    await db_session.rollback()
    policy = await db_session.get(DocumentVisionPolicy, 1, populate_existing=True)
    assert policy is not None and (policy.enabled, policy.epoch) == (True, 5)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://finanse_test:pass@evil.example/finanse_test",
        "postgresql+asyncpg://127.0.0.1:55432/not_finanse_test?target=finanse_test",
        "postgresql+asyncpg://finanse_test_127.0.0.1:pass@evil.example/other",
    ],
)
def test_cli_rejects_substring_lookalike_database_targets(monkeypatch, url):
    monkeypatch.setenv("DOCUMENT_VISION_POLICY_DATABASE_URL", url)
    with pytest.raises(ValueError, match="controlled_test_database_required"):
        cli._target_url(
            Settings(DATABASE_URL="postgresql+asyncpg://user:pass@127.0.0.1:55432/finanse_test")
        )


def test_cli_accepts_a_non_test_target_only_when_it_matches_its_configured_environment(monkeypatch):
    target = "postgresql+asyncpg://operator:secret@db.internal:5432/controlled"
    monkeypatch.setenv("DOCUMENT_VISION_POLICY_DATABASE_URL", target)
    assert (
        cli._target_url(
            Settings(DATABASE_URL="postgresql+asyncpg://runtime:secret@db.internal/controlled")
        )
        == target
    )


@pytest.mark.integration
async def test_cli_apply_requires_loaded_config_and_never_resumes_paused_work(
    db_session, monkeypatch
):
    _configure_cli_environment(
        monkeypatch, db_session.bind.url.render_as_string(hide_password=False), configured=False
    )

    user = User(email="cli-policy@example.com", password_hash="hash", display_name="Policy")
    db_session.add(user)
    await db_session.flush()
    document = Document(
        user_id=user.id,
        filename="x.jpg",
        original_name="x.jpg",
        mime_type="image/jpeg",
        sha256_hash="a" * 64,
        size_bytes=1,
        storage_path="x",
        processing_method="vision",
    )
    db_session.add(document)
    await db_session.flush()
    revision = DocumentExtractionRevision(
        user_id=user.id,
        document_id=document.id,
        revision=1,
        status="processing",
        data={"document_type": "other", "fields": {}, "provenance": {}, "parser_version": None},
        field_provenance={},
        input_method="image",
    )
    db_session.add(revision)
    await db_session.flush()
    from app.documents.job_models import DocumentProcessingJob

    processing_job = DocumentProcessingJob(
        user_id=user.id,
        document_id=document.id,
        revision_id=revision.id,
        kind="vision",
        intent_key="old",
        request_hash="x",
        state="processing",
        lease_token=uuid.uuid4(),
    )
    pending_job = DocumentProcessingJob(
        user_id=user.id,
        document_id=document.id,
        kind="vision",
        intent_key="pending",
        request_hash="y",
        state="pending",
    )
    db_session.add_all([processing_job, pending_job])
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()
    assert await cli.run(True, 4, True) == 2
    assert (await db_session.get(DocumentVisionPolicy, 1)).epoch == 4
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    await db_session.refresh(processing_job)
    await db_session.refresh(pending_job)
    await db_session.refresh(revision)
    assert (processing_job.state, pending_job.state, revision.status) == (
        "processing",
        "pending",
        "processing",
    )

    _configure_cli_environment(
        monkeypatch, db_session.bind.url.render_as_string(hide_password=False), configured=True
    )
    loaded_config = get_vision_config(Settings())
    assert loaded_config is not None
    assert await cli.run(True, 4, True) == 0
    await db_session.rollback()
    enabled = await db_session.get(DocumentVisionPolicy, 1, populate_existing=True)
    assert enabled is not None
    assert (enabled.enabled, enabled.epoch) == (True, 5)
    assert enabled.configuration_fingerprint == loaded_config.configuration_fingerprint

    assert await cli.run(False, 5, True) == 0
    await db_session.rollback()
    disabled = await db_session.get(DocumentVisionPolicy, 1, populate_existing=True)
    assert disabled is not None
    assert (disabled.enabled, disabled.epoch) == (False, 6)
    await db_session.refresh(processing_job)
    await db_session.refresh(pending_job)
    await db_session.refresh(revision)
    await db_session.refresh(document)
    assert (processing_job.state, processing_job.lease_token) == ("paused", None)
    assert pending_job.state == "paused"
    assert revision.status == "incomplete"
    assert document.status == "done"

    assert await cli.run(True, 6, True) == 0
    await db_session.rollback()
    restarted = await db_session.get(DocumentVisionPolicy, 1, populate_existing=True)
    assert restarted is not None
    assert (restarted.enabled, restarted.epoch) == (True, 7)
    await db_session.refresh(processing_job)
    await db_session.refresh(pending_job)
    assert (processing_job.state, pending_job.state) == ("paused", "paused")


async def test_capabilities_require_effective_flag_and_never_expose_secrets(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_VISION_ENABLED", True)
    monkeypatch.setattr(settings, "DOCUMENT_VISION_PROVIDER", "safe-label")
    monkeypatch.setattr(settings, "DOCUMENT_VISION_API_KEY", "private-key")

    class DB:
        async def get(self, *_args):
            return None

    capabilities = await upload_capabilities(None, DB())  # type: ignore[arg-type]
    payload = capabilities.model_dump()
    assert payload["automatic_image_vision"] is False
    assert payload["vision_provider_label"] is None
    assert "private-key" not in str(payload)
