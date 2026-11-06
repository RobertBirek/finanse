"""Owner-scoped SELECT-only integrity guard. No settings reconciliation or grant creation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlalchemy import Table, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.main import app as _app  # noqa: F401 - full metadata, never start lifespan
from scripts.category_tree_manifest import (
    CategoryBefore,
    CategoryTreeError,
    Frozen,
    NewRef,
    PreparedTree,
    tree_fingerprint,
)


class GuardReport(Frozen):
    owner_id: UUID
    before_fingerprint: str
    reference_fingerprints: dict[str, str]
    reference_counts: dict[str, int]
    blockers: tuple[str, ...]
    actual_migration_closed: bool
    schema_revision: str
    control_ids: dict[str, tuple[UUID, ...]] = Field(default_factory=dict)


_CATEGORY_REFS = frozenset(
    {
        ("categories", "parent_id"),
        ("postings", "category_id"),
        ("category_budgets", "category_id"),
        ("scheduled_finance_items", "category_id"),
        ("financial_documents", "category_id"),
        ("receipt_item_lines", "category_id"),
        ("transaction_categorization_settings", "uncategorized_category_id"),
        ("transaction_categorization_rules", "target_category_id"),
        ("transaction_categorization_rules", "approved_for_uncategorized_category_id"),
        ("categorization_proposal_items", "target_category_id"),
    }
)
_OWNER_TABLES = frozenset(
    {
        "accounts",
        "finance_settings",
        "financial_transactions",
        "postings",
        "transaction_date_metadata",
        "actual_import_mappings",
        "category_budgets",
        "scheduled_finance_items",
        "financial_documents",
        "financial_document_sources",
        "document_payment_allocations",
        "recurring_occurrence_coverages",
        "loan_agreements",
        "loan_installments",
        "loan_payment_links",
        "transaction_categorization_states",
        "transaction_categorization_settings",
        "transaction_categorization_rules",
        "transaction_categorization_origins",
        "transaction_rule_events",
        "categorization_suggestion_settings",
        "categorization_suggestion_jobs",
        "categorization_llm_usage_reservations",
        "categorization_proposal_items",
        "receipt_stores",
        "receipt_item_states",
        "receipt_item_revisions",
        "receipt_item_lines",
        "receipt_item_discounts",
        "receipt_item_discount_shares",
        "receipt_read_lineage",
        "documents",
        "document_texts",
        "document_extraction_revisions",
        "document_processing_jobs",
        "document_vision_usage",
        "receipt_read_streams",
        "receipt_read_jobs",
        "receipt_read_extractions",
        "receipt_read_reservations",
        "receipt_read_usage",
        "audit_events",
        "finance_command_receipts",
    }
)
_GLOBAL_TABLES = frozenset(
    {"document_vision_policy", "receipt_read_policy", "categorization_llm_policy"}
)
_CONTROLS = frozenset({"audit_events", "finance_command_receipts"})
_EVIDENCE = {
    "rule_evidence": frozenset(
        {
            "transaction_categorization_rules",
            "transaction_categorization_origins",
            "categorization_proposal_items",
        }
    ),
    "receipt_evidence": frozenset(
        {
            "receipt_item_states",
            "receipt_item_revisions",
            "receipt_item_lines",
            "receipt_item_discounts",
            "receipt_item_discount_shares",
            "receipt_read_lineage",
        }
    ),
}


def _no_pending(db: AsyncSession) -> None:
    if db.new or db.dirty or db.deleted:
        raise CategoryTreeError("pending_session_writes")


def _owner_clause(table: Table, owner: UUID) -> Any:
    if "user_id" in table.c:
        return table.c.user_id == owner
    if table.name == "postings":
        tx = Base.metadata.tables["financial_transactions"]
        return table.c.transaction_id.in_(select(tx.c.id).where(tx.c.user_id == owner))
    if table.name == "document_texts":
        docs = Base.metadata.tables["documents"]
        return table.c.document_id.in_(select(docs.c.id).where(docs.c.user_id == owner))
    if table.name == "receipt_read_usage":
        return table.c.scope_key.in_(["global", f"user:{owner}"])
    if table.name in _GLOBAL_TABLES:
        return True
    raise CategoryTreeError("unregistered_reference_scope")


async def read_tree(db: AsyncSession, owner: UUID) -> tuple[CategoryBefore, ...]:
    table = Base.metadata.tables["categories"]
    cols = [table.c[name] for name in ["id", "parent_id", "name", "type", "source", "is_active"]]
    rows = (
        (await db.execute(select(*cols).where(table.c.user_id == owner).order_by(table.c.id)))
        .mappings()
        .all()
    )
    try:
        return tuple(CategoryBefore.model_validate(dict(row)) for row in rows)
    except ValueError:
        raise CategoryTreeError("invalid_current_tree") from None


async def _references(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    control_ids: Mapping[str, tuple[UUID, ...]] | None = None,
) -> tuple[dict[str, str], dict[str, int], dict[str, tuple[UUID, ...]]]:
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    ids: dict[str, tuple[UUID, ...]] = {}
    for name in sorted(_OWNER_TABLES | _GLOBAL_TABLES):
        table = Base.metadata.tables[name]
        query = (
            select(table).where(_owner_clause(table, owner)).order_by(*table.primary_key.columns)
        )
        if control_ids is not None and name in _CONTROLS:
            if name not in control_ids:
                raise CategoryTreeError("incomplete_reference_proof")
            query = query.where(table.c.id.in_(control_ids[name]))
        rows = (await db.execute(query)).mappings().all()
        # Never expose these rows; only exact-type DB projections' fingerprints.
        payload = json.dumps(
            [dict(row) for row in rows],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            ensure_ascii=False,
        ).encode()
        hashes[name] = hashlib.sha256(payload).hexdigest()
        counts[name] = len(rows)
        if name in _CONTROLS:
            ids[name] = tuple(row["id"] for row in rows)
    categories = Base.metadata.tables["categories"]
    query = (
        select(
            categories.c.id,
            categories.c.user_id,
            categories.c.type,
            categories.c.source,
            categories.c.is_active,
            categories.c.created_at,
            case(
                (categories.c.id.in_([p.id for p in plan.patches]), None),
                else_=categories.c.updated_at,
            ).label("protected_updated_at"),
        )
        .where(categories.c.user_id == owner, categories.c.id.in_([r.id for r in plan.source]))
        .order_by(categories.c.id)
    )
    immutable = (await db.execute(query)).mappings().all()
    payload = json.dumps(
        [dict(row) for row in immutable], sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    hashes["categories_immutable"] = hashlib.sha256(payload).hexdigest()
    counts["categories_immutable"] = len(immutable)
    return hashes, counts, ids


async def _integrity_blockers(db: AsyncSession, owner: UUID, ids: list[UUID]) -> set[str]:
    blockers: set[str] = set()
    model_refs = frozenset(
        (t.name, f.parent.name)
        for t in Base.metadata.tables.values()
        for f in t.foreign_keys
        if f.target_fullname == "categories.id"
    )
    catalog = (
        await db.execute(
            text("""
        SELECT child.relname AS table_name, a.attname AS column_name
        FROM pg_constraint c
        JOIN pg_class child ON child.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=child.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
        WHERE c.contype='f' AND c.confrelid=to_regclass('categories')
          AND n.nspname=current_schema()
    """)
        )
    ).all()
    if model_refs != _CATEGORY_REFS or frozenset(tuple(row) for row in catalog) != _CATEGORY_REFS:
        blockers.add("unregistered_category_reference")
    for table_name, col in _CATEGORY_REFS:
        table = Base.metadata.tables[table_name]
        if table_name == "postings":
            tx = Base.metadata.tables["financial_transactions"]
            query = (
                select(func.count())
                .select_from(table.join(tx, table.c.transaction_id == tx.c.id))
                .where(table.c[col].in_(ids), tx.c.user_id != owner)
            )
        else:
            query = (
                select(func.count())
                .select_from(table)
                .where(table.c[col].in_(ids), table.c.user_id != owner)
            )
        if await db.scalar(query):
            blockers.add("foreign_reference")
    actual = Base.metadata.tables["actual_import_mappings"]
    if await db.scalar(
        select(func.count())
        .select_from(actual)
        .where(
            actual.c.entity_type.in_(["category", "category_group"]),
            actual.c.entity_id.in_(ids),
            actual.c.user_id != owner,
        )
    ):
        blockers.add("foreign_reference")
    return blockers


async def _work_blockers(db: AsyncSession, owner: UUID, counts: Mapping[str, int]) -> set[str]:
    blockers = {code for code, tables in _EVIDENCE.items() if any(counts[name] for name in tables)}
    if counts["categorization_suggestion_settings"]:
        blockers.add("suggestion_consent")
    settings = Base.metadata.tables["transaction_categorization_settings"]
    if await db.scalar(
        select(func.count())
        .select_from(settings)
        .where(
            settings.c.user_id == owner,
            (settings.c.uncategorized_category_id.is_not(None))
            | (settings.c.rules_enabled.is_(True)),
        )
    ):
        blockers.add("marker_configured")
    active = {
        "document_processing_jobs": ("state", ["pending", "processing"]),
        "documents": ("status", ["pending", "processing"]),
        "receipt_read_jobs": ("state", ["pending", "preparing", "dispatched"]),
        "categorization_suggestion_jobs": (
            "status",
            ["ready", "preparing", "reserved", "dispatching"],
        ),
        "transaction_rule_events": ("status", ["ready", "processing"]),
    }
    for name, (col, states) in active.items():
        table = Base.metadata.tables[name]
        if await db.scalar(
            select(func.count())
            .select_from(table)
            .where(table.c.user_id == owner, table.c[col].in_(states))
        ):
            blockers.add("active_work")
    tx = Base.metadata.tables["financial_transactions"]
    post = Base.metadata.tables["postings"]
    invalid = (
        select(tx.c.id)
        .select_from(tx.outerjoin(post, tx.c.id == post.c.transaction_id))
        .where(tx.c.user_id == owner)
        .group_by(tx.c.id)
        .having(func.count(post.c.id) < 2)
    )
    # Balance check uses exact signed BIGINT, never floating-point amounts.
    invalid_balance = (
        select(tx.c.id)
        .select_from(tx.join(post, tx.c.id == post.c.transaction_id))
        .where(tx.c.user_id == owner)
        .group_by(tx.c.id)
        .having(
            func.sum(
                case(
                    (post.c.direction == "debit", post.c.base_amount_pln),
                    else_=-post.c.base_amount_pln,
                )
            )
            != 0
        )
    )
    if (await db.execute(invalid.limit(1))).first() or (
        await db.execute(invalid_balance.limit(1))
    ).first():
        blockers.add("ledger_invariant")
    return blockers


async def preflight(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    *,
    actual_migration_closed: bool,
) -> GuardReport:
    _no_pending(db)
    rows = await read_tree(db, owner)
    hashes, counts, control_ids = await _references(db, owner, plan)
    counts["categories"] = len(rows)
    blockers = await _integrity_blockers(db, owner, [row.id for row in rows])
    if not actual_migration_closed:
        blockers.add("actual_migration_open")
    fingerprint = tree_fingerprint(rows)
    if fingerprint != plan.before_fingerprint:
        blockers.add("tree_changed")
    users = Base.metadata.tables["users"]
    if not await db.scalar(
        select(users.c.id).where(users.c.id == owner, users.c.is_active.is_(True))
    ):
        blockers.add("owner_missing")
    schema = await db.scalar(text("SELECT version_num FROM alembic_version"))
    if schema != plan.schema_revision:
        blockers.add("schema_changed")
    blockers.update(await _work_blockers(db, owner, counts))
    return GuardReport(
        owner_id=owner,
        before_fingerprint=fingerprint,
        reference_fingerprints=hashes,
        reference_counts=counts,
        blockers=tuple(sorted(blockers)),
        actual_migration_closed=actual_migration_closed,
        schema_revision=schema,
        control_ids=control_ids,
    )


async def verify_before(
    db: AsyncSession, owner: UUID, plan: PreparedTree, expected: GuardReport
) -> None:
    current = await preflight(
        db, owner, plan, actual_migration_closed=expected.actual_migration_closed
    )
    if expected.owner_id != owner or expected.blockers or current != expected:
        raise CategoryTreeError("preflight_changed")


def expected_tree(
    plan: PreparedTree, resolved_ids: Mapping[str, UUID]
) -> tuple[CategoryBefore, ...]:
    if set(resolved_ids) != {node.key for node in plan.creates} or len(
        set(resolved_ids.values())
    ) != len(plan.creates):
        raise CategoryTreeError("invalid_created_ids")
    if set(resolved_ids.values()) & {row.id for row in plan.source}:
        raise CategoryTreeError("invalid_created_ids")

    def resolve(parent: UUID | NewRef | None) -> UUID | None:
        return resolved_ids[parent.key] if isinstance(parent, NewRef) else parent

    changes = {p.id: p for p in plan.patches}
    rows = []
    for before in plan.source:
        patch = changes.get(before.id)
        row = before
        if patch:
            row = before.model_copy(
                update={
                    "name": patch.name if patch.name is not None else before.name,
                    "parent_id": resolve(patch.parent)
                    if patch.parent_changed
                    else before.parent_id,
                }
            )
        rows.append(row)
    for node in plan.creates:
        rows.append(
            CategoryBefore(
                id=resolved_ids[node.key],
                parent_id=resolve(node.parent),
                name=node.name,
                type="expense",
                source="manual",
                is_active=True,
            )
        )
    return tuple(rows)


async def verify_after(
    db: AsyncSession,
    owner: UUID,
    plan: PreparedTree,
    *,
    resolved_ids: Mapping[str, UUID],
    before: GuardReport,
) -> None:
    _no_pending(db)
    expected = expected_tree(plan, resolved_ids)
    actual = await read_tree(db, owner)
    if (
        before.owner_id != owner
        or before.blockers
        or tree_fingerprint(actual) != tree_fingerprint(expected)
    ):
        raise CategoryTreeError("after_tree_mismatch")
    hashes, counts, _ = await _references(db, owner, plan, before.control_ids)
    expected_counts = {
        key: value for key, value in before.reference_counts.items() if key != "categories"
    }
    if hashes != before.reference_fingerprints or counts != expected_counts:
        raise CategoryTreeError("after_reference_mismatch")
    if await _integrity_blockers(db, owner, [row.id for row in actual]):
        raise CategoryTreeError("after_integrity_mismatch")
    if await _work_blockers(db, owner, counts):
        raise CategoryTreeError("after_work_mismatch")
    if await db.scalar(text("SELECT version_num FROM alembic_version")) != before.schema_revision:
        raise CategoryTreeError("schema_changed")
