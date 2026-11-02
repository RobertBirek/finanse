import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

import app.main  # noqa: F401 - register complete metadata for integration schema lifecycle
from app.config import Settings
from app.documents.job_models import (
    DocumentProcessingJob,
    DocumentVisionPolicy,
    DocumentVisionUsage,
)
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.processing_policy import set_vision_policy
from app.documents.vision_config import get_vision_config


def _activation_config():
    config = get_vision_config(
        Settings(
            DOCUMENT_VISION_PROVIDER="test-provider",
            DOCUMENT_VISION_BASE_URL="https://vision.example.test/v1",
            DOCUMENT_VISION_MODEL="test-model",
            DOCUMENT_VISION_API_KEY="vision-secret",
            DOCUMENT_VISION_PROMPT_VERSION="prompt-1",
            DOCUMENT_VISION_SCHEMA_VERSION="schema-1",
        )
    )
    assert config is not None
    return config


def test_vision_config_does_not_inherit_advisor_key() -> None:
    settings = Settings(OPENAI_API_KEY="advisor-secret")
    assert get_vision_config(settings) is None

    config = get_vision_config(
        Settings(
            DOCUMENT_VISION_PROVIDER="test-provider",
            DOCUMENT_VISION_BASE_URL="https://vision.example.test/v1",
            DOCUMENT_VISION_MODEL="test-model",
            DOCUMENT_VISION_API_KEY="vision-secret",
        )
    )
    assert config is not None
    assert "vision-secret" not in repr(config)
    assert (
        config.configuration_fingerprint
        == get_vision_config(
            Settings(
                DOCUMENT_VISION_PROVIDER="TEST-PROVIDER",
                DOCUMENT_VISION_BASE_URL="https://VISION.example.test/v1",
                DOCUMENT_VISION_MODEL="test-model",
                DOCUMENT_VISION_API_KEY="another-secret",
            )
        ).configuration_fingerprint
    )

    for base_url in (
        "http://vision.example.test",
        "https://user:password@vision.example.test",
        "https://vision.example.test/path?token=x",
        "https://vision.example.test/path#fragment",
    ):
        with pytest.raises(ValidationError):
            Settings(DOCUMENT_VISION_BASE_URL=base_url)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_constraints(db_session) -> None:
    document = Document(
        user_id=uuid.uuid4(),
        filename="receipt.jpg",
        original_name="receipt.jpg",
        mime_type="image/jpeg",
        sha256_hash="c" * 64,
        size_bytes=1,
        storage_path="aa/receipt.jpg",
    )
    db_session.add(document)
    await db_session.flush()
    job = DocumentProcessingJob(
        user_id=document.user_id,
        document_id=document.id,
        kind="invalid",
        intent_key="intent",
        request_hash="a" * 64,
        state="pending",
    )
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    usage = DocumentVisionUsage(user_id=uuid.uuid4(), reserved_calls=-1)
    db_session.add(usage)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    document = Document(
        user_id=uuid.uuid4(),
        filename="constraint.jpg",
        original_name="constraint.jpg",
        mime_type="image/jpeg",
        sha256_hash="j" * 64,
        size_bytes=1,
        storage_path="aa/constraint.jpg",
    )
    db_session.add(document)
    await db_session.flush()

    async with db_session.begin_nested():
        db_session.add(
            Document(
                user_id=uuid.uuid4(),
                filename="invalid.jpg",
                original_name="invalid.jpg",
                mime_type="image/jpeg",
                sha256_hash="e" * 64,
                size_bytes=1,
                storage_path="aa/invalid.jpg",
                processing_method="invalid",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async with db_session.begin_nested():
        db_session.add(
            DocumentExtractionRevision(
                user_id=document.user_id,
                document_id=document.id,
                revision=1,
                status="pending",
                data={},
                field_provenance={},
                input_method="invalid",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async with db_session.begin_nested():
        db_session.add(
            DocumentProcessingJob(
                user_id=document.user_id,
                document_id=document.id,
                kind="vision",
                intent_key="invalid-state",
                request_hash="f" * 64,
                state="invalid",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async with db_session.begin_nested():
        db_session.add(
            DocumentProcessingJob(
                user_id=document.user_id,
                document_id=document.id,
                kind="vision",
                intent_key="negative-attempts",
                request_hash="g" * 64,
                state="pending",
                attempt_count=-1,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_policy_disable_changes_epoch_and_cannot_resume_old_jobs(db_session) -> None:
    document = Document(
        user_id=uuid.uuid4(),
        filename="receipt.jpg",
        original_name="receipt.jpg",
        mime_type="image/jpeg",
        sha256_hash="d" * 64,
        size_bytes=1,
        storage_path="aa/receipt.jpg",
    )
    policy = DocumentVisionPolicy(id=1, enabled=True, epoch=4)
    db_session.add_all((document, policy))
    await db_session.flush()
    job = DocumentProcessingJob(
        user_id=document.user_id,
        document_id=document.id,
        kind="vision",
        intent_key="image:1",
        request_hash="b" * 64,
        state="pending",
        policy_epoch=4,
    )
    db_session.add(job)
    await db_session.flush()

    disabled = await set_vision_policy(db_session, enabled=False, performed_by="test")
    assert disabled.enabled is False
    assert disabled.epoch == 5
    await db_session.refresh(job)
    assert (job.state, job.error_code, job.lease_token) == ("paused", "vision_disabled", None)

    enabled = await set_vision_policy(
        db_session, enabled=True, performed_by="test", config=_activation_config()
    )
    assert enabled.epoch == 6
    await db_session.refresh(job)
    assert job.state == "paused"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_configuration_change_disables_enabled_policy_and_pauses_old_jobs(db_session) -> None:
    from app.documents.processing_policy import reconcile_vision_policy_configuration

    old_config = get_vision_config(
        Settings(
            DOCUMENT_VISION_PROVIDER="provider-a",
            DOCUMENT_VISION_BASE_URL="https://vision.example.test/v1",
            DOCUMENT_VISION_MODEL="model-a",
            DOCUMENT_VISION_API_KEY="secret-a",
            DOCUMENT_VISION_PROMPT_VERSION="prompt-1",
            DOCUMENT_VISION_SCHEMA_VERSION="schema-1",
        )
    )
    changed_config = get_vision_config(
        Settings(
            DOCUMENT_VISION_PROVIDER="provider-b",
            DOCUMENT_VISION_BASE_URL="https://vision.example.test/v1",
            DOCUMENT_VISION_MODEL="model-b",
            DOCUMENT_VISION_API_KEY="secret-b",
            DOCUMENT_VISION_PROMPT_VERSION="prompt-2",
            DOCUMENT_VISION_SCHEMA_VERSION="schema-2",
        )
    )
    assert old_config is not None and changed_config is not None
    document = Document(
        user_id=uuid.uuid4(),
        filename="receipt.jpg",
        original_name="receipt.jpg",
        mime_type="image/jpeg",
        sha256_hash="h" * 64,
        size_bytes=1,
        storage_path="aa/receipt.jpg",
    )
    policy = DocumentVisionPolicy(
        id=1, enabled=True, epoch=7, configuration_fingerprint=old_config.configuration_fingerprint
    )
    db_session.add_all((document, policy))
    await db_session.flush()
    job = DocumentProcessingJob(
        user_id=document.user_id,
        document_id=document.id,
        kind="vision",
        intent_key="image:2",
        request_hash="i" * 64,
        state="pending",
        policy_epoch=7,
    )
    db_session.add(job)
    await db_session.flush()

    snapshot = await reconcile_vision_policy_configuration(db_session, config=changed_config)
    assert (snapshot.enabled, snapshot.epoch) == (False, 8)
    assert snapshot.configuration_fingerprint == changed_config.configuration_fingerprint
    await db_session.refresh(job)
    assert (job.state, job.error_code) == ("paused", "vision_configuration_changed")

    with pytest.raises(ValueError, match="configuration_missing"):
        await set_vision_policy(db_session, enabled=True, performed_by="test", config=None)
