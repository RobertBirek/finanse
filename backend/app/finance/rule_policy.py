"""Owner-scoped, versioned approval of future-only exact-description rules."""

import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.finance.categorization_context import CategorizationError, columns, digest
from app.finance.document_guards import lock_document_mutations
from app.finance.models import Category, FinanceCommandReceipt
from app.finance.rule_models import TransactionCategorizationRule as Rule
from app.finance.rule_models import TransactionCategorizationSettings as Policy


def normalize_rule_description(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if (
        not normalized
        or max(len(value), len(normalized)) > settings.FINANCE_RULE_DESCRIPTION_MAX_CHARS
    ):
        raise CategorizationError(
            "invalid_description", "Podaj niepusty opis w dozwolonym limicie.", 422
        )
    return normalized


async def policy_locks(db: AsyncSession, owner: uuid.UUID) -> None:
    await lock_document_mutations(db, owner)
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"category-tree:{owner}"))))


async def get_settings(db: AsyncSession, owner: uuid.UUID) -> Policy | None:
    return await db.scalar(
        select(Policy).where(Policy.user_id == owner).execution_options(populate_existing=True)
    )


def settings_response(row: Policy | None) -> dict[str, Any]:
    return {
        "version": row.version if row else 0,
        "uncategorized_category_id": str(row.uncategorized_category_id)
        if row and row.uncategorized_category_id
        else None,
        "rules_enabled": row.rules_enabled if row else False,
        "max_description_chars": settings.FINANCE_RULE_DESCRIPTION_MAX_CHARS,
    }


