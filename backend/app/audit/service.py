import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent


async def log_event(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    entity_type: str,
    entity_id: str,
    action: str,
    old_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    performed_by: str = "human",
    source_ip: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_state=old_state,
        new_state=new_state,
        performed_by=performed_by,
        source_ip=source_ip,
    )
    db.add(event)
    await db.flush()
    return event
