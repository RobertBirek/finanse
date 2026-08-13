#!/usr/bin/env python3
"""
Migrate data from Actual Budget SQLite to Personal Advisor PostgreSQL.

Usage:
    python scripts/migrate_actual.py --blob-path /path/to/file-xxx.blob --user-id UUID --dry-run
    python scripts/migrate_actual.py --blob-path /path/to/file-xxx.blob --user-id UUID --execute

Requirements: Run inside backend container (has access to DB + models).
"""

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import uuid
import zipfile
from datetime import date
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session_factory
from app.finance.actual_parser import ActualParser
from app.finance.models import FinancialTransaction
from app.finance.nbp_rates import NbpRateProvider
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction

logger = logging.getLogger(__name__)


async def extract_sqlite(blob_path: Path) -> Path:
    """Extract db.sqlite from Actual encrypted ZIP blob."""
    extract_dir = Path(tempfile.mkdtemp(prefix="actual_extract_"))
    with zipfile.ZipFile(blob_path, "r") as zf:
        zf.extractall(extract_dir)
    sqlite_path = extract_dir / "db.sqlite"
    if not sqlite_path.exists():
        raise FileNotFoundError(f"db.sqlite not found in {blob_path}")
    return sqlite_path


async def resolve_ids(
    db,
    user_id: uuid.UUID,
    parser: ActualParser,
) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID], dict[str, str]]:
    """Create accounts and categories, return Actual ID -> PA ID mappings."""
    acct_map = {}
    cat_map = {}
    acct_currency = {}

    for a in parser.get_accounts():
        pa_acct = await create_account(
            db,
            user_id,
            AccountCreate(
                name=a["name"],
                type=a["type"],
                currency=a["currency"],
            ),
        )
        acct_map[a["actual_id"]] = pa_acct.id
        acct_currency[a["actual_id"]] = a["currency"]

    for c in parser.get_categories():
        pa_cat = await create_category(
            db,
            user_id,
            CategoryCreate(
                name=c["name"],
                type=c["type"],
            ),
        )
        cat_map[c["actual_id"]] = pa_cat.id

    return acct_map, cat_map, acct_currency


def build_pa_postings(
    txn: dict,
    acct_map: dict[str, uuid.UUID],
    cat_map: dict[str, uuid.UUID],
    acct_currency: dict[str, str],
    fx_rates: dict[tuple[str, date], float],
) -> list[PostingCreate]:
    """Convert parser postings to PA PostingCreate with resolved IDs and FX."""
    postings = []
    for p in txn["postings"]:
        actual_acct_id = p["account_actual_id"]
        currency = acct_currency.get(actual_acct_id, "PLN")
        fx_rate = fx_rates.get((currency, txn["date"]), 1.0)
        if fx_rate == 0.0:
            base_amount = p["source_amount"]
            fx_source = "nbp_error"
        elif currency == "PLN":
            base_amount = p["source_amount"]
            fx_source = "manual"
        else:
            base_amount = round(p["source_amount"] * fx_rate)
            fx_source = "nbp"

        postings.append(
            PostingCreate(
                account_id=(None if p.get("category_actual_id") else acct_map[actual_acct_id]),
                category_id=cat_map.get(p.get("category_actual_id"))
                if p.get("category_actual_id")
                else None,
                source_amount=p["source_amount"],
                source_currency=currency,
                base_amount_pln=base_amount,
                fx_rate=fx_rate,
                fx_rate_source=fx_source,
                direction=p["direction"],
            )
        )
    return postings


def make_description(actual_id: str, description: str) -> str:
    """Prefix description with Actual UUID for idempotency."""
    return f"[actual:{actual_id}] {description}"


async def check_idempotent(db, user_id: uuid.UUID, actual_id: str) -> bool:
    """Check if transaction with this Actual ID already exists."""
    result = await db.execute(
        select(FinancialTransaction.id).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source == "actual",
            FinancialTransaction.description.like(f"[actual:{actual_id}]%"),
        )
    )
    return result.first() is not None