async def category_path(
    db: AsyncSession, owner: uuid.UUID, target: uuid.UUID | None
) -> tuple[str, str]:
    cats = {
        c.id: c
        for c in (
            await db.scalars(
                select(Category)
                .where(Category.user_id == owner)
                .order_by(Category.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    path = []
    seen = set()
    while target:
        c = cats.get(target)
        if c is None or not c.is_active or c.type != "expense" or target in seen:
            raise CategorizationError(
                "invalid_category", "Wybierz własną aktywną kategorię wydatków.", 422
            )
        seen.add(target)
        path.append(c)
        target = c.parent_id
    if not path:
        raise CategorizationError("invalid_category", "Wybierz kategorię techniczną.", 422)
    return " / ".join(c.name for c in reversed(path)), digest(
        {"path": [columns(c) for c in reversed(path)]}
    )


async def get_rule(db: AsyncSession, owner: uuid.UUID, rule_id: uuid.UUID) -> Rule:
    row = await db.scalar(
        select(Rule)
        .where(Rule.id == rule_id, Rule.user_id == owner)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise LookupError("Rule not found")
    return row


def rule_response(row: Rule) -> dict[str, Any]:
    return columns(row)


async def rule_preview(db: AsyncSession, owner: uuid.UUID, row: Rule) -> dict[str, Any]:
    policy = await get_settings(db, owner)
    if policy is None or policy.uncategorized_category_id is None:
        raise CategorizationError("marker_required", "Wybierz najpierw kategorię techniczną.", 422)
    await category_path(db, owner, policy.uncategorized_category_id)
    if row.target_category_id == policy.uncategorized_category_id:
        raise CategorizationError(
            "invalid_category", "Kategoria docelowa musi różnić się od technicznej.", 422
        )
    path, target_sha = await category_path(db, owner, row.target_category_id)
    grant = {
        "rule_id": str(row.id),
        "rule_version": row.version,
        "display_description": row.display_description,
        "normalized_description_exact": row.normalized_description_exact,
        "marker_id": str(policy.uncategorized_category_id),
        "target_category_id": str(row.target_category_id),
        "target_path": path,
        "target_sha256": target_sha,
        "scope": "future_manual_pln_only",
        "settings_version": policy.version,
    }
    return {"grant": grant, "preview_snapshot": digest(grant)}


async def command(
    db: AsyncSession,
    owner: uuid.UUID,
    action: str,
    payload: dict[str, Any],
    key: str,
    rule_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    if rule_id:
        await get_rule(db, owner, rule_id)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"rule-command:{owner}:{key}")))
    )
    hashed = digest({"rule_id": rule_id, "payload": payload})
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == action,
            FinanceCommandReceipt.key == key,
        )
    )
    if receipt:
        if receipt.request_hash != hashed:
            raise CategorizationError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
        return receipt.response_json
    await policy_locks(db, owner)
    receipt_id = uuid.uuid4()
    grant: dict[str, Any] | None = None
    before: dict[str, Any] | None
    rule: Rule | None = None
    if action == "rule_settings":
        if payload["confirm_future_only"] is not True:
            raise CategorizationError(
                "confirmation_required", "Potwierdź zakres przyszłych wydatków.", 422
            )
        row = await get_settings(db, owner)
        if (row.version if row else 0) != payload["expected_version"]:
            raise CategorizationError("version_conflict", "Ustawienia zmieniły się.")
        marker = (
            uuid.UUID(payload["uncategorized_category_id"])
            if payload["uncategorized_category_id"]
            else None
        )
        if marker or payload["rules_enabled"]:
            await category_path(db, owner, marker)
        before = settings_response(row)
        if row is None:
            row = Policy(user_id=owner, version=1)
            db.add(row)
        else:
            row.version += 1
        row.uncategorized_category_id = marker
        row.rules_enabled = payload["rules_enabled"]
        await db.flush()
        result = settings_response(row)
        entity_id = row.id
    else:
        rule = await get_rule(db, owner, rule_id) if rule_id else None
        before = rule_response(rule) if rule else None
        if rule and (rule.version != payload["expected_version"] or rule.state == "retired"):
            raise CategorizationError(
                "version_conflict", "Reguła zmieniła się lub została wycofana."
            )
        if action in {"rule_create", "rule_edit"}:
            normalized = normalize_rule_description(payload["display_description"])
            target = uuid.UUID(payload["target_category_id"])
            await category_path(db, owner, target)
            policy = await get_settings(db, owner)
            if policy and policy.uncategorized_category_id == target:
                raise CategorizationError(
                    "invalid_category", "Wybierz kategorię inną niż techniczna.", 422
                )
            if rule is None:
                rule = Rule(user_id=owner, version=1)
                db.add(rule)
            else:
                rule.version += 1
            rule.display_description = payload["display_description"]
            rule.normalized_description_exact = normalized
            rule.target_category_id = target
            rule.state = "draft"
        elif action == "rule_approve" and rule:
            if rule.state == "active":
                raise CategorizationError(
                    "version_conflict", "Wstrzymaj lub zmień regułę przed ponownym zatwierdzeniem."
                )
            if payload["confirm_future_only"] is not True:
                raise CategorizationError(
                    "confirmation_required", "Potwierdź przyszły zakres reguły.", 422
                )
            try:
                preview = await rule_preview(db, owner, rule)
            except CategorizationError as error:
                raise CategorizationError(
                    "target_changed", "Kategorie zmieniły się; sprawdź regułę ponownie."
                ) from error
            if preview["preview_snapshot"] != payload["preview_snapshot"]:
                raise CategorizationError("preview_conflict", "Podgląd jest nieaktualny.")
            duplicate = await db.scalar(
                select(Rule.id).where(
                    Rule.user_id == owner,
                    Rule.state == "active",
                    Rule.normalized_description_exact == rule.normalized_description_exact,
                    Rule.id != rule.id,
                )
            )
            if duplicate:
                raise CategorizationError("ambiguous_rule", "Istnieje aktywna reguła tego opisu.")
            grant = preview["grant"]
            grant.update({"approved_by": str(owner), "approved_at": datetime.now(UTC).isoformat()})
            rule.state = "active"
            rule.approved_version = rule.version
            rule.approved_at = datetime.now(UTC)
            rule.approved_for_uncategorized_category_id = uuid.UUID(grant["marker_id"])
            rule.approved_target_sha256 = grant["target_sha256"]
            # Insert receipt before flushing the rule's immediate FK below.
        elif rule and action in {"rule_pause", "rule_retire"}:
            rule.state = "paused" if action == "rule_pause" else "retired"
            rule.version += 1
        else:
            raise ValueError("Unknown categorization command")
        if grant:
            with db.no_autoflush:
                result = rule_response(rule)
            result["approval_receipt_id"] = str(receipt_id)
            result["grant"] = grant
        else:
            await db.flush()
            await db.refresh(rule, attribute_names=["updated_at"])
            result = rule_response(rule)
        entity_id = rule.id
    receipt = FinanceCommandReceipt(
        id=receipt_id,
        user_id=owner,
        action=action,
        key=key,
        request_hash=hashed,
        entity_id=entity_id,
        result_ids=[str(entity_id)],
        version=result["version"],
        response_json=result,
    )
    if grant:
        assert rule is not None
        # Disable autoflush: active rule's FK/check must be set only after receipt exists.
        db.add(receipt)
        await db.flush([receipt])
        rule.approval_receipt_id = receipt_id
    else:
        db.add(receipt)
    await db.flush()
    if grant:
        assert rule is not None
        await db.refresh(rule, attribute_names=["updated_at"])
        result = {**rule_response(rule), "grant": grant}
        receipt.response_json = result
    await log_event(
        db, owner, "categorization_rule", str(entity_id), action, old_state=before, new_state=result
    )
    await db.flush()
    return result
