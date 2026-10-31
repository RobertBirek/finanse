from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.documents.job_models import DocumentProcessingJob, DocumentVisionPolicy
from app.documents.models import DocumentExtractionRevision


@dataclass(frozen=True)
class PolicySnapshot:
    enabled: bool
    epoch: int


async def set_vision_policy(
    db: AsyncSession, *, enabled: bool, performed_by: str
) -> PolicySnapshot:
    policy = await db.get(DocumentVisionPolicy, 1, with_for_update=True)
    if policy is None:
        policy = DocumentVisionPolicy(id=1, enabled=False, epoch=1)
        db.add(policy)
        await db.flush()

    previous = PolicySnapshot(enabled=policy.enabled, epoch=policy.epoch)
    if policy.enabled == enabled:
        return previous

    policy.enabled = enabled
    policy.epoch += 1
    if not enabled:
        await db.execute(
            update(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.kind == "vision",
                DocumentProcessingJob.state.in_(("pending", "processing")),
            )
            .values(
                state="paused",
                error_code="vision_disabled",
                lease_token=None,
                lease_expires_at=None,
            )
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
            .values(status="incomplete", error_code="vision_disabled")
        )
    snapshot = PolicySnapshot(enabled=policy.enabled, epoch=policy.epoch)
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
