"""Atomic operator contract on an owned disposable PostgreSQL schema."""

import importlib
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.models import AuditEvent
from app.finance import entities
from app.finance.models import Category, FinanceCommandReceipt
from scripts.category_tree_guard import preflight
from scripts.category_tree_manifest import CategoryTreeError, compile_tree, load_bundle
from tests.test_finance.category_tree_cases import cases, uid, write_bundle
from tests.test_finance.category_tree_database import (
    seed_ordinary_refs,
    seed_owner,
    test_database,  # noqa: F401 - owned schema override
)

pytestmark = pytest.mark.integration


def api() -> Any:
    return importlib.import_module("scripts.category_tree_apply")


async def context(db: AsyncSession, tmp: Path) -> tuple[Any, ...]:
    owner = await seed_owner(db)
    await seed_ordinary_refs(db, owner)
    plan = compile_tree(load_bundle(tmp, **write_bundle(tmp, *cases())))
    before = await preflight(db, owner, plan, actual_migration_closed=True)
    operation = uuid4()
    request = api().request_fingerprint(owner, operation, plan)
    await db.rollback()
    return owner, plan, before, operation, request


async def apply(db: AsyncSession, args: tuple[Any, ...]) -> Any:
    owner, plan, before, operation, request = args
    return await api().apply_tree(
        db, owner, plan, operation_id=operation, expected=before, request_hash=request
    )


async def status(db: AsyncSession, args: tuple[Any, ...]) -> Any:
    owner, plan, _, operation, request = args
    return await api().inspect_operation(
        db, owner, plan, operation_id=operation, request_hash=request
    )


