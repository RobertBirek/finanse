"""Small owner-approved category commands; model output is never ledger authority."""

import base64
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.finance.categorization import _record_human_assignment, _write_category_parts
from app.finance.categorization_context import (
    CategorizationError,
    LedgerContext,
    build_preview,
    columns,
    digest,
    load_context,
)
from app.finance.categorization_schemas import CategorizationPart
from app.finance.models import FinanceCommandReceipt
from app.finance.proposal_context import load_proposal_contexts, project_proposal
from app.finance.proposal_schemas import (
    ProposalApply,
    ProposalDecision,
    ProposalDetail,
    ProposalPage,
    ProposalPreview,
    ProposalVersion,
)
from app.finance.proposal_state import supersede_pending_proposals
from app.finance.rule_policy import get_settings, policy_locks
from app.finance.suggestion_models import (
    CategorizationProposalItem as Item,
)
from app.finance.suggestion_models import (
    CategorizationSuggestionJob as Job,
)

ACTION = "apply_reviewed_category_proposal"


async def owned_proposal(
    db: AsyncSession, owner: uuid.UUID, proposal_id: uuid.UUID, *, lock: bool = False
) -> Item:
    stmt = (
        select(Item)
        .where(Item.id == proposal_id, Item.user_id == owner)
        .execution_options(populate_existing=True)
    )
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise LookupError("Proposal not found")
    return row


async def list_proposals(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    state: str = "pending",
    cursor: str | None = None,
    limit: int | None = None,
) -> ProposalPage:
    bound = settings.FINANCE_SUGGESTIONS_REVIEW_PAGE_SIZE
    size = min(limit or bound, bound)
    query = select(Item).where(Item.user_id == owner, Item.status == state)
    if cursor:
        try:
            raw = json.loads(base64.urlsafe_b64decode(cursor))
            if (
                not isinstance(raw, list)
                or len(raw) != 2
                or not all(isinstance(v, str) for v in raw)
            ):
                raise ValueError("Invalid cursor shape")
            created, identifier = datetime.fromisoformat(raw[0]), uuid.UUID(raw[1])
            if created.tzinfo is None:
                raise ValueError("Timezone required")
        except (ValueError, TypeError, IndexError, json.JSONDecodeError) as error:
            raise CategorizationError(
                "invalid_cursor", "Nieprawidłowa strona propozycji.", 422
            ) from error
        query = query.where(tuple_(Item.created_at, Item.id) > (created, identifier))
    rows = list((await db.scalars(query.order_by(Item.created_at, Item.id).limit(size + 1))).all())
    more = len(rows) > size
    rows = rows[:size]
    contexts = await load_proposal_contexts(
        db, owner, [i.transaction_id for i in rows if i.transaction_id]
    )
    rules = await get_settings(db, owner)
    marker = rules.uncategorized_category_id if rules else None
    next_cursor = (
        base64.urlsafe_b64encode(
            json.dumps([rows[-1].created_at.isoformat(), str(rows[-1].id)]).encode()
        ).decode()
        if more
        else None
    )
    return ProposalPage(
        items=[
            project_proposal(
                i, contexts.get(i.transaction_id) if i.transaction_id else None, marker
            )
            for i in rows
        ],
        next_cursor=next_cursor,
        page_size=size,
    )


async def get_proposal(
    db: AsyncSession, owner: uuid.UUID, proposal_id: uuid.UUID
) -> ProposalDetail:
    row = await owned_proposal(db, owner, proposal_id)
    contexts = await load_proposal_contexts(
        db, owner, [row.transaction_id] if row.transaction_id else []
    )
    rules = await get_settings(db, owner)
    return project_proposal(
        row,
        contexts.get(row.transaction_id) if row.transaction_id else None,
        rules.uncategorized_category_id if rules else None,
    )


async def checked_preview(
    db: AsyncSession, owner: uuid.UUID, row: Item, version: int
) -> tuple[LedgerContext, ProposalPreview]:
    if row.version != version:
        raise CategorizationError("version_conflict", "Propozycja zmieniła się.")
    if row.transaction_id is None:
        raise CategorizationError("source_missing", "Płatność już nie istnieje.")
    try:
        ctx = await load_context(db, owner, row.transaction_id, lock=True)
    except LookupError as error:
        raise CategorizationError("source_missing", "Płatność już nie istnieje.") from error
    rules = await get_settings(db, owner)
    detail = project_proposal(row, ctx, rules.uncategorized_category_id if rules else None)
    if not detail.eligible:
        reason = detail.blocked_reason or "proposal_blocked"
        raise CategorizationError(
            reason,
            "Propozycja wymaga ręcznego sprawdzenia.",
            422 if reason == "manual_category_required" else 409,
        )
    assert row.target_category_id and detail.amount_minor and detail.target_path
    parts = [
        CategorizationPart(category_id=row.target_category_id, amount_minor=detail.amount_minor)
    ]
    native = build_preview(ctx, parts)
    token = digest(
        {
            "proposal_id": row.id,
            "version": row.version,
            "source": ctx.snapshot(),
            "taxonomy": row.taxonomy_sha256,
            "target": row.target_category_id,
            "expires_at": row.expires_at,
            "native_preview": native.preview_snapshot,
        }
    )
    return ctx, ProposalPreview(
        proposal_id=row.id,
        expected_version=row.version,
        source_version=ctx.response().version,
        context_snapshot=ctx.snapshot(),
        preview_snapshot=token,
        amount_minor=detail.amount_minor,
        before_parts=native.before_parts,
        after_parts=parts,
        target_path=detail.target_path,
        explanation=row.explanation,
        confidence=row.confidence,
        expires_at=row.expires_at,
    )


