"""Metadata-only lifecycle helpers. No ledger/provider dependencies or writes."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.finance.suggestion_models import CategorizationProposalItem as Item


async def supersede_pending_proposals(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    *,
    except_proposal_id: uuid.UUID | None = None,
) -> None:
    rows = (
        await db.scalars(
            select(Item)
            .where(
                Item.user_id == owner,
                Item.transaction_id == transaction_id,
                Item.status == "pending",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    for row in rows:
        if row.id == except_proposal_id:
            continue
        row.status = "superseded"
        row.version += 1
        await log_event(
            db,
            owner,
            "categorization_proposal",
            str(row.id),
            "proposal_superseded",
            new_state={"status": row.status, "version": row.version},
        )


async def expire_proposal_items(db: AsyncSession, now: datetime, *, limit: int) -> int:
    rows = (
        await db.scalars(
            select(Item)
            .where(Item.status == "pending", Item.expires_at <= now)
            .order_by(Item.expires_at, Item.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
    ).all()
    for row in rows:
        row.status = "expired"
        row.version += 1
        await log_event(
            db,
            row.user_id,
            "categorization_proposal",
            str(row.id),
            "proposal_expired",
            new_state={"status": row.status, "version": row.version},
        )
    await db.flush()
    return len(rows)
