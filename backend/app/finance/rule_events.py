"""Creation-only enrollment and separately leased, policy-fenced ledger commands."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.finance.categorization import _write_category_parts
from app.finance.categorization_context import (
    CategorizationError,
    LedgerContext,
    build_preview,
    columns,
    digest,
    load_context,
)
from app.finance.categorization_schemas import CategorizationPart
from app.finance.models import FinanceCommandReceipt, FinancialTransaction
from app.finance.rule_event_models import TransactionRuleEvent
from app.finance.rule_models import TransactionCategorizationOrigin as Origin
from app.finance.rule_models import TransactionCategorizationRule as Rule
from app.finance.rule_models import TransactionCategorizationSettings as Policy
from app.finance.rule_policy import (
    category_path,
    get_settings,
    normalize_rule_description,
    policy_locks,
)

ACTION = "apply_approved_category_rule"
TERMINAL = frozenset({"applied", "skipped", "failed"})


def eligible_unclassified(ctx: LedgerContext, marker: uuid.UUID | None) -> bool:
    category = ctx.categories.get(marker) if marker else None
    return bool(
        marker
        and category
        and category.is_active
        and category.type == "expense"
        and ctx.txn.source == "manual"
        and ctx.eligibility().allowed
        and len(ctx.txn.postings) == 2
        and not ctx.allocations
        and not ctx.state
        and not ctx.origin
        and any(p.category_id == marker and p.account_id is None for p in ctx.txn.postings)
    )


async def record_new_expense_event(
    db: AsyncSession, user_id: uuid.UUID, transaction: FinancialTransaction
) -> uuid.UUID | None:
    """Internal creation-path hook: no commits, broker calls, row/advisory locks."""
    if (
        transaction.source != "manual"
        or transaction.type != "expense"
        or transaction.is_pending
        or len(transaction.postings) != 2
    ):
        return None
    try:
        normalized = normalize_rule_description(transaction.description)
    except CategorizationError:
        normalized = ""  # Invalid rule matcher never prevents recording a valid payment.
    observed = (
        await db.execute(
            select(Policy, Rule)
            .outerjoin(
                Rule,
                and_(
                    Rule.user_id == Policy.user_id,
                    Rule.state == "active",
                    Rule.approved_version == Rule.version,
                    Rule.normalized_description_exact == normalized,
                ),
            )
            .where(Policy.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).all()
    if not observed:
        return None
    policy = observed[0][0]
    if not policy.rules_enabled:
        return None
    ctx = await load_context(db, user_id, transaction.id)
    if not eligible_unclassified(ctx, policy.uncategorized_category_id):
        return None
    rules = [r for _, r in observed if r is not None]
    rule = rules[0] if len(rules) == 1 else None
    event_id = uuid.uuid4()
    await db.execute(
        insert(TransactionRuleEvent)
        .values(
            id=event_id,
            transaction_id=transaction.id,
            user_id=user_id,
            settings_version=policy.version,
            observed_rule_id=rule.id if rule else None,
            observed_rule_version=rule.version if rule else None,
            source_context_sha256=ctx.snapshot(),
            status="ready" if rule else "skipped",
            reason_code=None if rule else ("ambiguous" if rules else "no_match"),
            attempts=0,
        )
        .on_conflict_do_nothing(index_elements=["transaction_id"])
    )
    return await db.scalar(
        select(TransactionRuleEvent.id).where(TransactionRuleEvent.transaction_id == transaction.id)
    )


@dataclass(frozen=True)
class RuleLease:
    event_id: uuid.UUID
    owner: uuid.UUID
    token: uuid.UUID


def due_predicate(now: datetime):
    return or_(
        and_(TransactionRuleEvent.status == "ready", TransactionRuleEvent.next_attempt_at <= now),
        and_(
            TransactionRuleEvent.status == "processing", TransactionRuleEvent.lease_deadline <= now
        ),
    )


async def claim_rule_event(db: AsyncSession, event_id: uuid.UUID) -> RuleLease | None:
    event = await db.scalar(
        select(TransactionRuleEvent)
        .where(TransactionRuleEvent.id == event_id)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    now = datetime.now(UTC)
    if event is None or event.status in TERMINAL:
        return None
    if (event.status == "ready" and event.next_attempt_at > now) or (
        event.status == "processing" and event.lease_deadline and event.lease_deadline > now
    ):
        return None
    if event.attempts >= settings.FINANCE_RULE_MAX_ATTEMPTS:
        event.status, event.reason_code = "failed", "attempts_exhausted"
        event.lease_token = event.lease_deadline = None
        await db.flush()
        return None
    event.status = "processing"
    event.attempts += 1
    event.lease_token = uuid.uuid4()
    event.lease_deadline = now + timedelta(seconds=settings.FINANCE_RULE_LEASE_SECONDS)
    await db.flush()
    return RuleLease(event.id, event.user_id, event.lease_token)


async def _owned_event(db: AsyncSession, lease: RuleLease) -> TransactionRuleEvent | None:
    event = await db.scalar(
        select(TransactionRuleEvent)
        .where(
            TransactionRuleEvent.id == lease.event_id, TransactionRuleEvent.user_id == lease.owner
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        event is None
        or event.status != "processing"
        or event.lease_token != lease.token
        or event.lease_deadline is None
        or event.lease_deadline <= datetime.now(UTC)
    ):
        return None
    return event


async def _validate_grant(
    db: AsyncSession, event: TransactionRuleEvent, ctx: LedgerContext
) -> tuple[Rule | None, dict | None, str | None]:
    policy = await get_settings(db, event.user_id)
    if policy is None or not policy.rules_enabled or policy.version != event.settings_version:
        return None, None, "settings_changed"
    if ctx.state or ctx.origin:
        return None, None, "manual_protected"
    marker = (
        ctx.categories.get(policy.uncategorized_category_id)
        if policy.uncategorized_category_id
        else None
    )
    if (
        not marker
        or marker.user_id != event.user_id
        or not marker.is_active
        or marker.type != "expense"
    ):
        return None, None, "marker_invalid"
    if not eligible_unclassified(ctx, marker.id):
        return None, None, "ledger_protected"
    if ctx.snapshot() != event.source_context_sha256:
        return None, None, "input_changed"
    rule = await db.scalar(
        select(Rule)
        .where(Rule.id == event.observed_rule_id, Rule.user_id == event.user_id)
        .execution_options(populate_existing=True)
    )
    if (
        not rule
        or rule.version != event.observed_rule_version
        or rule.state != "active"
        or rule.approved_version != rule.version
        or rule.approved_for_uncategorized_category_id != marker.id
        or not rule.approval_receipt_id
    ):
        return None, None, "rule_changed"
    if normalize_rule_description(ctx.txn.description) != rule.normalized_description_exact:
        return None, None, "input_changed"
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.id == rule.approval_receipt_id,
            FinanceCommandReceipt.user_id == event.user_id,
            FinanceCommandReceipt.action == "rule_approve",
        )
    )
    grant = receipt.response_json.get("grant") if receipt else None
    if (
        not isinstance(grant, dict)
        or grant.get("rule_id") != str(rule.id)
        or grant.get("rule_version") != rule.version
        or grant.get("marker_id") != str(marker.id)
        or grant.get("target_category_id") != str(rule.target_category_id)
        or grant.get("normalized_description_exact") != rule.normalized_description_exact
        or grant.get("approved_by") != str(event.user_id)
    ):
        return None, None, "rule_changed"
    try:
        _, target_sha = await category_path(db, event.user_id, rule.target_category_id)
    except CategorizationError:
        return None, None, "target_changed"
    if (
        target_sha != rule.approved_target_sha256
        or target_sha != grant.get("target_sha256")
        or rule.target_category_id == marker.id
    ):
        return None, None, "target_changed"
    return rule, grant, None


async def apply_rule_event(db: AsyncSession, lease: RuleLease) -> str:
    """Caller commits success atomically or rolls back before separate failure CAS."""
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext(f"rule-event-command:{lease.owner}:{lease.event_id}")
            )
        )
    )
    await policy_locks(db, lease.owner)
    event = await _owned_event(db, lease)
    if event is None:
        return "lease_lost"
    try:
        ctx = await load_context(db, lease.owner, event.transaction_id, lock=True)
    except LookupError:
        event.status, event.reason_code = "skipped", "source_missing"
        await db.flush()
        return "skipped"
    rule, grant, reason = await _validate_grant(db, event, ctx)
    if reason:
        event.status, event.reason_code = "skipped", reason
        event.lease_token = event.lease_deadline = None
        await db.flush()
        return "skipped"
    assert rule is not None and grant is not None
    parts = [
        CategorizationPart(
            category_id=rule.target_category_id,
            amount_minor=next(p.source_amount for p in ctx.txn.postings if p.account_id),
        )
    ]
    build_preview(ctx, parts)
    before = [columns(p) for p in ctx.txn.postings]
    await _write_category_parts(db, ctx, parts)
    origin = Origin(
        transaction_id=ctx.txn.id,
        user_id=lease.owner,
        origin="approved_rule",
        version=1,
        rule_id=rule.id,
        rule_version=rule.version,
        approval_receipt_id=rule.approval_receipt_id,
        approval_snapshot_sha256=digest(grant),
        assignment_sha256=digest({"parts": [p.model_dump(mode="json") for p in parts]}),
    )
    db.add(origin)
    result_id = uuid.uuid4()
    receipt = FinanceCommandReceipt(
        id=result_id,
        user_id=lease.owner,
        action=ACTION,
        key=str(event.id),
        request_hash=digest({"event_id": event.id, "context": event.source_context_sha256}),
        entity_id=ctx.txn.id,
        result_ids=[str(ctx.txn.id)],
        version=1,
        response_json={
            "origin": "approved_rule",
            "rule_id": str(rule.id),
            "rule_version": rule.version,
            "approval_receipt_id": str(rule.approval_receipt_id),
        },
    )
    db.add(receipt)
    await db.flush([receipt])
    await log_event(
        db,
        lease.owner,
        "financial_transaction",
        str(ctx.txn.id),
        ACTION,
        old_state={"postings": before},
        new_state={**receipt.response_json, "postings": [columns(p) for p in ctx.txn.postings]},
    )
    event.status = "applied"
    event.reason_code = None
    event.result_receipt_id = result_id
    event.lease_token = event.lease_deadline = None
    await db.flush()
    return "applied"


async def record_rule_event_failure(db: AsyncSession, lease: RuleLease, safe_code: str) -> None:
    event = await _owned_event(db, lease)
    if event is None:
        return
    event.status = "failed" if event.attempts >= settings.FINANCE_RULE_MAX_ATTEMPTS else "ready"
    event.reason_code = "attempts_exhausted" if event.status == "failed" else "write_failed"
    delay = (
        settings.FINANCE_RULE_RETRY_INITIAL_SECONDS
        if event.attempts <= 1
        else settings.FINANCE_RULE_RETRY_LATER_SECONDS
    )
    event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
    event.lease_token = event.lease_deadline = None
    await db.flush()