async def test_committed_apply_has_exact_rows_types_audits_and_one_receipt(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    owner = args[0]
    old = {
        row.id: (row.name, row.parent_id, row.created_at, row.updated_at)
        for row in (
            await db_session.scalars(select(Category).where(Category.user_id == owner))
        ).all()
    }
    await db_session.rollback()
    async with db_session.begin():
        result = await apply(db_session, args)
    assert len(result.created_ids) == 14 and len(result.updated_ids) == 30 and not result.replayed
    rows = (
        await db_session.scalars(
            select(Category)
            .where(Category.user_id == owner)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert len(rows) == 79 and set(old) <= {r.id for r in rows}
    assert Counter(r.type for r in rows) == {"expense": 73, "income": 6}
    assert (
        sum(
            (r.name, r.parent_id, r.created_at, r.updated_at) == old[r.id]
            for r in rows
            if r.id in old
        )
        == 35
    )
    audits = (await db_session.scalars(select(AuditEvent).where(AuditEvent.user_id == owner))).all()
    assert Counter(a.action for a in audits) == {
        "category_tree.created": 14,
        "category_tree.updated": 30,
        "category_tree.applied": 1,
    }
    assert {a.performed_by for a in audits} == {"operator-cli"}
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 1
    await db_session.rollback()
    assert (await status(db_session, args)).status == "applied"


async def test_domain_create_update_are_used_without_type_source_active_changes(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = await context(db_session, tmp_path)
    seen = []
    created = []
    original = entities.update_category
    create = entities.create_category

    async def update(db: Any, owner: Any, ident: Any, data: Any) -> Any:
        fields = data.model_dump(exclude_unset=True)
        seen.append((ident, fields))
        assert set(fields) <= {"name", "parent_id"}
        return await original(db, owner, ident, data)

    async def make(db: Any, owner: Any, data: Any) -> Any:
        created.append(data)
        return await create(db, owner, data)

    monkeypatch.setattr(entities, "update_category", update)
    monkeypatch.setattr(entities, "create_category", make)
    await apply(db_session, args)
    assert len(seen) == 30 and len(created) == 14
    assert all(uid(i) not in {ident for ident, _ in seen} for i in [5, 6, 13, 40, 41, 43, 48, 58])
    assert next(fields for ident, fields in seen if ident == uid(12)) == {"name": "T12"}
    assert next(fields for ident, fields in seen if ident == uid(3)) == {
        "name": "T3",
        "parent_id": None,
    }


@pytest.mark.parametrize("phase", ["create", "update", "receipt"])
async def test_fault_after_first_create_mid_updates_and_before_receipt_rolls_back_everything(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    args = await context(db_session, tmp_path)
    calls = 0
    if phase == "receipt":
        original = db_session.flush

        async def flush(*a: Any, **kw: Any) -> None:
            if any(isinstance(row, FinanceCommandReceipt) for row in db_session.new):
                raise RuntimeError("injected")
            await original(*a, **kw)

        monkeypatch.setattr(db_session, "flush", flush)
    else:
        name = "create_category" if phase == "create" else "update_category"
        original = getattr(entities, name)

        async def fail(*a: Any, **kw: Any) -> Any:
            nonlocal calls
            result = await original(*a, **kw)
            calls += 1
            if calls == (1 if phase == "create" else 15):
                raise RuntimeError("injected")
            return result

        monkeypatch.setattr(entities, name, fail)
    with pytest.raises(RuntimeError):
        async with db_session.begin():
            await apply(db_session, args)
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Category).where(Category.user_id == args[0])
        )
        == 65
    )
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 0
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0


async def test_response_loss_after_commit_replays_without_second_writes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    async with db_session.begin():
        first = await apply(db_session, args)
    async with db_session.begin():
        second = await apply(db_session, args)
    assert second.replayed and second.created_ids == first.created_ids
    assert await db_session.scalar(select(func.count()).select_from(Category)) == 79
    assert await db_session.scalar(select(func.count()).select_from(AuditEvent)) == 45
    assert await db_session.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 1


async def test_verify_during_uncommitted_apply_reports_busy_not_not_applied(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    async with db_session.begin():
        await apply(db_session, args)
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
        async with factory() as other:
            await other.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY"))
            assert (await status(other, args)).status == "busy_or_conflict"


async def test_verify_reads_fresh_receipt_after_lock_acquisition(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as reader:
        await reader.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED READ ONLY"))
        assert await reader.scalar(select(func.count()).select_from(FinanceCommandReceipt)) == 0
        async with db_session.begin():
            await apply(db_session, args)
        assert (await status(reader, args)).status == "applied"


async def test_same_key_different_request_is_conflict(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    async with db_session.begin():
        await apply(db_session, args)
    owner, plan, before, operation, _ = args
    with pytest.raises(CategoryTreeError):
        await apply(db_session, (owner, plan, before, operation, "a" * 64))


async def test_receipt_replay_with_changed_post_tree_reports_drift_not_success(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    async with db_session.begin():
        await apply(db_session, args)
    await db_session.execute(
        text("UPDATE categories SET name='drift' WHERE id=:id"), {"id": uid(0)}
    )
    await db_session.commit()
    assert (await status(db_session, args)).status == "applied_state_changed"
    with pytest.raises(CategoryTreeError):
        await apply(db_session, args)


async def test_second_operation_id_cannot_reapply_to_post_tree(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    async with db_session.begin():
        await apply(db_session, args)
    owner, plan, before, _, _ = args
    op = uuid4()
    with pytest.raises(CategoryTreeError):
        async with db_session.begin():
            await apply(
                db_session, (owner, plan, before, op, api().request_fingerprint(owner, op, plan))
            )
    assert await db_session.scalar(select(func.count()).select_from(Category)) == 79


@pytest.mark.parametrize("mutation", ["reference", "grant"])
async def test_reference_or_grant_change_since_preflight_aborts_before_first_write(
    db_session: AsyncSession, tmp_path: Path, mutation: str
) -> None:
    args = await context(db_session, tmp_path)
    if mutation == "reference":
        await db_session.execute(text("UPDATE category_budgets SET amount_pln=2000"))
    else:
        from app.finance.rule_models import TransactionCategorizationSettings

        db_session.add(
            TransactionCategorizationSettings(
                user_id=args[0], uncategorized_category_id=uid(0), rules_enabled=False, version=1
            )
        )
    await db_session.commit()
    with pytest.raises(CategoryTreeError):
        async with db_session.begin():
            await apply(db_session, args)
    assert await db_session.scalar(select(func.count()).select_from(Category)) == 65


async def test_verify_absent_receipt_requires_unchanged_before_tree(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    assert (await status(db_session, args)).status == "not_applied"
    await db_session.rollback()
    await db_session.execute(
        text("UPDATE categories SET name='changed' WHERE id=:id"), {"id": uid(0)}
    )
    await db_session.commit()
    assert (await status(db_session, args)).status == "busy_or_conflict"


async def test_actual_importer_still_refuses_original_group_after_reparent(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    from scripts.migrate_actual import LegacyActualMappingError, resolve_ids

    args = await context(db_session, tmp_path)
    async with db_session.begin():
        await apply(db_session, args)

    class SyntheticParser:
        def get_accounts(self) -> list[Any]:
            return []

        def get_categories(self) -> list[Any]:
            return [
                {
                    "actual_id": "test-category",
                    "name": "S0",
                    "type": "expense",
                    "group_actual_id": "test-group",
                }
            ]

        def get_category_groups(self) -> list[Any]:
            return [{"actual_id": "test-group", "name": "S1", "type": "expense"}]

    with pytest.raises(LegacyActualMappingError):
        await resolve_ids(db_session, args[0], SyntheticParser())
    await db_session.rollback()
    assert (await status(db_session, args)).status == "applied"


async def test_parent_changed_false_does_not_clear_parent(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    args = await context(db_session, tmp_path)
    await apply(db_session, args)
    assert await db_session.scalar(select(Category.parent_id).where(Category.id == uid(12))) == uid(
        25
    )


async def test_cli_real_preflight_apply_verify_and_replay_on_disposable_schema(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    import hashlib
    import json
    import os
    import subprocess
    import sys
    from datetime import UTC, datetime

    owner = await seed_owner(db_session)
    await seed_ordinary_refs(db_session, owner)
    hashes = write_bundle(tmp_path / "input", *cases())
    op = uuid4()
    schema = await db_session.scalar(text("SELECT current_schema()"))
    await db_session.rollback()
    env = dict(
        os.environ,
        DATABASE_URL=os.environ["TEST_DATABASE_URL"],
        CATEGORY_TREE_DATABASE_URL=os.environ["TEST_DATABASE_URL"],
        CATEGORY_TREE_TEST_SCHEMA=schema,
        CATEGORY_TREE_RUNTIME_REVISION="synthetic",
        CATEGORY_TREE_RUNTIME_IMAGE="synthetic",
    )
    common = [
        "--bundle-dir",
        str(tmp_path / "input"),
        "--owner",
        str(owner),
        "--operation-id",
        str(op),
        "--source-sha",
        hashes["expected_source_sha"],
        "--mapping-sha",
        hashes["expected_mapping_sha"],
        "--proposal-sha",
        hashes["expected_proposal_sha"],
        "--statement-timeout-ms",
        "10000",
        "--lock-timeout-ms",
        "10000",
        "--actual-migration-closed",
    ]

    def invoke(mode: str, name: str, extra: list[str] | None = None) -> int:
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.category_tree",
                mode,
                *common,
                "--report-file",
                str(tmp_path / name),
                *(extra or []),
            ],
            env=env,
            capture_output=True,
            check=False,
            text=True,
            timeout=45,
        )
        assert "secret" not in process.stdout + process.stderr
        return process.returncode

    assert invoke("--preflight", "preflight.json") == 0
    assert invoke("--verify", "before-verify.json") == 3
    envelope = json.loads((tmp_path / "preflight.json").read_text())
    identity = envelope["identity"]
    identity = {
        **identity,
        "preflight_sha": hashlib.sha256((tmp_path / "preflight.json").read_bytes()).hexdigest(),
    }
    now = datetime.now(UTC).isoformat()
    evidence = {}
    for kind in ["backup_restore", "rehearsal", "fence"]:
        # Synthetic prerequisites only: this approval is DB-guarded test-only, never production.
        proof = {
            "kind": kind,
            "passed": True,
            "identity": identity,
            "issued_at": now,
            "snapshot_sha": "a" * 64,
        }
        p = tmp_path / (kind + ".json")
        p.write_text(json.dumps(proof))
        p.chmod(0o600)
        evidence[kind] = {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    approval = {
        "version": 1,
        "scope": "category_tree_rehearsal_v1",
        "production_apply_approved": False,
        "identity": identity,
        "issued_at": now,
        "max_age_seconds": 180,
        "evidence": evidence,
    }
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(approval))
    path.chmod(0o600)
    extra = [
        "--approval-file",
        str(path),
        "--expected-report",
        str(tmp_path / "preflight.json"),
        "--operator-sha",
        identity["operator_sha"],
    ]
    assert invoke("--apply", "apply.json", extra) == 0
    assert invoke("--verify", "verify.json") == 0
    assert invoke("--apply", "replay.json", extra) == 0
    assert json.loads((tmp_path / "replay.json").read_text())["report"]["replayed"] is True
    assert await db_session.scalar(select(func.count()).select_from(Category)) == 79