async def preview_proposal(
    db: AsyncSession, owner: uuid.UUID, proposal_id: uuid.UUID, data: ProposalVersion
) -> ProposalPreview:
    await owned_proposal(db, owner, proposal_id)
    await policy_locks(db, owner)
    row = await owned_proposal(db, owner, proposal_id, lock=True)
    _, preview = await checked_preview(db, owner, row, data.expected_version)
    return preview


async def receipt_replay(
    db: AsyncSession,
    owner: uuid.UUID,
    proposal_id: uuid.UUID,
    action: str,
    data: ProposalVersion,
    key: str,
) -> tuple[str, ProposalDecision | None]:
    await owned_proposal(db, owner, proposal_id)
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"proposal-command:{owner}:{key}")))
    )
    request = digest({"proposal_id": proposal_id, "data": data.model_dump(mode="json")})
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == action,
            FinanceCommandReceipt.key == key,
        )
    )
    if receipt:
        if receipt.request_hash != request:
            raise CategorizationError("idempotency_key_reused", "Klucz dotyczy innej decyzji.")
        return request, ProposalDecision.model_validate(receipt.response_json)
    return request, None


async def apply_proposal(
    db: AsyncSession,
    owner: uuid.UUID,
    proposal_id: uuid.UUID,
    data: ProposalApply,
    *,
    idempotency_key: str,
) -> ProposalDecision:
    hashed, replay = await receipt_replay(db, owner, proposal_id, ACTION, data, idempotency_key)
    if replay:
        return replay
    await policy_locks(db, owner)
    row = await owned_proposal(db, owner, proposal_id, lock=True)
    ctx, preview = await checked_preview(db, owner, row, data.expected_version)
    if preview.preview_snapshot != data.preview_snapshot:
        raise CategorizationError(
            "preview_conflict", "Podgląd zmienił się; sprawdź propozycję ponownie."
        )
    job = await db.scalar(select(Job).where(Job.id == row.job_id, Job.user_id == owner))
    if not job:
        raise CategorizationError("generation_missing", "Brakuje dowodu pochodzenia propozycji.")
    grant = {
        "proposal_id": str(row.id),
        "proposal_version": row.version,
        "job_id": str(job.id),
        "display_description": row.generated_description,
        "target_category_id": str(row.target_category_id),
        "target_path": preview.target_path,
        "preview_snapshot": preview.preview_snapshot,
        "approved_by": str(owner),
        "approved_at": datetime.now(UTC).isoformat(),
        "configuration_fingerprint": job.configuration_fingerprint,
        "model": job.packet_json.get("model") if job.packet_json else None,
        "prompt_sha256": digest(
            {"instructions": job.packet_json.get("instructions") if job.packet_json else None}
        ),
        "schema_sha256": digest({"text": job.packet_json.get("text") if job.packet_json else None}),
        "request_sha256": row.request_sha256,
    }
    receipt = FinanceCommandReceipt(
        id=uuid.uuid4(),
        user_id=owner,
        action=ACTION,
        key=idempotency_key,
        request_hash=hashed,
        entity_id=ctx.txn.id,
        result_ids=[str(row.id), str(ctx.txn.id)],
        version=row.version + 1,
        response_json={},
    )
    db.add(receipt)
    await db.flush([receipt])
    before = ctx.response()
    old_postings = [columns(p) for p in ctx.txn.postings]
    await _write_category_parts(db, ctx, preview.after_parts)
    await _record_human_assignment(
        db,
        ctx,
        before=before,
        parts=preview.after_parts,
        origin="approved_llm",
        proposal_id=row.id,
        approval_receipt_id=receipt.id,
        approval_snapshot_sha256=digest(grant),
    )
    ctx.origin_grant = grant
    row.status, row.approval_receipt_id = "approved", receipt.id
    row.version += 1
    await supersede_pending_proposals(db, owner, ctx.txn.id, except_proposal_id=row.id)
    await db.flush()
    response = ProposalDecision(
        proposal_id=row.id,
        version=row.version,
        status="approved",
        context=ctx.response(),
        grant=grant,
    )
    receipt.response_json = response.model_dump(mode="json")
    await log_event(
        db,
        owner,
        "financial_transaction",
        str(ctx.txn.id),
        ACTION,
        old_state={"postings": old_postings, "snapshot": before.context_snapshot},
        new_state={
            "postings": [columns(p) for p in ctx.txn.postings],
            "grant": grant,
            "proposal_id": str(row.id),
        },
    )
    await db.flush()
    return response


async def reject_proposal(
    db: AsyncSession,
    owner: uuid.UUID,
    proposal_id: uuid.UUID,
    data: ProposalVersion,
    *,
    idempotency_key: str,
) -> ProposalDecision:
    action = "reject_category_proposal"
    hashed, replay = await receipt_replay(db, owner, proposal_id, action, data, idempotency_key)
    if replay:
        return replay
    await policy_locks(db, owner)
    row = await owned_proposal(db, owner, proposal_id, lock=True)
    if row.version != data.expected_version or row.status not in {"pending", "expired"}:
        raise CategorizationError("version_conflict", "Propozycja zmieniła się.")
    row.status = "rejected"
    row.version += 1
    response = ProposalDecision(proposal_id=row.id, version=row.version, status="rejected")
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=action,
            key=idempotency_key,
            request_hash=hashed,
            entity_id=row.id,
            result_ids=[str(row.id)],
            version=row.version,
            response_json=response.model_dump(mode="json"),
        )
    )
    await log_event(
        db,
        owner,
        "categorization_proposal",
        str(row.id),
        action,
        new_state={"version": row.version, "status": row.status},
    )
    await db.flush()
    return response
