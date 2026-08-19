import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.audit.models import AuditEvent

logger = logging.getLogger(__name__)


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


async def log_security_event(
    action: str,
    entity_id: str,
    user_id: uuid.UUID | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    """Persist security telemetry separately so rejected requests cannot roll it back."""
    try:
        async with database.async_session_factory() as db, db.begin():
            await log_event(
                db,
                user_id,
                "security",
                entity_id[:50],
                action,
                new_state=state,
                performed_by="system",
            )
    except Exception:
        logger.exception("Could not persist security audit event: %s", action)