def generate_report(stats: dict, errors: list[str], warnings: list[str], mapping: dict) -> str:
    """Generate human-readable report."""
    lines = [
        "=" * 60,
        "Actual Budget -> Personal Advisor -- Migration Report",
        "=" * 60,
        "",
        f"Accounts imported:    {stats.get('accounts', 0)}",
        f"Categories imported:  {stats.get('categories', 0)}",
        f"Transactions:         {stats.get('transactions', 0)} (simple)",
        f"Transfers:            {stats.get('transfers', 0)}",
        f"Splits:               {stats.get('splits', 0)}",
        f"Total written:        {stats.get('written', 0)}",
        f"Skipped (duplicate):  {stats.get('skipped', 0)}",
        f"Errors:               {stats.get('errors', 0)}",
        "",
    ]
    if warnings:
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  [W] {w}")
    if errors:
        lines.append("Errors:")
        for e in errors:
            lines.append(f"  [E] {e}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


async def migrate(blob_path: Path, user_id: uuid.UUID, dry_run: bool = False) -> None:
    """Main migration pipeline."""
    sqlite_path = await extract_sqlite(blob_path)
    parser = ActualParser(sqlite_path)
    nbp = NbpRateProvider()

    errors: list[str] = []
    warnings: list[str] = []
    stats = {
        "accounts": 0,
        "categories": 0,
        "transactions": 0,
        "transfers": 0,
        "splits": 0,
        "written": 0,
        "skipped": 0,
        "errors": 0,
    }
    mapping = {"accounts": {}, "categories": {}}

    # Phase 1: Parse
    print("Phase 1: Reading Actual data...")
    accounts = parser.get_accounts()
    categories = parser.get_categories()
    simple_txns = parser.get_transactions()
    transfers = parser.get_transfers()
    splits = parser.get_splits()
    warnings.extend(parser.get_warnings())
    print(f"  Accounts: {len(accounts)}, Categories: {len(categories)}")
    print(f"  Simple: {len(simple_txns)}, Transfers: {len(transfers)}, Splits: {len(splits)}")

    all_txns = simple_txns + transfers + splits

    for txn in all_txns:
        total = 0
        for p in txn["postings"]:
            signed = p["source_amount"] if p["direction"] == "debit" else -p["source_amount"]
            total += signed
        if total != 0:
            errors.append(f"Posting sum not zero for {txn['actual_id']}: {total}")

    if dry_run:
        acct_currency = parser._get_account_currency_map()
        fx_dates: set[tuple[str, date]] = set()
        for txn in all_txns:
            for p in txn["postings"]:
                currency = acct_currency.get(p["account_actual_id"], "PLN")
                if currency != "PLN":
                    fx_dates.add((currency, txn["date"]))

        for currency, dt in fx_dates:
            rate = await nbp.get_rate(currency, dt)
            if rate == 0.0:
                warnings.append(f"NBP rate unavailable: {currency} on {dt}")

        report = generate_report(
            {
                "accounts": len(accounts),
                "categories": len(categories),
                "transactions": len(simple_txns),
                "transfers": len(transfers),
                "splits": len(splits),
                "written": 0,
                "skipped": 0,
                "errors": len(errors),
            },
            errors,
            warnings,
            mapping,
        )
        print(report)

        output_dir = Path(tempfile.gettempdir()) / "actual_migration"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "migration_report.txt").write_text(report)
        (output_dir / "migration_log.json").write_text(
            json.dumps(
                {
                    "stats": stats,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
                default=str,
            )
        )
        print("Report saved to scripts/output/")
        await nbp.close()
        return

    # Phase 2: Write to DB
    async with async_session_factory() as db:
        print("Phase 2: Creating accounts and categories...")
        acct_map, cat_map, acct_currency = await resolve_ids(db, user_id, parser)
        stats["accounts"] = len(acct_map)
        stats["categories"] = len(cat_map)
        for actual_id, pa_id in acct_map.items():
            mapping["accounts"][actual_id] = str(pa_id)
        for actual_id, pa_id in cat_map.items():
            mapping["categories"][actual_id] = str(pa_id)

        # Phase 3: Fetch FX rates
        print("Phase 3: Fetching FX rates...")
        fx_rates: dict[tuple[str, date], float] = {}
        for txn in all_txns:
            for p in txn["postings"]:
                actual_acct_id = p["account_actual_id"]
                currency = acct_currency.get(actual_acct_id, "PLN")
                if currency != "PLN":
                    rate = await nbp.get_rate(currency, txn["date"])
                    fx_rates[(currency, txn["date"])] = rate
                    if rate == 0.0:
                        warnings.append(f"NBP rate unavailable: {currency} on {txn['date']}")

        # Phase 4: Write transactions
        print("Phase 4: Writing transactions...")
        stats["transactions"] = len(simple_txns)
        stats["transfers"] = len(transfers)
        stats["splits"] = len(splits)

        for txn in all_txns:
            if await check_idempotent(db, user_id, txn["actual_id"]):
                stats["skipped"] += 1
                continue

            postings = build_pa_postings(txn, acct_map, cat_map, acct_currency, fx_rates)

            total = 0
            for p in postings:
                signed = p.base_amount_pln if p.direction == "debit" else -p.base_amount_pln
                total += signed
            if total != 0:
                errors.append(f"Posting sum not zero for {txn['actual_id']}: {total} after FX")
                stats["errors"] += 1
                continue

            try:
                await create_transaction(
                    db,
                    user_id,
                    TransactionCreate(
                        transaction_date=txn["date"],
                        description=make_description(txn["actual_id"], txn["description"]),
                        type=txn["type"],
                        source="actual",
                        postings=postings,
                    ),
                )
                stats["written"] += 1
            except Exception as e:
                errors.append(f"Failed to write {txn['actual_id']}: {e}")
                stats["errors"] += 1

        report = generate_report(stats, errors, warnings, mapping)
        print(report)

        output_dir = Path(tempfile.gettempdir()) / "actual_migration"
        output_dir.mkdir(exist_ok=True)
        (output_dir / "migration_report.txt").write_text(report)
        (output_dir / "migration_log.json").write_text(
            json.dumps(
                {
                    "stats": stats,
                    "errors": errors,
                    "warnings": warnings,
                    "mapping": mapping,
                },
                indent=2,
                default=str,
            )
        )
        print("Report saved to scripts/output/")

        if not dry_run:
            await db.commit()

    await nbp.close()


async def main():
    parser_args = argparse.ArgumentParser(description="Migrate Actual Budget to Personal Advisor")
    parser_args.add_argument(
        "--blob-path", required=True, help="Path to Actual blob file (file-*.blob)"
    )
    parser_args.add_argument(
        "--user-id", required=True, help="PA user UUID to assign imported data to"
    )
    parser_args.add_argument(
        "--dry-run", action="store_true", help="Validate and report only, no writes"
    )
    parser_args.add_argument("--execute", action="store_true", help="Actually write to database")
    args = parser_args.parse_args()

    if args.execute and args.dry_run:
        print("Error: cannot use both --dry-run and --execute")
        sys.exit(1)
    if not args.dry_run and not args.execute:
        print("Error: must specify --dry-run or --execute")
        sys.exit(1)

    blob_path = Path(args.blob_path)
    if not blob_path.exists():
        print(f"Error: blob file not found: {args.blob_path}")
        sys.exit(1)

    user_id = uuid.UUID(args.user_id)
    await migrate(blob_path, user_id, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
