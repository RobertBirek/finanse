import pytest

from app.config import settings
from app.documents.job_models import DocumentVisionPolicy
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.router import upload_capabilities
from app.identity.models import User
from scripts import document_vision_policy as cli


@pytest.mark.integration
async def test_cli_dry_run_and_epoch_mismatch_do_not_mutate(db_session, monkeypatch):
    from tests.conftest import TEST_DATABASE_URL

    monkeypatch.setenv(
        "DOCUMENT_VISION_POLICY_DATABASE_URL", TEST_DATABASE_URL.replace("localhost", "127.0.0.1")
    )
    db_session.add(DocumentVisionPolicy(id=1, enabled=False, epoch=4))
    await db_session.commit()
    assert await cli.run(False, 4, False) == 0
    assert await cli.run(False, 3, True) == 2
    policy = await db_session.get(DocumentVisionPolicy, 1)
    assert (policy.enabled, policy.epoch) == (False, 4)


@pytest.mark.integration
async def test_disable_pauses_old_work_and_enable_never_resumes_it(db_session):
    from app.documents.processing_policy import set_vision_policy
    from app.documents.vision_config import VisionConfig

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

    db_session.add(
        DocumentProcessingJob(
            user_id=user.id,
            document_id=document.id,
            revision_id=revision.id,
            kind="vision",
            intent_key="old",
            request_hash="x",
            state="processing",
        )
    )
    db_session.add(DocumentVisionPolicy(id=1, enabled=True, epoch=4))
    await db_session.commit()
    await set_vision_policy(db_session, enabled=False, performed_by="test")
    disabled = await db_session.get(DocumentVisionPolicy, 1)
    assert (disabled.enabled, disabled.epoch) == (False, 5)
    assert revision.status == "incomplete"
    config = VisionConfig("test", "https://vision.example.test/v1", "model", "secret", "p1", "s1")
    await set_vision_policy(db_session, enabled=True, performed_by="test", config=config)
    restarted = await db_session.get(DocumentVisionPolicy, 1)
    assert (restarted.enabled, restarted.epoch) == (True, 6)


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
