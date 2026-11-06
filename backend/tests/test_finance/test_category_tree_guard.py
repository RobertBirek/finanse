import importlib
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base
from app.finance.models import Category
from app.finance.receipt_models import ReceiptItemState
from app.finance.rule_models import (
    TransactionCategorizationOrigin,
    TransactionCategorizationRule,
    TransactionCategorizationSettings,
)
from app.finance.suggestion_models import (
    CategorizationSuggestionJob,
    CategorizationSuggestionSettings,
)
from scripts.category_tree_manifest import compile_tree, load_bundle
from tests.test_finance.category_tree_cases import cases, uid, write_bundle
from tests.test_finance.category_tree_database import (
    apply_categories_only,
    seed_ordinary_refs,
    seed_owner,
    test_database,  # noqa: F401 - module-local override
)

pytestmark = pytest.mark.integration


def guard() -> Any:
    return importlib.import_module("scripts.category_tree_guard")


def prepared(tmp_path: Path) -> Any:
    return compile_tree(load_bundle(tmp_path, **write_bundle(tmp_path, *cases())))


async def test_preflight_is_owner_scoped_read_only_and_creates_nothing(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    other = await seed_owner(db_session, source_tree=False)
    db_session.add(Category(user_id=other, name="Other owner", type="expense"))
    await db_session.commit()
    await db_session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    before = {}
    for name in [
        "categories",
        "audit_events",
        "finance_command_receipts",
        "transaction_categorization_settings",
        "categorization_suggestion_settings",
    ]:
        before[name] = await db_session.scalar(text(f"SELECT count(*) FROM {name}"))
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert report.blockers == ()
    assert report.owner_id == owner
    assert report.reference_counts["categories"] == 65
    assert await db_session.scalar(text("SELECT current_setting('transaction_read_only')")) == "on"
    for name, count in before.items():
        assert await db_session.scalar(text(f"SELECT count(*) FROM {name}")) == count
    await db_session.rollback()


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "changed"),
        ("parent_id", None),
        ("source", "manual"),
        ("is_active", False),
        ("extra", True),
    ],
)
async def test_stale_tree_name_parent_source_active_or_extra_category_blocks(
    db_session: AsyncSession, tmp_path: Path, field: str, value: Any
) -> None:
    owner = await seed_owner(db_session)
    if field == "extra":
        db_session.add(Category(user_id=owner, name="New", type="expense"))
    else:
        setattr(await db_session.get(Category, uid(0)), field, value)
    await db_session.commit()
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert "tree_changed" in report.blockers


