import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditEvent
from app.config import Settings, settings
from app.documents.job_models import DocumentVisionPolicy
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.router import upload_capabilities
from app.documents.vision_config import get_vision_config
from app.identity.models import User
from scripts import document_vision_policy as cli


def _gate_environment() -> dict[str, str]:
    gate_path = (
        Path(__file__).resolve().parents[3]
        / ".superpowers/sdd/2026-10-31-automatic-document-vision/gate.py"
    )
    spec = importlib.util.spec_from_file_location("vision_gate", gate_path)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate.environment()


def _configure_cli_environment(monkeypatch, *, configured: bool) -> None:
    environment = _gate_environment()
    monkeypatch.setenv("DOCUMENT_VISION_POLICY_DATABASE_URL", environment["TEST_DATABASE_URL"])
    monkeypatch.setenv("DATABASE_URL", environment["DATABASE_URL"])
    monkeypatch.setenv("TEST_DATABASE_URL", environment["TEST_DATABASE_URL"])
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
    _configure_cli_environment(monkeypatch, configured=False)
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()
    assert await cli.run(False, 4, False) == 0
    assert await cli.run(False, 3, True) == 2
    policy = await db_session.get(DocumentVisionPolicy, 1)
    assert (policy.enabled, policy.epoch) == (False, 4)


@pytest.mark.integration
async def test_cli_apply_requires_loaded_config_and_never_resumes_paused_work(
    db_session, monkeypatch
):
    _configure_cli_environment(monkeypatch, configured=False)

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

    _configure_cli_environment(monkeypatch, configured=True)
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
    assert (processing_job.state, processing_job.lease_token) == ("paused", None)
    assert pending_job.state == "paused"
    assert revision.status == "incomplete"

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
