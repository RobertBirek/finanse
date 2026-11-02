from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.models import Document, DocumentExtractionRevision
from app.documents.vision_config import VisionConfig, get_vision_config


@dataclass(frozen=True)
class PolicySnapshot:
    enabled: bool
    epoch: int
    configuration_fingerprint: str | None


async def set_vision_policy(
    db: AsyncSession,
    *,
    enabled: bool,
    performed_by: str,
    config: VisionConfig | None = None,
    expected_epoch: int | None = None,
) -> PolicySnapshot:
    policy = await db.get(DocumentVisionPolicy, 1, with_for_update=True)
    actual_epoch = policy.epoch if policy is not None else 1
    if expected_epoch is not None and actual_epoch != expected_epoch:
        raise ValueError("expected_epoch_mismatch")
    if policy is None:
        policy = DocumentVisionPolicy(id=1, enabled=False, epoch=1)
        db.add(policy)
        await db.flush()

    if enabled and config is None:
        config = get_vision_config(settings)
    if enabled and (config is None or not config.is_activation_ready):
        raise ValueError("configuration_missing")
    if enabled:
        assert config is not None
    configuration_fingerprint = config.configuration_fingerprint if config is not None else None

    previous = _snapshot(policy)
    fingerprint_changed = enabled and policy.configuration_fingerprint != configuration_fingerprint
    if policy.enabled == enabled and not fingerprint_changed:
        return previous

    if fingerprint_changed and policy.enabled:
        policy.enabled = False
        policy.epoch += 1
        policy.configuration_fingerprint = configuration_fingerprint
        await _pause_vision_work(db, error_code="vision_configuration_changed")
    else:
        policy.enabled = enabled
        policy.epoch += 1
        if enabled:
            policy.configuration_fingerprint = configuration_fingerprint
        else:
            await _pause_vision_work(db, error_code="vision_disabled")
    snapshot = _snapshot(policy)
    await log_event(
        db,
        user_id=None,
        entity_type="document_vision_policy",
        entity_id="1",
        action="updated",
        old_state={"enabled": previous.enabled, "epoch": previous.epoch},
        new_state={"enabled": snapshot.enabled, "epoch": snapshot.epoch},
        performed_by=performed_by,
    )
    return snapshot


async def reconcile_vision_policy_configuration(
    db: AsyncSession, *, config: VisionConfig | None
) -> PolicySnapshot:
    """Fail closed when an enabled policy no longer matches its configured destination."""
    policy = await db.get(DocumentVisionPolicy, 1, with_for_update=True)
    if policy is None:
        policy = DocumentVisionPolicy(id=1, enabled=False, epoch=1)
        db.add(policy)
        await db.flush()
    if not policy.enabled:
        return _snapshot(policy)

    fingerprint = (
        config.configuration_fingerprint if config and config.is_activation_ready else None
    )
    if policy.configuration_fingerprint == fingerprint:
        return _snapshot(policy)

    previous = _snapshot(policy)
    policy.enabled = False
    policy.epoch += 1
    policy.configuration_fingerprint = fingerprint
    error_code = "vision_configuration_changed" if fingerprint else "configuration_missing"
    await _pause_vision_work(db, error_code=error_code)
    snapshot = _snapshot(policy)
    await log_event(
        db,
        user_id=None,
        entity_type="document_vision_policy",
        entity_id="1",
        action="configuration_changed",
        old_state={
            "enabled": previous.enabled,
            "epoch": previous.epoch,
            "fingerprint": previous.configuration_fingerprint,
        },
        new_state={
            "enabled": snapshot.enabled,
            "epoch": snapshot.epoch,
            "fingerprint": snapshot.configuration_fingerprint,
        },
        performed_by="system",
    )
    return snapshot


def _snapshot(policy: DocumentVisionPolicy) -> PolicySnapshot:
    return PolicySnapshot(
        enabled=policy.enabled,
        epoch=policy.epoch,
        configuration_fingerprint=policy.configuration_fingerprint,
    )


async def _pause_vision_work(db: AsyncSession, *, error_code: str) -> None:
    active_vision_documents = select(DocumentProcessingJob.document_id).where(
        DocumentProcessingJob.kind == "vision",
        DocumentProcessingJob.state.in_(("pending", "processing")),
    )
    await db.execute(
        update(Document).where(Document.id.in_(active_vision_documents)).values(status="done")
    )
    await db.execute(
        update(DocumentProcessingJob)
        .where(
            DocumentProcessingJob.kind == "vision",
            DocumentProcessingJob.state.in_(("pending", "processing")),
        )
        .values(state="paused", error_code=error_code, lease_token=None, lease_expires_at=None)
    )
    await db.execute(
        update(DocumentExtractionRevision)
        .where(
            DocumentExtractionRevision.id.in_(
                select(DocumentProcessingJob.revision_id).where(
                    DocumentProcessingJob.kind == "vision"
                )
            ),
            DocumentExtractionRevision.status.in_(("pending", "processing")),
        )
        .values(status="incomplete", error_code=error_code)
    )
