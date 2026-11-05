"""Independent fail-closed receipt-image export purpose. No header policy inheritance."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.documents.receipt_read_config import ReceiptReadConfig
from app.documents.receipt_read_models import ReceiptReadJob, ReceiptReadPolicy
from app.documents.receipt_read_schemas import READ_ACTIVE_STATES
from app.finance.categorization_context import CategorizationError


@dataclass(frozen=True)
class ReceiptReadPolicySnapshot:
    enabled: bool
    epoch: int
    fingerprint: str | None


async def receipt_read_admission(db: AsyncSession) -> None:
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext("receipt-read-admission"))))


async def get_receipt_read_policy(db: AsyncSession) -> ReceiptReadPolicySnapshot:
    row = await db.scalar(
        select(ReceiptReadPolicy)
        .where(ReceiptReadPolicy.id == 1)
        .execution_options(populate_existing=True)
    )
    return (
        ReceiptReadPolicySnapshot(row.enabled, row.epoch, row.configuration_fingerprint)
        if row
        else ReceiptReadPolicySnapshot(False, 0, None)
    )


def receipt_read_allowed(
    policy: ReceiptReadPolicySnapshot, config: ReceiptReadConfig | None
) -> bool:
    return bool(
        settings.DOCUMENT_RECEIPT_ITEMS_ENABLED
        and policy.enabled
        and config
        and policy.fingerprint == config.configuration_fingerprint
    )


async def set_receipt_read_policy(
    db: AsyncSession,
    *,
    enabled: bool,
    expected_epoch: int,
    config: ReceiptReadConfig | None,
    performed_by: str,
) -> ReceiptReadPolicySnapshot:
    await receipt_read_admission(db)
    row = await db.scalar(
        select(ReceiptReadPolicy)
        .where(ReceiptReadPolicy.id == 1)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    actual = row.epoch if row else 0
    if actual != expected_epoch:
        raise CategorizationError("policy_changed", "Polityka odczytu zmieniła się.")
    if enabled and (not settings.DOCUMENT_RECEIPT_ITEMS_ENABLED or config is None):
        raise CategorizationError(
            "receipt_read_disabled", "Konfiguracja odczytu produktów nie jest aktywna."
        )
    fingerprint = config.configuration_fingerprint if config else None
    if row and row.enabled == enabled and row.configuration_fingerprint == fingerprint:
        return ReceiptReadPolicySnapshot(enabled, row.epoch, fingerprint)
    old = (
        ReceiptReadPolicySnapshot(row.enabled, actual, row.configuration_fingerprint)
        if row
        else ReceiptReadPolicySnapshot(False, 0, None)
    )
    if row is None:
        row = ReceiptReadPolicy(id=1)
        db.add(row)
    row.enabled, row.epoch, row.configuration_fingerprint = enabled, actual + 1, fingerprint
    row.changed_at = datetime.now(UTC)
    await db.execute(
        update(ReceiptReadJob)
        .where(ReceiptReadJob.state.in_(READ_ACTIVE_STATES))
        .values(
            state=case((ReceiptReadJob.dispatch_token.is_not(None), "superseded"), else_="paused"),
            error_code="receipt_read_policy_changed",
            lease_token=None,
            lease_expires_at=None,
            version=ReceiptReadJob.version + 1,
        )
    )
    await log_event(
        db,
        None,
        "receipt_read_policy",
        "1",
        "updated",
        old_state={"enabled": old.enabled, "epoch": old.epoch},
        new_state={"enabled": enabled, "epoch": row.epoch, "fingerprint": fingerprint},
        performed_by=performed_by,
    )
    await db.flush()
    return ReceiptReadPolicySnapshot(enabled, row.epoch, fingerprint)


async def reconcile_receipt_read_policy(
    db: AsyncSession, config: ReceiptReadConfig | None
) -> ReceiptReadPolicySnapshot:
    await receipt_read_admission(db)
    current = await get_receipt_read_policy(db)
    if current.enabled and not receipt_read_allowed(current, config):
        return await set_receipt_read_policy(
            db, enabled=False, expected_epoch=current.epoch, config=config, performed_by="system"
        )
    return current
