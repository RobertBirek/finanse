"""Versioned opt-in and internal server gate; reads never create grants."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.finance.categorization_context import CategorizationError, digest
from app.finance.models import FinanceCommandReceipt
from app.finance.rule_policy import category_path, get_settings, policy_locks
from app.finance.suggestion_config import PRIVACY_TEXT, SuggestionConfig, get_suggestion_config
from app.finance.suggestion_models import CategorizationLlmPolicy as Policy
from app.finance.suggestion_models import CategorizationSuggestionSettings as Consent
from app.finance.suggestion_schemas import SuggestionSettingsChange, SuggestionSettingsResponse


async def current_consent(
    db: AsyncSession, owner: uuid.UUID, *, lock: bool = False
) -> Consent | None:
    query = (
        select(Consent).where(Consent.user_id == owner).execution_options(populate_existing=True)
    )
    return await db.scalar(query.with_for_update() if lock else query)


async def current_policy(db: AsyncSession, *, lock: bool = False) -> Policy | None:
    query = select(Policy).where(Policy.id == 1).execution_options(populate_existing=True)
    return await db.scalar(query.with_for_update() if lock else query)


async def suggestion_policy_snapshot(
    db: AsyncSession, owner: uuid.UUID
) -> SuggestionSettingsResponse:
    row = await current_consent(db, owner)
    server = await current_policy(db)
    config = get_suggestion_config(settings)
    available = bool(
        config
        and server
        and server.enabled
        and server.configuration_fingerprint == config.fingerprint
    )
    marker = await get_settings(db, owner)
    marker_valid = False
    if marker and marker.uncategorized_category_id:
        try:
            await category_path(db, owner, marker.uncategorized_category_id)
            marker_valid = True
        except CategorizationError:
            pass
    granted = bool(
        row
        and row.enabled
        and server
        and row.accepted_server_epoch == server.epoch
        and config
        and row.accepted_configuration_fingerprint == config.fingerprint
    )
    reason = (
        "server_unavailable"
        if not available
        else "marker_required"
        if not marker_valid
        else "consent_required"
        if not granted
        else None
    )
    return SuggestionSettingsResponse(
        version=row.version if row else 0,
        enabled=row.enabled if row else False,
        effective_enabled=available and marker_valid and granted,
        available=available,
        blocked_reason=reason,
        server_epoch=server.epoch if server else 0,
        configuration_fingerprint=config.fingerprint if available and config else None,
        daily_call_limit=settings.FINANCE_SUGGESTIONS_DAILY_CALL_LIMIT,
        max_description_chars=settings.FINANCE_SUGGESTIONS_DESCRIPTION_MAX_CHARS,
        max_categories=settings.FINANCE_SUGGESTIONS_MAX_CATEGORIES,
        review_page_size=settings.FINANCE_SUGGESTIONS_REVIEW_PAGE_SIZE,
        privacy_text=PRIVACY_TEXT,
    )


async def change_suggestion_settings(
    db: AsyncSession, owner: uuid.UUID, data: SuggestionSettingsChange, *, idempotency_key: str
) -> SuggestionSettingsResponse:
    action = "suggestion_settings"
    hashed = digest(data.model_dump(mode="json"))
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext(f"suggestion-command:{owner}:{idempotency_key}")
            )
        )
    )
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == action,
            FinanceCommandReceipt.key == idempotency_key,
        )
    )
    if receipt:
        if receipt.request_hash != hashed:
            raise CategorizationError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
        return SuggestionSettingsResponse.model_validate(receipt.response_json)
    await policy_locks(db, owner)
    row = await current_consent(db, owner, lock=True)
    if (row.version if row else 0) != data.expected_version:
        raise CategorizationError("version_conflict", "Ustawienia zmieniły się.")
    await current_policy(db, lock=True)
    before = await suggestion_policy_snapshot(db, owner)
    if data.enabled:
        if not data.confirm_future_only or not data.confirm_data_export:
            raise CategorizationError(
                "confirmation_required", "Potwierdź przyszły zakres i wysyłanie danych.", 422
            )
        if not before.available:
            raise CategorizationError(
                "server_unavailable", "Generowanie propozycji AI nie jest aktywne."
            )
        if before.blocked_reason == "marker_required":
            raise CategorizationError(
                "marker_required", "Wybierz własną aktywną kategorię techniczną.", 422
            )
        if (
            data.expected_server_epoch != before.server_epoch
            or data.expected_configuration_fingerprint != before.configuration_fingerprint
        ):
            raise CategorizationError(
                "policy_changed", "Zakres AI zmienił się; sprawdź zgodę ponownie."
            )
    if row is None:
        row = Consent(user_id=owner, version=1)
        db.add(row)
    else:
        row.version += 1
    row.enabled = data.enabled
    if data.enabled:
        row.consent_at = datetime.now(UTC)
        row.accepted_server_epoch = before.server_epoch
        row.accepted_configuration_fingerprint = before.configuration_fingerprint
    await db.flush()
    response = await suggestion_policy_snapshot(db, owner)
    result = response.model_dump(mode="json")
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=action,
            key=idempotency_key,
            request_hash=hashed,
            entity_id=row.id,
            result_ids=[str(row.id)],
            version=row.version,
            response_json=result,
        )
    )
    await log_event(
        db,
        owner,
        "suggestion_settings",
        str(row.id),
        action,
        old_state=before.model_dump(mode="json"),
        new_state=result,
    )
    await db.flush()
    return response


async def set_suggestion_policy(
    db: AsyncSession,
    *,
    enabled: bool,
    expected_epoch: int,
    performed_by: uuid.UUID,
    config: SuggestionConfig | None,
) -> Policy:
    # Global policy lock never precedes owner/job/ledger mutations in this service.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("finance-suggestion-server-policy")))
    )
    row = await current_policy(db, lock=True)
    if (row.epoch if row else 0) != expected_epoch:
        raise CategorizationError("policy_changed", "Polityka AI zmieniła się.")
    actual = get_suggestion_config(settings)
    if enabled and (not config or not actual or config.fingerprint != actual.fingerprint):
        raise CategorizationError("server_unavailable", "Brak aktywnej konfiguracji finansów.")
    if row is None:
        row = Policy(id=1, epoch=1)
        db.add(row)
    else:
        row.epoch += 1
    row.enabled = enabled
    row.configuration_fingerprint = config.fingerprint if config else None
    row.changed_at = datetime.now(UTC)
    await db.flush()
    await log_event(
        db,
        performed_by,
        "categorization_llm_policy",
        "1",
        "suggestion_policy_change",
        new_state={
            "enabled": enabled,
            "epoch": row.epoch,
            "fingerprint": row.configuration_fingerprint,
        },
    )
    return row


async def reconcile_suggestion_policy(db: AsyncSession) -> None:
    """Persist observed config revocation outside all owner/job/ledger transactions.

    Never enables policy or discovers transactions. A reverted environment cannot
    resurrect a consent that was invalidated by an observed scope change.
    """
    row = await current_policy(db)
    config = get_suggestion_config(settings)
    if not row or not row.enabled or config and row.configuration_fingerprint == config.fingerprint:
        return
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext("finance-suggestion-server-policy")))
    )
    row = await current_policy(db, lock=True)
    config = get_suggestion_config(settings)
    if not row or not row.enabled or config and row.configuration_fingerprint == config.fingerprint:
        return
    before = {
        "enabled": row.enabled,
        "epoch": row.epoch,
        "fingerprint": row.configuration_fingerprint,
    }
    row.enabled = False
    row.epoch += 1
    row.configuration_fingerprint = config.fingerprint if config else None
    row.changed_at = datetime.now(UTC)
    await db.flush()
    await log_event(
        db,
        None,
        "categorization_llm_policy",
        "1",
        "suggestion_configuration_revoked",
        old_state=before,
        new_state={
            "enabled": False,
            "epoch": row.epoch,
            "fingerprint": row.configuration_fingerprint,
        },
        performed_by="system",
    )
