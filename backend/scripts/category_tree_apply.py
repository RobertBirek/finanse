"""Transactional category changes; caller owns commit/rollback and authorization."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.service import log_event
from app.finance import entities
from app.finance.models import Category, FinanceCommandReceipt
from app.finance.schemas import CategoryCreate, CategoryUpdate
from scripts.category_tree_guard import (
    GuardReport,
    expected_tree,
    read_tree,
    verify_after,
    verify_before,
)
from scripts.category_tree_manifest import (
    CategoryTreeError,
    Frozen,
    NewRef,
    PreparedTree,
    canonical_hash,
    tree_fingerprint,
)

ACTION = "category_tree_reorganize_v1"


class ApplyResult(Frozen):
    operation_id: UUID
    before_fingerprint: str
    after_fingerprint: str
    created_ids: dict[str, UUID]
    updated_ids: tuple[UUID, ...]
    replayed: bool


class OperationStatusReport(Frozen):
    status: Literal[
        "not_applied", "applied", "applied_state_changed", "busy_or_conflict", "receipt_conflict"
    ]
    result: ApplyResult | None = None


def request_fingerprint(owner: UUID, operation: UUID, plan: PreparedTree) -> str:
    return canonical_hash(
        {
            "version": 1,
            "owner": str(owner),
            "operation": str(operation),
            "mapping_sha": plan.mapping_sha,
            "proposal_sha": plan.proposal_sha,
            "before_fingerprint": plan.before_fingerprint,
        }
    )


async def _locks(db: AsyncSession, owner: UUID, *, wait: bool) -> bool:
    for prefix in ["actual-import", "category-tree"]:
        key = func.hashtext(f"{prefix}:{owner}")
        if wait:
            await db.execute(select(func.pg_advisory_xact_lock(key)))
        elif not await db.scalar(select(func.pg_try_advisory_xact_lock(key))):
            return False
    return True


async def _receipt(db: AsyncSession, owner: UUID, operation: UUID) -> FinanceCommandReceipt | None:
    return await db.scalar(
        select(FinanceCommandReceipt)
        .where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == ACTION,
            FinanceCommandReceipt.key == str(operation),
        )
        .execution_options(populate_existing=True)
    )


async def _audit_hash(db: AsyncSession, owner: UUID, ids: tuple[UUID, ...]) -> str:
    table = AuditEvent.__table__
    rows = (
        (
            await db.execute(
                select(table)
                .where(table.c.user_id == owner, table.c.id.in_(ids))
                .order_by(table.c.id)
            )
        )
        .mappings()
        .all()
    )
    return hashlib.sha256(
        json.dumps(
            [dict(row) for row in rows], default=str, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


async def _verified_receipt(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    operation: UUID,
    request: str,
    receipt: FinanceCommandReceipt,
) -> ApplyResult:
    if receipt.request_hash != request or request != request_fingerprint(owner, operation, plan):
        raise CategoryTreeError("receipt_conflict")
    try:
        response = receipt.response_json
        if (
            set(response) != {"version", "result", "before", "audit_ids", "audit_sha"}
            or response["version"] != 1
        ):
            raise ValueError()
        result = ApplyResult.model_validate(response["result"])
        before = GuardReport.model_validate(response["before"])
        raw_audits = response["audit_ids"]
        if not isinstance(raw_audits, list):
            raise TypeError()
        audit_ids = tuple(UUID(str(value)) for value in raw_audits)
        if (
            receipt.version != 1
            or receipt.entity_id != operation
            or result.operation_id != operation
            or result.before_fingerprint != plan.before_fingerprint
            or result.updated_ids != tuple(p.id for p in plan.patches)
            or receipt.result_ids != [str(result.created_ids[n.key]) for n in plan.creates]
            or result.after_fingerprint != tree_fingerprint(expected_tree(plan, result.created_ids))
            or len(audit_ids) != len(plan.creates) + len(plan.patches) + 1
            or len(set(audit_ids)) != len(audit_ids)
        ):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise CategoryTreeError("receipt_conflict") from None
    await verify_after(db, owner, plan, resolved_ids=result.created_ids, before=before)
    if await _audit_hash(db, owner, audit_ids) != response["audit_sha"]:
        raise CategoryTreeError("after_audit_mismatch")
    return result.model_copy(update={"replayed": True})


async def inspect_operation(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    *,
    operation_id: UUID,
    request_hash: str,
) -> OperationStatusReport:
    if db.new or db.dirty or db.deleted:
        raise CategoryTreeError("pending_session_writes")
    if request_hash != request_fingerprint(owner, operation_id, plan):
        return OperationStatusReport(status="receipt_conflict")
    if not await _locks(db, owner, wait=False):
        return OperationStatusReport(status="busy_or_conflict")
    receipt = await _receipt(db, owner, operation_id)
    if receipt is None:
        matching = tree_fingerprint(await read_tree(db, owner)) == plan.before_fingerprint
        return OperationStatusReport(status="not_applied" if matching else "busy_or_conflict")
    try:
        result = await _verified_receipt(db, owner, plan, operation_id, request_hash, receipt)
    except CategoryTreeError as error:
        return OperationStatusReport(
            status="receipt_conflict"
            if error.code == "receipt_conflict"
            else "applied_state_changed"
        )
    return OperationStatusReport(status="applied", result=result)


async def apply_tree(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    *,
    operation_id: UUID,
    expected: GuardReport,
    request_hash: str,
) -> ApplyResult:
    if db.new or db.dirty or db.deleted:
        raise CategoryTreeError("pending_session_writes")
    if request_hash != request_fingerprint(owner, operation_id, plan):
        raise CategoryTreeError("receipt_conflict")
    if (
        expected.owner_id != owner
        or expected.before_fingerprint != plan.before_fingerprint
        or expected.blockers
    ):
        raise CategoryTreeError("invalid_preflight")
    await _locks(db, owner, wait=True)
    await db.execute(
        select(Category.id).where(Category.user_id == owner).order_by(Category.id).with_for_update()
    )
    receipt = await _receipt(db, owner, operation_id)
    if receipt is not None:
        return await _verified_receipt(db, owner, plan, operation_id, request_hash, receipt)
    await verify_before(db, owner, plan, expected)
    created: dict[str, UUID] = {}
    audit_ids = []

    def resolve(parent: UUID | NewRef | None) -> UUID | None:
        return created[parent.key] if isinstance(parent, NewRef) else parent

    row: Category | None
    for node in plan.creates:
        row = await entities.create_category(
            db,
            owner,
            CategoryCreate(name=node.name, parent_id=resolve(node.parent), type="expense"),
        )
        if (
            row.user_id != owner
            or row.type != "expense"
            or row.source != "manual"
            or not row.is_active
        ):
            raise CategoryTreeError("domain_create_mismatch")
        created[node.key] = row.id
        event = await log_event(
            db,
            owner,
            "category",
            str(row.id),
            "category_tree.created",
            new_state={
                "operation_id": str(operation_id),
                "name": row.name,
                "parent_id": str(row.parent_id) if row.parent_id else None,
            },
            performed_by="operator-cli",
        )
        audit_ids.append(event.id)
    originals = {row.id: row for row in plan.source}
    for patch in plan.patches:
        changes: dict[str, Any] = {}
        if patch.name is not None:
            changes["name"] = patch.name
        if patch.parent_changed:
            changes["parent_id"] = resolve(patch.parent)
        row = await entities.update_category(db, owner, patch.id, CategoryUpdate(**changes))
        old = originals[patch.id]
        if (
            row is None
            or row.user_id != owner
            or (row.type, row.source, row.is_active) != (old.type, old.source, old.is_active)
        ):
            raise CategoryTreeError("domain_update_mismatch")
        event = await log_event(
            db,
            owner,
            "category",
            str(row.id),
            "category_tree.updated",
            old_state=old.model_dump(mode="json"),
            new_state={
                "operation_id": str(operation_id),
                "name": row.name,
                "parent_id": str(row.parent_id) if row.parent_id else None,
            },
            performed_by="operator-cli",
        )
        audit_ids.append(event.id)
    await verify_after(db, owner, plan, resolved_ids=created, before=expected)
    after = tree_fingerprint(await read_tree(db, owner))
    result = ApplyResult(
        operation_id=operation_id,
        before_fingerprint=plan.before_fingerprint,
        after_fingerprint=after,
        created_ids=created,
        updated_ids=tuple(p.id for p in plan.patches),
        replayed=False,
    )
    batch = await log_event(
        db,
        owner,
        "category_tree",
        str(operation_id),
        "category_tree.applied",
        new_state={
            "mapping_sha": plan.mapping_sha,
            "proposal_sha": plan.proposal_sha,
            "before_fingerprint": plan.before_fingerprint,
            "after_fingerprint": after,
            "created": len(created),
            "updated": len(plan.patches),
        },
        performed_by="operator-cli",
    )
    audit_ids.append(batch.id)
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=ACTION,
            key=str(operation_id),
            request_hash=request_hash,
            entity_id=operation_id,
            result_ids=[str(created[n.key]) for n in plan.creates],
            version=1,
            response_json={
                "version": 1,
                "result": result.model_dump(mode="json"),
                "before": expected.model_dump(mode="json"),
                "audit_ids": [str(ident) for ident in audit_ids],
                "audit_sha": await _audit_hash(db, owner, tuple(audit_ids)),
            },
        )
    )
    await db.flush()
    await verify_after(db, owner, plan, resolved_ids=created, before=expected)
    return result