async def test_existing_budget_schedule_bill_posting_and_import_refs_are_counted_and_retained(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    await seed_ordinary_refs(db_session, owner)
    plan = prepared(tmp_path)
    report = await guard().preflight(db_session, owner, plan, actual_migration_closed=True)
    assert report.blockers == ()
    assert report.reference_counts["postings"] == 2
    for name in ["category_budgets", "scheduled_finance_items", "financial_documents"]:
        assert report.reference_counts[name] == 1
    assert report.reference_counts["actual_import_mappings"] == 2
    await guard().verify_before(db_session, owner, plan, report)


@pytest.mark.parametrize("evidence", ["rule", "origin", "receipt"])
async def test_rule_grant_proposal_origin_or_receipt_item_evidence_blocks(
    db_session: AsyncSession, tmp_path: Path, evidence: str
) -> None:
    owner = await seed_owner(db_session)
    refs = await seed_ordinary_refs(db_session, owner)
    if evidence == "rule":
        db_session.add(
            TransactionCategorizationRule(
                user_id=owner,
                display_description="test",
                normalized_description_exact="test",
                target_category_id=uid(0),
                state="draft",
                version=1,
            )
        )
    elif evidence == "origin":
        db_session.add(
            TransactionCategorizationOrigin(
                user_id=owner,
                transaction_id=refs["transaction"],
                origin="manual",
                version=1,
                assignment_sha256="a" * 64,
            )
        )
    else:
        db_session.add(ReceiptItemState(user_id=owner, bill_id=refs["bill"], version=1))
    await db_session.commit()
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert {"rule_evidence", "receipt_evidence"} & set(report.blockers)


@pytest.mark.parametrize("evidence", ["marker", "consent", "active_suggestion"])
async def test_marker_or_suggestion_consent_and_active_read_work_blocks(
    db_session: AsyncSession, tmp_path: Path, evidence: str
) -> None:
    owner = await seed_owner(db_session)
    if evidence == "marker":
        db_session.add(
            TransactionCategorizationSettings(
                user_id=owner, uncategorized_category_id=uid(56), rules_enabled=False, version=1
            )
        )
    elif evidence == "consent":
        db_session.add(CategorizationSuggestionSettings(user_id=owner, enabled=False, version=1))
    else:
        db_session.add(
            CategorizationSuggestionJob(
                user_id=owner,
                transaction_id=uuid4(),
                source_context_sha256="a" * 64,
                marker_id=uid(56),
                settings_version=1,
                user_epoch=1,
                server_epoch=1,
                configuration_fingerprint="b" * 64,
                status="ready",
            )
        )
    await db_session.commit()
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert {"marker_configured", "suggestion_consent", "active_work"} & set(report.blockers)


async def test_unknown_category_reference_requires_review(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    await db_session.execute(
        text(
            "CREATE TABLE unexpected_category_refs (id uuid PRIMARY KEY, category_id uuid REFERENCES categories(id))"
        )
    )
    await db_session.commit()
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert "unregistered_category_reference" in report.blockers
    assert "unexpected_category_refs" not in Base.metadata.tables


async def test_foreign_owner_reference_to_category_is_blocker(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    other = await seed_owner(db_session, source_tree=False)
    db_session.add(Category(user_id=other, name="Other", parent_id=uid(1), type="expense"))
    await db_session.commit()
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=True
    )
    assert "foreign_reference" in report.blockers


async def test_closed_actual_migration_is_required_without_touching_import_mapping(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    report = await guard().preflight(
        db_session, owner, prepared(tmp_path), actual_migration_closed=False
    )
    assert "actual_migration_open" in report.blockers


async def test_after_verification_detects_modified_posting_import_budget_or_foreign_owner(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    await seed_ordinary_refs(db_session, owner)
    plan = prepared(tmp_path)
    api = guard()
    before = await api.preflight(db_session, owner, plan, actual_migration_closed=True)
    await db_session.execute(
        text("UPDATE category_budgets SET amount_pln=2000 WHERE user_id=:owner"), {"owner": owner}
    )
    await db_session.commit()
    with pytest.raises(importlib.import_module("scripts.category_tree_manifest").CategoryTreeError):
        await api.verify_before(db_session, owner, plan, before)


async def test_wrong_owner_cannot_match_source_tree(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await seed_owner(db_session)
    other = await seed_owner(db_session, source_tree=False)
    report = await guard().preflight(
        db_session, other, prepared(tmp_path), actual_migration_closed=True
    )
    assert "tree_changed" in report.blockers
    assert await db_session.scalar(select(Category.id).where(Category.user_id == other)) is None


async def test_valid_after_tree_retains_all_original_refs(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    owner = await seed_owner(db_session)
    await seed_ordinary_refs(db_session, owner)
    api = guard()
    plan = prepared(tmp_path)
    before = await api.preflight(db_session, owner, plan, actual_migration_closed=True)
    ids = await apply_categories_only(db_session, owner, plan)
    await api.verify_after(db_session, owner, plan, resolved_ids=ids, before=before)


@pytest.mark.parametrize(
    "column,index", [("created_at", 0), ("updated_at", 56), ("updated_at", 13)]
)
async def test_after_rejects_protected_category_timestamp_changes(
    db_session: AsyncSession, tmp_path: Path, column: str, index: int
) -> None:
    owner = await seed_owner(db_session)
    api = guard()
    plan = prepared(tmp_path)
    before = await api.preflight(db_session, owner, plan, actual_migration_closed=True)
    ids = await apply_categories_only(db_session, owner, plan)
    # column is from literal test cases, never an operator input.
    await db_session.execute(
        text(f"UPDATE categories SET {column}='1999-01-01' WHERE id=:id"), {"id": uid(index)}
    )
    with pytest.raises(importlib.import_module("scripts.category_tree_manifest").CategoryTreeError):
        await api.verify_after(db_session, owner, plan, resolved_ids=ids, before=before)
