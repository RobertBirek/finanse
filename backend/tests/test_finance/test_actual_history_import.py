"""A pin explains only its own ledger contribution, never other differences."""

import hashlib
import io
import json
import sqlite3
import sys
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.finance.actual_history import PreservedHistoryError, transaction_fingerprint
from app.finance.actual_parser import ActualParser
from app.finance.models import Account, ActualImportMapping, Category, FinancialTransaction, Posting
from app.finance.reconciliation import ReconciliationError, ReconciliationReport
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction
from scripts import migrate_actual as importer


@dataclass
class HistoryCase:
    user: uuid.UUID
    archive: Path
    manifest: Path
    kept_id: uuid.UUID
    fingerprint: str
    factory: async_sessionmaker[AsyncSession]


async def prepare_case(
    db: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_variant: str | None = None,
    extra_local: bool = False,
) -> HistoryCase:
    user = uuid.uuid4()
    account = await create_account(db, user, AccountCreate(name="Account", type="checking"))
    group = await create_category(db, user, CategoryCreate(name="Group", type="expense"))
    category = await create_category(
        db, user, CategoryCreate(name="Category", type="expense", parent_id=group.id)
    )

    def expense(amount: int, description: str, source: str) -> TransactionCreate:
        return TransactionCreate(
            transaction_date=date(2026, 1, 1),
            description=description,
            type="expense",
            source=source,
            postings=[
                PostingCreate(
                    account_id=account.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="debit",
                ),
                PostingCreate(
                    category_id=category.id,
                    source_amount=amount,
                    base_amount_pln=amount,
                    direction="credit",
                ),
            ],
        )

    kept = await create_transaction(db, user, expense(37, "[actual:kept] Kept unchanged", "actual"))
    for kind, actual_id, entity in [
        ("account", "a", account),
        ("category", "c", category),
        ("category_group", "g", group),
        ("transaction", "kept", kept),
    ]:
        await importer._store_mapping(db, user, kind, actual_id, entity.id)
    if extra_local:
        await create_transaction(db, user, expense(11, "Unapproved local transaction", "manual"))
    await db.commit()
    fingerprint = transaction_fingerprint(kept)
    source = tmp_path / "db.sqlite"
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            CREATE TABLE accounts (id TEXT, name TEXT, offbudget INTEGER, closed INTEGER, tombstone INTEGER);
            CREATE TABLE categories (id TEXT, name TEXT, is_income INTEGER, cat_group TEXT, tombstone INTEGER);
            CREATE TABLE category_groups (id TEXT, name TEXT, tombstone INTEGER);
            CREATE TABLE payees (id TEXT, name TEXT);
            CREATE TABLE payee_mapping (id TEXT, payeeId TEXT);
            CREATE TABLE transactions (id TEXT, acct TEXT, category TEXT, amount INTEGER,
                description TEXT, notes TEXT, date INTEGER, tombstone INTEGER,
                isParent INTEGER, isChild INTEGER, parent_id TEXT, transferred_id TEXT);
            INSERT INTO accounts VALUES ('a','Account',0,0,0);
            INSERT INTO accounts VALUES ('new-closed','New closed',0,1,0);
            INSERT INTO category_groups VALUES ('g','Group',0);
            INSERT INTO categories VALUES ('c','Category',0,'g',0);
            INSERT INTO transactions VALUES ('new','a','c',-100,NULL,'New expense',20261001,0,0,0,NULL,NULL);
        """)
        if source_variant == "simple":
            conn.execute(
                "INSERT INTO transactions VALUES ('kept','a','c',-37,NULL,NULL,20261001,0,0,0,NULL,NULL)"
            )
        elif source_variant == "transfer":
            conn.executescript("""
            INSERT INTO transactions VALUES ('kept','a',NULL,-37,NULL,NULL,20261001,0,0,0,NULL,'partner');
            INSERT INTO transactions VALUES ('partner','new-closed',NULL,37,NULL,NULL,20261001,0,0,0,NULL,'kept');
        """)
        elif source_variant == "split":
            conn.executescript("""
            INSERT INTO transactions VALUES ('kept','a',NULL,-37,NULL,NULL,20261001,0,1,0,NULL,NULL);
            INSERT INTO transactions VALUES ('child','a','c',-37,NULL,NULL,20261001,0,0,1,'kept',NULL);
        """)
        elif source_variant == "transfer-partner":
            conn.executescript("""
            INSERT INTO transactions VALUES ('aaa-leg','a',NULL,-37,NULL,NULL,20261001,0,0,0,NULL,'kept');
            INSERT INTO transactions VALUES ('kept','new-closed',NULL,37,NULL,NULL,20261001,0,0,0,NULL,'aaa-leg');
        """)
        elif source_variant == "split-child":
            conn.executescript("""
            INSERT INTO transactions VALUES ('parent','a',NULL,-37,NULL,NULL,20261001,0,1,0,NULL,NULL);
            INSERT INTO transactions VALUES ('kept','a','c',-37,NULL,NULL,20261001,0,0,1,'parent',NULL);
        """)
        elif source_variant == "unparsed-duplicate":
            conn.executescript("""
            INSERT INTO transactions VALUES ('orphan','a','c',-37,NULL,NULL,20261001,0,0,1,'missing-parent',NULL);
            INSERT INTO transactions SELECT * FROM transactions WHERE id='orphan';
        """)
        elif source_variant == "duplicate":
            conn.execute("INSERT INTO transactions SELECT * FROM transactions WHERE id='new'")
        elif source_variant == "import-error":
            conn.execute(
                "INSERT INTO transactions VALUES ('bad','a','missing-category',-1,NULL,NULL,20261001,0,0,0,NULL,NULL)"
            )
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(source, "db.sqlite")
    manifest = tmp_path / "pin.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "user_id": str(user),
                "source_zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "transaction": {
                    "actual_id": "kept",
                    "pa_id": str(kept.id),
                    "snapshot_sha256": fingerprint,
                },
            }
        )
    )
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    monkeypatch.setattr(importer, "async_session_factory", factory)
    monkeypatch.setattr(importer.tempfile, "gettempdir", lambda: str(tmp_path))
    return HistoryCase(user, archive, manifest, kept.id, fingerprint, factory)


async def database_snapshot(case: HistoryCase) -> dict[str, Any]:
    async with case.factory() as session:
        return {
            model.__tablename__: list(
                (await session.execute(select(model.__table__).order_by(model.id))).all()
            )
            for model in (Account, Category, ActualImportMapping, FinancialTransaction, Posting)
        }


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("source_variant", ["transfer-partner", "split-child"])
async def test_pin_cannot_ignore_reappearing_underlying_source_row(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_variant: str
) -> None:
    case = await prepare_case(db_session, tmp_path, monkeypatch, source_variant=source_variant)
    before = await database_snapshot(case)
    with pytest.raises(PreservedHistoryError, match="source-absence"):
        await importer.migrate(
            case.archive,
            case.user,
            require_reconciled=True,
            preserved_history_manifest=case.manifest,
        )
    assert await database_snapshot(case) == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_duplicate_underlying_rows_are_rejected_even_when_not_parsed_as_operations(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = await prepare_case(
        db_session, tmp_path, monkeypatch, source_variant="unparsed-duplicate"
    )
    before = await database_snapshot(case)
    with pytest.raises(ValueError, match="Duplicate Actual"):
        await importer.migrate(
            case.archive,
            case.user,
            require_reconciled=True,
            preserved_history_manifest=case.manifest,
        )
    assert await database_snapshot(case) == before


@pytest.mark.parametrize("use_view", [False, True])
def test_underlying_identity_inventory_includes_legs_but_ignores_tombstones(
    tmp_path: Path, use_view: bool
) -> None:
    path = tmp_path / "inventory.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE transactions (id TEXT, tombstone INTEGER);
            INSERT INTO transactions VALUES ('parent',0),('child',0),('partner',0),('removed',1),('removed',1);
        """)
        if use_view:
            connection.execute("CREATE VIEW v_transactions AS SELECT * FROM transactions")
    with ActualParser(path) as parser:
        assert parser.get_source_transaction_ids() == {"parent", "child", "partner"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_explicit_manifest_reconciles_once_and_retains_raw_differences(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = await prepare_case(db_session, tmp_path, monkeypatch)
    before = await database_snapshot(case)
    for _ in range(2):
        await importer.migrate(
            case.archive,
            case.user,
            require_reconciled=True,
            preserved_history_manifest=case.manifest,
        )
        envelope = json.loads((tmp_path / "actual_migration/reconciliation.json").read_text())
        assert set(envelope) == {
            "schema_version",
            "source_basis",
            "raw_actual",
            "augmented",
            "preserved_history",
        }
        assert (
            envelope["source_basis"] == "actual_plus_pinned_preserved_history"
            and envelope["schema_version"] == 1
        )
        assert (
            envelope["raw_actual"]["is_reconciled"] is False
            and envelope["augmented"]["is_reconciled"] is True
        )
        assert envelope["augmented"]["import_errors"] == []
        assert (
            envelope["preserved_history"]["manifest"]["transaction"]["snapshot_sha256"]
            == case.fingerprint
        )
        assert envelope["preserved_history"]["contributions"] == {
            "accounts": {"a": -37},
            "categories": {"c": -37},
            "category_groups": {"g": -37},
        }
        raw = next(row for row in envelope["raw_actual"]["accounts"] if row["actual_id"] == "a")
        augmented = next(
            row for row in envelope["augmented"]["accounts"] if row["actual_id"] == "a"
        )
        assert raw["actual_amount"] == -100 and raw["pa_amount"] == -137 and raw["difference"] == 37
        assert augmented["actual_amount"] == augmented["pa_amount"] == -137
        async with case.factory() as fresh:
            kept = await fresh.scalar(
                select(FinancialTransaction)
                .options(selectinload(FinancialTransaction.postings))
                .where(FinancialTransaction.id == case.kept_id)
            )
            assert kept is not None and transaction_fingerprint(kept) == case.fingerprint
        after = await database_snapshot(case)
        assert len(after["accounts"]) == 2 and len(after["financial_transactions"]) == 2
        assert all(row in after["postings"] for row in before["postings"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_default_import_still_requires_literal_actual_balances(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = await prepare_case(db_session, tmp_path, monkeypatch)
    before = await database_snapshot(case)
    with pytest.raises(ReconciliationError):
        await importer.migrate(case.archive, case.user, require_reconciled=True)
    assert await database_snapshot(case) == before
    report = json.loads((tmp_path / "actual_migration/reconciliation.json").read_text())
    assert report["is_reconciled"] is False and "raw_actual" not in report


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "wrong-pin",
        "stale-pin",
        "wrong-user",
        "wrong-zip",
        "simple",
        "transfer",
        "split",
        "duplicate",
        "cross-path-duplicate",
        "unapproved-local",
        "import-error",
    ],
)
async def test_invalid_pin_or_any_unapproved_difference_rolls_back_from_fresh_session(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    case = await prepare_case(
        db_session,
        tmp_path,
        monkeypatch,
        source_variant=fault,
        extra_local=fault == "unapproved-local",
    )
    data = json.loads(case.manifest.read_text())
    if fault == "wrong-pin":
        data["transaction"]["snapshot_sha256"] = "0" * 64
    elif fault == "wrong-user":
        data["user_id"] = str(uuid.uuid4())
    elif fault == "wrong-zip":
        data["source_zip_sha256"] = "0" * 64
    elif fault == "stale-pin":
        async with case.factory() as changed:
            kept = await changed.get(FinancialTransaction, case.kept_id)
            assert kept is not None
            kept.description = "[actual:kept] Edited after approval"
            await changed.commit()
    elif fault == "cross-path-duplicate":
        original = importer.ActualParser.get_transactions
        monkeypatch.setattr(importer.ActualParser, "get_transfers", lambda parser: original(parser))
    case.manifest.write_text(json.dumps(data))
    before = await database_snapshot(case)
    with pytest.raises(ValueError):
        await importer.migrate(
            case.archive,
            case.user,
            require_reconciled=True,
            preserved_history_manifest=case.manifest,
        )
    assert await database_snapshot(case) == before


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_swap_after_hash_does_not_change_parsed_bytes(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = await prepare_case(db_session, tmp_path, monkeypatch)
    original = importer.load_preserved_history

    def verify_then_swap(path: Path, archive_bytes: bytes, user: uuid.UUID) -> Any:
        manifest = original(path, archive_bytes, user)
        case.archive.write_bytes(b"Changed after hash verification")
        return manifest

    monkeypatch.setattr(importer, "load_preserved_history", verify_then_swap)
    await importer.migrate(
        case.archive, case.user, require_reconciled=True, preserved_history_manifest=case.manifest
    )
    envelope = json.loads((tmp_path / "actual_migration/reconciliation.json").read_text())
    assert envelope["augmented"]["is_reconciled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [
        {"dry_run": True, "require_reconciled": True},
        {"require_reconciled": False},
        {"replace_legacy_actual": True, "require_reconciled": True},
    ],
)
async def test_manifest_rejects_modes_without_database_pin_validation(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        await importer.migrate(
            tmp_path / "not-read.zip",
            uuid.uuid4(),
            preserved_history_manifest=tmp_path / "not-read.json",
            **options,
        )


def test_no_manifest_report_bytes_are_backward_compatible(tmp_path: Path) -> None:
    importer.write_reconciliation_report(tmp_path, ReconciliationReport(accounts=()))
    assert (
        (tmp_path / "reconciliation.json").read_text()
        == '{\n  "is_reconciled": true,\n  "accounts": [],\n  "categories": [],\n  "category_groups": [],\n  "import_errors": []\n}\n'
    )
    assert (tmp_path / "reconciliation_report.txt").read_text() == "\n"


@pytest.mark.asyncio
async def test_verified_extract_uses_only_immutable_root_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "source.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE marker (value TEXT)")
    data = database.read_bytes()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("db.sqlite", data)
        output.writestr("../outside.txt", "must not be extracted")
        output.writestr("nested/extra.txt", "must not be extracted")
    monkeypatch.setattr(importer.tempfile, "gettempdir", lambda: str(tmp_path))
    path = await importer.extract_sqlite(
        tmp_path / "nonexistent.zip", archive_bytes=archive.getvalue()
    )
    assert path.read_bytes() == data and {entry.name for entry in path.parent.iterdir()} == {
        "db.sqlite"
    }
    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["duplicate", "nested-only"])
async def test_verified_extract_rejects_ambiguous_database_members(
    tmp_path: Path, fault: str
) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("nested/db.sqlite" if fault == "nested-only" else "db.sqlite", b"database")
        if fault == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate"):
                output.writestr("db.sqlite", b"another database")
    with pytest.raises(ValueError):
        await importer.extract_sqlite(tmp_path / "unused.zip", archive_bytes=archive.getvalue())


@pytest.mark.asyncio
async def test_cli_forwards_valid_manifest_only_to_strict_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "export.zip"
    archive.write_bytes(b"archive")
    manifest = tmp_path / "pin.json"
    user = uuid.uuid4()
    calls = []

    async def capture(blob_path: Path, user_id: uuid.UUID, **options: Any) -> None:
        calls.append((blob_path, user_id, options))

    monkeypatch.setattr(importer, "migrate", capture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migrate",
            "--blob-path",
            str(archive),
            "--user-id",
            str(user),
            "--execute",
            "--require-reconciled",
            "--preserved-history-manifest",
            str(manifest),
        ],
    )
    await importer.main()
    assert calls == [
        (
            archive,
            user,
            {"dry_run": False, "require_reconciled": True, "preserved_history_manifest": manifest},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        ["--dry-run", "--require-reconciled"],
        ["--execute"],
        [
            "--execute",
            "--require-reconciled",
            "--replace-legacy-actual",
            "--backup-path",
            "unused.dump",
        ],
    ],
)
async def test_cli_rejects_manifest_modes_before_backup_or_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: list[str]
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Invalid manifest mode must not execute or back up")

    monkeypatch.setattr(importer, "create_verified_backup", forbidden)
    monkeypatch.setattr(importer, "migrate", forbidden)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migrate",
            "--blob-path",
            str(tmp_path / "unused.zip"),
            "--user-id",
            str(uuid.uuid4()),
            "--preserved-history-manifest",
            str(tmp_path / "pin.json"),
            *mode,
        ],
    )
    with pytest.raises(SystemExit):
        await importer.main()
