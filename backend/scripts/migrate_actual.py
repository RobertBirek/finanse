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
import re
import sqlite3
import sys
import tempfile
import uuid
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import async_session_factory
from app.finance.actual_parser import ActualParser, TransactionDict
from app.finance.models import Account, ActualImportMapping, Category, FinancialTransaction, Posting
from app.finance.nbp_rates import NbpRateProvider
from app.finance.reconciliation import (
    CategoryBalance,
    ReconciliationError,
    ReconciliationReport,
    SourceBalance,
    reconcile_account_balances,
    reconcile_category_balances,
)
from app.finance.reconciliation import require_reconciled as ensure_reconciled
from app.finance.schemas import AccountCreate, CategoryCreate, PostingCreate, TransactionCreate
from app.finance.service import create_account, create_category, create_transaction

logger = logging.getLogger(__name__)


class ImportValidationError(ValueError):
    """Raised when an Actual transaction cannot be imported faithfully."""


class LegacyActualMappingError(ImportValidationError):
    """Raised when legacy Actual entities cannot be mapped without guessing."""


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
    db: Any,
    user_id: uuid.UUID,
    parser: ActualParser,
    transactions: list[TransactionDict] | None = None,
) -> tuple[dict[str, uuid.UUID], dict[str, uuid.UUID], dict[str, str], dict[str, bool]]:
    """Create accounts and categories, return Actual ID -> PA ID mappings."""
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"actual-import:{user_id}"))))
    if transactions is not None:
        await _backfill_legacy_mappings(db, user_id, parser, transactions)
    acct_map: dict[str, uuid.UUID] = {}
    cat_map: dict[str, uuid.UUID] = {}
    acct_currency: dict[str, str] = {}
    acct_budget: dict[str, bool] = {}
    group_map: dict[str, uuid.UUID] = {}

    for a in parser.get_accounts():
        pa_acct = await _get_mapped_entity(db, user_id, "account", a["actual_id"], Account)
        if pa_acct is None:
            pa_acct = await create_account(
                db,
                user_id,
                AccountCreate(
                    name=a["name"],
                    type=a["type"],
                    currency=a["currency"],
                    is_budget_account=a["is_budget_account"],
                ),
            )
            await _store_mapping(db, user_id, "account", a["actual_id"], pa_acct.id)
        acct_map[a["actual_id"]] = pa_acct.id
        acct_currency[a["actual_id"]] = a["currency"]
        acct_budget[a["actual_id"]] = a["is_budget_account"]

    try:
        category_groups = parser.get_category_groups()
    except sqlite3.OperationalError:
        category_groups = []

    for group in category_groups:
        pa_group = await _get_mapped_entity(
            db, user_id, "category_group", group["actual_id"], Category
        )
        if pa_group is None:
            pa_group = await create_category(
                db,
                user_id,
                CategoryCreate(name=group["name"], type=group["type"]),
            )
            await _store_mapping(db, user_id, "category_group", group["actual_id"], pa_group.id)
        group_map[group["actual_id"]] = pa_group.id

    for c in parser.get_categories():
        pa_cat = await _get_mapped_entity(db, user_id, "category", c["actual_id"], Category)
        if pa_cat is None:
            pa_cat = await create_category(
                db,
                user_id,
                CategoryCreate(
                    name=c["name"],
                    type=c["type"],
                    parent_id=group_map.get(c["group_actual_id"]) if c["group_actual_id"] else None,
                ),
            )
            await _store_mapping(db, user_id, "category", c["actual_id"], pa_cat.id)
        cat_map[c["actual_id"]] = pa_cat.id

    return acct_map, cat_map, acct_currency, acct_budget


async def _get_mapping_id(
    db: Any, user_id: uuid.UUID, entity_type: str, actual_id: str
) -> uuid.UUID | None:
    return await db.scalar(
        select(ActualImportMapping.entity_id).where(
            ActualImportMapping.user_id == user_id,
            ActualImportMapping.entity_type == entity_type,
            ActualImportMapping.actual_id == actual_id,
        )
    )


async def _backfill_legacy_mappings(
    db: Any,
    user_id: uuid.UUID,
    parser: ActualParser,
    transactions: list[TransactionDict],
) -> None:
    """Backfill only mappings proven by legacy Actual transaction postings."""
    transactions_by_actual_id = {
        transaction["actual_id"]: transaction for transaction in transactions
    }
    legacy_result = await db.execute(
        select(FinancialTransaction)
        .options(selectinload(FinancialTransaction.postings))
        .where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source == "actual",
            FinancialTransaction.description.like("[actual:%"),
        )
    )
    legacy_transactions: dict[str, FinancialTransaction] = {}
    for transaction in legacy_result.scalars():
        match = re.match(r"^\[actual:([^\]]+)\]", transaction.description)
        if match is not None and match.group(1) in transactions_by_actual_id:
            legacy_transactions[match.group(1)] = transaction
    if not legacy_transactions:
        return

    account_candidates: dict[str, set[uuid.UUID]] = {}
    category_candidates: dict[str, set[uuid.UUID]] = {}
    for actual_id, legacy_transaction in legacy_transactions.items():
        for source_posting in transactions_by_actual_id[actual_id]["postings"]:
            legacy_postings = [
                posting
                for posting in legacy_transaction.postings
                if posting.source_amount == source_posting["source_amount"]
                and posting.source_currency == source_posting["source_currency"]
                and posting.direction == source_posting["direction"]
            ]
            category_actual_id = source_posting["category_actual_id"]
            if category_actual_id is None:
                entity_ids = {
                    posting.account_id
                    for posting in legacy_postings
                    if posting.account_id is not None and posting.category_id is None
                }
                account_candidates.setdefault(source_posting["account_actual_id"], set()).update(
                    entity_ids
                )
            else:
                entity_ids = {
                    posting.category_id
                    for posting in legacy_postings
                    if posting.category_id is not None
                }
                category_candidates.setdefault(category_actual_id, set()).update(entity_ids)

    accounts = parser.get_accounts()
    categories = parser.get_categories()
    unresolved: list[str] = []
    account_mappings: dict[str, uuid.UUID] = {}
    category_mappings: dict[str, uuid.UUID] = {}
    for account in accounts:
        actual_id = account["actual_id"]
        existing_id = await _get_mapping_id(db, user_id, "account", actual_id)
        candidate_ids = account_candidates.get(actual_id, set())
        if existing_id is not None:
            account_mappings[actual_id] = existing_id
        elif len(candidate_ids) == 1:
            account_mappings[actual_id] = next(iter(candidate_ids))
        else:
            unresolved.append(f"account:{actual_id}")
    for category in categories:
        actual_id = category["actual_id"]
        existing_id = await _get_mapping_id(db, user_id, "category", actual_id)
        candidate_ids = category_candidates.get(actual_id, set())
        if existing_id is not None:
            category_mappings[actual_id] = existing_id
        elif len(candidate_ids) == 1:
            category_mappings[actual_id] = next(iter(candidate_ids))
        else:
            unresolved.append(f"category:{actual_id}")

    try:
        category_groups = parser.get_category_groups()
    except sqlite3.OperationalError:
        category_groups = []
    group_mappings: dict[str, uuid.UUID] = {}
    for group in category_groups:
        actual_id = group["actual_id"]
        existing_id = await _get_mapping_id(db, user_id, "category_group", actual_id)
        child_ids = [
            category_mappings[category["actual_id"]]
            for category in categories
            if category["group_actual_id"] == actual_id
            and category["actual_id"] in category_mappings
        ]
        parent_ids = set(
            (
                await db.execute(select(Category.parent_id).where(Category.id.in_(child_ids)))
            ).scalars()
        )
        parent_ids.discard(None)
        if existing_id is not None:
            group_mappings[actual_id] = existing_id
        elif len(child_ids) > 0 and len(parent_ids) == 1:
            group_mappings[actual_id] = next(iter(parent_ids))
        else:
            unresolved.append(f"category_group:{actual_id}")

    if unresolved:
        raise LegacyActualMappingError(
            "Cannot safely resume legacy Actual import; unresolved provenance: "
            + ", ".join(sorted(unresolved))
        )

    for actual_id, entity_id in account_mappings.items():
        await _store_mapping(db, user_id, "account", actual_id, entity_id)
    for actual_id, entity_id in group_mappings.items():
        await _store_mapping(db, user_id, "category_group", actual_id, entity_id)
    for actual_id, entity_id in category_mappings.items():
        await _store_mapping(db, user_id, "category", actual_id, entity_id)


async def _get_mapped_entity(
    db: Any, user_id: uuid.UUID, entity_type: str, actual_id: str, model: type[Any]
) -> Any | None:
    entity_id = await db.scalar(
        select(ActualImportMapping.entity_id).where(
            ActualImportMapping.user_id == user_id,
            ActualImportMapping.entity_type == entity_type,
            ActualImportMapping.actual_id == actual_id,
        )
    )
    if entity_id is None:
        return None
    return await db.scalar(select(model).where(model.id == entity_id, model.user_id == user_id))


async def _store_mapping(
    db: Any, user_id: uuid.UUID, entity_type: str, actual_id: str, entity_id: uuid.UUID
) -> uuid.UUID:
    result = await db.execute(
        pg_insert(ActualImportMapping)
        .values(
            user_id=user_id,
            entity_type=entity_type,
            actual_id=actual_id,
            entity_id=entity_id,
        )
        .on_conflict_do_nothing(constraint="uq_actual_import_mapping")
        .returning(ActualImportMapping.entity_id)
    )
    stored_entity_id = result.scalar_one_or_none()
    if stored_entity_id is not None:
        return stored_entity_id
    existing_entity_id = await db.scalar(
        select(ActualImportMapping.entity_id).where(
            ActualImportMapping.user_id == user_id,
            ActualImportMapping.entity_type == entity_type,
            ActualImportMapping.actual_id == actual_id,
        )
    )
    if existing_entity_id is None:
        raise RuntimeError("Actual mapping disappeared after conflict")
    return existing_entity_id


def _posting_base_amount(
    source_amount: int,
    currency: str,
    transaction_date: date,
    fx_rates: dict[tuple[str, date], float],
) -> tuple[int, float, str]:
    if currency == "PLN":
        return source_amount, 1.0, "manual"

    fx_rate = fx_rates.get((currency, transaction_date), 0.0)
    if fx_rate <= 0:
        raise ImportValidationError(f"Missing FX rate: {currency} on {transaction_date}")
    return round(source_amount * fx_rate), fx_rate, "nbp"


def _fx_difference_kind(postings: list[PostingCreate]) -> str | None:
    delta = sum(
        posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
        for posting in postings
    )
    if delta > 0:
        return "gain"
    if delta < 0:
        return "loss"
    return None


def required_fx_difference_kind(
    txn: TransactionDict,
    acct_currency: dict[str, str],
    fx_rates: dict[tuple[str, date], float],
) -> str | None:
    """Return the balancing FX category needed for a transfer, if any."""
    if txn["type"] not in {"transfer", "exchange"}:
        return None

    total = 0
    for posting in txn["postings"]:
        currency = posting.get("source_currency") or acct_currency.get(
            posting["account_actual_id"], "PLN"
        )
        base_amount, _, _ = _posting_base_amount(
            posting["source_amount"], currency, txn["date"], fx_rates
        )
        total += base_amount if posting["direction"] == "credit" else -base_amount
    if total > 0:
        return "gain"
    if total < 0:
        return "loss"
    return None


def build_pa_postings(
    txn: TransactionDict,
    acct_map: dict[str, uuid.UUID],
    cat_map: dict[str, uuid.UUID],
    acct_currency: dict[str, str],
    fx_rates: dict[tuple[str, date], float],
    acct_budget: dict[str, bool] | None = None,
    fx_category_ids: dict[str, uuid.UUID] | None = None,
) -> list[PostingCreate]:
    """Convert parser postings to PA PostingCreate with resolved IDs and FX."""
    postings: list[PostingCreate] = []
    for p in txn["postings"]:
        actual_acct_id = p["account_actual_id"]
        category_actual_id = p.get("category_actual_id")
        currency = p.get("source_currency") or acct_currency.get(actual_acct_id, "PLN")
        base_amount, fx_rate, fx_source = _posting_base_amount(
            p["source_amount"], currency, txn["date"], fx_rates
        )
        if category_actual_id is not None and category_actual_id not in cat_map:
            raise ImportValidationError(f"Missing category for {txn['actual_id']}")
        if category_actual_id is None and actual_acct_id not in acct_map:
            raise ImportValidationError(f"Missing account for {txn['actual_id']}")

        postings.append(
            PostingCreate(
                account_id=None if category_actual_id is not None else acct_map[actual_acct_id],
                category_id=cat_map.get(category_actual_id)
                if category_actual_id is not None
                else None,
                source_amount=p["source_amount"],
                source_currency=currency,
                base_amount_pln=base_amount,
                fx_rate=fx_rate,
                fx_rate_source=fx_source,
                # Actual's account sign is opposite to PA's credit-minus-debit balance convention.
                direction="debit" if p["direction"] == "credit" else "credit",
                is_budget_impact=(acct_budget or {}).get(actual_acct_id, True),
            )
        )

    if txn["type"] in {"income", "expense"} and not any(
        posting.category_id is not None for posting in postings
    ):
        raise ImportValidationError(f"Missing category for {txn['actual_id']}")

    fx_difference_kind = _fx_difference_kind(postings)
    if fx_difference_kind is not None:
        fx_category_id = (fx_category_ids or {}).get(fx_difference_kind)
        if fx_category_id is None:
            raise ImportValidationError(
                f"FX category required: {fx_difference_kind} for {txn['actual_id']}"
            )
        difference = abs(
            sum(
                posting.base_amount_pln
                if posting.direction == "debit"
                else -posting.base_amount_pln
                for posting in postings
            )
        )
        postings.append(
            PostingCreate(
                category_id=fx_category_id,
                source_amount=difference,
                source_currency="PLN",
                base_amount_pln=difference,
                fx_rate=1.0,
                fx_rate_source="manual",
                direction="credit" if fx_difference_kind == "gain" else "debit",
                is_budget_impact=False,
            )
        )
    return postings


def make_description(actual_id: str, description: str) -> str:
    """Prefix description with Actual UUID for idempotency."""
    return f"[actual:{actual_id}] {description}"


async def check_idempotent(db, user_id: uuid.UUID, actual_id: str) -> bool:
    """Check if transaction with this Actual ID already exists."""
    mapped_transaction = await _get_mapped_entity(
        db, user_id, "transaction", actual_id, FinancialTransaction
    )
    if mapped_transaction is not None:
        return True
    result = await db.execute(
        select(FinancialTransaction.id).where(
            FinancialTransaction.user_id == user_id,
            FinancialTransaction.source == "actual",
            FinancialTransaction.description.like(f"[actual:{actual_id}]%"),
        )
    )
    transaction_id = result.scalar_one_or_none()
    if transaction_id is None:
        return False
    await _store_mapping(db, user_id, "transaction", actual_id, transaction_id)
    return True


async def get_pa_source_balances(
    db: Any, user_id: uuid.UUID, account_map: dict[str, uuid.UUID]
) -> dict[str, SourceBalance]:
    """Return source balances for mapped PA financial accounts, keyed by Actual ID."""
    pa_ids = set(account_map.values())
    if len(pa_ids) != len(account_map):
        raise ReconciliationError("Multiple Actual accounts map to the same PA account")
    if not pa_ids:
        return {}

    account_result = await db.execute(
        select(Account).where(Account.user_id == user_id, Account.id.in_(pa_ids))
    )
    accounts = {account.id: account for account in account_result.scalars().all()}
    balance_result = await db.execute(
        select(
            Posting.account_id,
            func.coalesce(
                func.sum(
                    case(
                        (Posting.direction == "credit", Posting.source_amount),
                        else_=-Posting.source_amount,
                    )
                ),
                0,
            ).label("amount"),
        )
        .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
        .where(
            FinancialTransaction.user_id == user_id,
            Posting.account_id.in_(accounts),
            Posting.category_id.is_(None),
        )
        .group_by(Posting.account_id)
    )
    amounts = {account_id: int(amount) for account_id, amount in balance_result.all()}
    return {
        actual_id: SourceBalance(
            actual_id=actual_id,
            name=accounts[pa_id].name,
            currency=accounts[pa_id].currency,
            is_budget_account=accounts[pa_id].is_budget_account,
            amount=amounts.get(pa_id, 0),
        )
        for actual_id, pa_id in account_map.items()
        if pa_id in accounts
    }


async def get_pa_category_balances(
    db: Any, user_id: uuid.UUID, category_map: dict[str, uuid.UUID]
) -> dict[str, CategoryBalance]:
    """Return PLN category balances for mapped PA categories, keyed by Actual ID."""
    pa_ids = set(category_map.values())
    if len(pa_ids) != len(category_map):
        raise ReconciliationError("Multiple Actual categories map to the same PA category")
    if not pa_ids:
        return {}

    category_result = await db.execute(
        select(Category).where(Category.user_id == user_id, Category.id.in_(pa_ids))
    )
    categories = {category.id: category for category in category_result.scalars().all()}
    balance_result = await db.execute(
        select(
            Posting.category_id,
            func.coalesce(
                func.sum(
                    case(
                        (Posting.direction == "debit", Posting.base_amount_pln),
                        else_=-Posting.base_amount_pln,
                    )
                ),
                0,
            ).label("amount_pln"),
        )
        .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
        .where(
            FinancialTransaction.user_id == user_id,
            Posting.category_id.in_(categories),
            Posting.account_id.is_(None),
        )
        .group_by(Posting.category_id)
    )
    amounts = {category_id: int(amount) for category_id, amount in balance_result.all()}
    return {
        actual_id: CategoryBalance(
            actual_id=actual_id,
            name=categories[pa_id].name,
            type=categories[pa_id].type,
            amount_pln=amounts.get(pa_id, 0),
        )
        for actual_id, pa_id in category_map.items()
        if pa_id in categories
    }


def get_actual_category_balances(
    transactions: list[TransactionDict],
    categories: list[Any],
    account_map: dict[str, uuid.UUID],
    category_map: dict[str, uuid.UUID],
    account_currency: dict[str, str],
    fx_rates: dict[tuple[str, date], float],
    account_budget: dict[str, bool],
) -> dict[str, CategoryBalance]:
    """Calculate expected category PLN balances from importable Actual transactions."""
    categories_by_id = {category["actual_id"]: category for category in categories}
    category_by_pa_id = {pa_id: actual_id for actual_id, pa_id in category_map.items()}
    amounts = {actual_id: 0 for actual_id in categories_by_id}

    for transaction in transactions:
        try:
            fx_difference_kind = required_fx_difference_kind(
                transaction, account_currency, fx_rates
            )
            postings = build_pa_postings(
                transaction,
                account_map,
                category_map,
                account_currency,
                fx_rates,
                account_budget,
                {fx_difference_kind: uuid.uuid4()} if fx_difference_kind is not None else {},
            )
        except ImportValidationError:
            continue
        for posting in postings:
            if posting.category_id is None:
                continue
            actual_id = category_by_pa_id.get(posting.category_id)
            if actual_id is None:
                continue
            amount = (
                posting.base_amount_pln
                if posting.direction == "debit"
                else -posting.base_amount_pln
            )
            amounts[actual_id] += amount

    return {
        actual_id: CategoryBalance(
            actual_id=actual_id,
            name=category["name"],
            type=category["type"],
            amount_pln=amounts[actual_id],
        )
        for actual_id, category in categories_by_id.items()
    }


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


def write_reconciliation_report(output_dir: Path, report: ReconciliationReport) -> None:
    (output_dir / "reconciliation.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
    )
    (output_dir / "reconciliation_report.txt").write_text(report.to_text() + "\n")


async def migrate(
    blob_path: Path,
    user_id: uuid.UUID,
    dry_run: bool = False,
    require_reconciled: bool = False,
) -> None:
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
    mapping: dict[str, dict[str, str]] = {"accounts": {}, "categories": {}}

    # Phase 1: Parse
    print("Phase 1: Reading Actual data...")
    accounts = parser.get_accounts()
    categories = parser.get_categories()
    simple_txns = parser.get_transactions()
    transfers = parser.get_transfers()
    splits = parser.get_splits()
    actual_balances = parser.get_account_balances()
    warnings.extend(parser.get_warnings())
    print(f"  Accounts: {len(accounts)}, Categories: {len(categories)}")
    print(f"  Simple: {len(simple_txns)}, Transfers: {len(transfers)}, Splits: {len(splits)}")

    all_txns = simple_txns + transfers + splits

    if dry_run:
        acct_currency = parser._get_account_currency_map()
        acct_map = {account["actual_id"]: uuid.uuid4() for account in accounts}
        cat_map = {category["actual_id"]: uuid.uuid4() for category in categories}
        acct_budget = {account["actual_id"]: account["is_budget_account"] for account in accounts}
        fetched_fx_rates: dict[tuple[str, date], float] = {}
        fx_dates: set[tuple[str, date]] = set()
        for txn in all_txns:
            for p in txn["postings"]:
                currency = p["source_currency"]
                if currency != "PLN":
                    fx_dates.add((currency, txn["date"]))

        for currency, dt in fx_dates:
            rate = await nbp.get_rate(currency, dt)
            fetched_fx_rates[(currency, dt)] = rate

        for txn in all_txns:
            try:
                fx_difference_kind = required_fx_difference_kind(
                    txn, acct_currency, fetched_fx_rates
                )
                dry_run_fx_category_ids = (
                    {fx_difference_kind: uuid.uuid4()} if fx_difference_kind is not None else {}
                )
                postings = build_pa_postings(
                    txn,
                    acct_map,
                    cat_map,
                    acct_currency,
                    fetched_fx_rates,
                    acct_budget,
                    dry_run_fx_category_ids,
                )
            except ImportValidationError as error:
                errors.append(f"Skipped {txn['actual_id']}: {error}")
                continue

            total = sum(
                posting.base_amount_pln
                if posting.direction == "debit"
                else -posting.base_amount_pln
                for posting in postings
            )
            if total != 0:
                errors.append(f"Posting sum not zero for {txn['actual_id']}: {total} after FX")

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
        stats["errors"] = len(errors)

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
        reconciliation = ReconciliationReport(
            accounts=reconcile_account_balances(actual_balances, {}).accounts,
            categories=reconcile_category_balances(
                get_actual_category_balances(
                    all_txns,
                    categories,
                    acct_map,
                    cat_map,
                    acct_currency,
                    fetched_fx_rates,
                    acct_budget,
                ),
                {},
            ),
            import_errors=tuple(errors),
        )
        write_reconciliation_report(output_dir, reconciliation)
        print(reconciliation.to_text())
        print("Report saved to scripts/output/")
        await nbp.close()
        if require_reconciled:
            ensure_reconciled(reconciliation)
        return

    # Phase 2: Write to DB
    async with async_session_factory() as db:
        print("Phase 2: Creating accounts and categories...")
        try:
            acct_map, cat_map, acct_currency, acct_budget = await resolve_ids(
                db, user_id, parser, all_txns
            )
        except LegacyActualMappingError as error:
            errors.append(str(error))
            stats["errors"] += 1
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
            output_dir = Path(tempfile.gettempdir()) / "actual_migration"
            output_dir.mkdir(exist_ok=True)
            (output_dir / "migration_report.txt").write_text(report)
            write_reconciliation_report(
                output_dir,
                ReconciliationReport(
                    accounts=reconcile_account_balances(actual_balances, {}).accounts,
                    import_errors=tuple(errors),
                ),
            )
            print(report)
            print("Legacy mapping failure report saved to scripts/output/")
            await nbp.close()
            raise
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
                currency = p["source_currency"]
                if currency != "PLN":
                    rate = await nbp.get_rate(currency, txn["date"])
                    fx_rates[(currency, txn["date"])] = rate

        actual_category_balances = get_actual_category_balances(
            all_txns,
            categories,
            acct_map,
            cat_map,
            acct_currency,
            fx_rates,
            acct_budget,
        )

        # Phase 4: Write transactions
        print("Phase 4: Writing transactions...")
        stats["transactions"] = len(simple_txns)
        stats["transfers"] = len(transfers)
        stats["splits"] = len(splits)
        fx_category_ids: dict[str, uuid.UUID] = {}
        fx_category_specs = {
            "gain": ("Różnice kursowe — zysk", "income"),
            "loss": ("Różnice kursowe — strata", "expense"),
        }

        for txn in all_txns:
            if await check_idempotent(db, user_id, txn["actual_id"]):
                stats["skipped"] += 1
                continue

            try:
                fx_difference_kind = required_fx_difference_kind(txn, acct_currency, fx_rates)
                if fx_difference_kind is not None and fx_difference_kind not in fx_category_ids:
                    name, category_type = fx_category_specs[fx_difference_kind]
                    fx_category = await create_category(
                        db, user_id, CategoryCreate(name=name, type=category_type)
                    )
                    fx_category_ids[fx_difference_kind] = fx_category.id
                postings = build_pa_postings(
                    txn,
                    acct_map,
                    cat_map,
                    acct_currency,
                    fx_rates,
                    acct_budget,
                    fx_category_ids,
                )
            except ImportValidationError as error:
                errors.append(f"Skipped {txn['actual_id']}: {error}")
                stats["errors"] += 1
                continue

            total = 0
            for posting in postings:
                signed = (
                    posting.base_amount_pln
                    if posting.direction == "debit"
                    else -posting.base_amount_pln
                )
                total += signed
            if total != 0:
                errors.append(f"Posting sum not zero for {txn['actual_id']}: {total} after FX")
                stats["errors"] += 1
                continue

            try:
                created_transaction = await create_transaction(
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
                await _store_mapping(
                    db, user_id, "transaction", txn["actual_id"], created_transaction.id
                )
                stats["written"] += 1
            except (SQLAlchemyError, ValueError) as error:
                errors.append(f"Failed to write {txn['actual_id']}: {error}")
                stats["errors"] += 1

        output_dir = Path(tempfile.gettempdir()) / "actual_migration"
        output_dir.mkdir(exist_ok=True)
        reconciliation = reconcile_account_balances(
            actual_balances,
            await get_pa_source_balances(db, user_id, acct_map),
        )
        reconciliation = ReconciliationReport(
            accounts=reconciliation.accounts,
            categories=reconcile_category_balances(
                actual_category_balances,
                await get_pa_category_balances(db, user_id, cat_map),
            ),
            import_errors=tuple(errors),
        )
        write_reconciliation_report(output_dir, reconciliation)
        print(reconciliation.to_text())
        if require_reconciled:
            ensure_reconciled(reconciliation)

        report = generate_report(stats, errors, warnings, mapping)
        print(report)
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
    parser_args.add_argument(
        "--require-reconciled",
        action="store_true",
        help="Fail unless all Actual account source balances reconcile with PA",
    )
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
    await migrate(
        blob_path,
        user_id,
        dry_run=args.dry_run,
        require_reconciled=args.require_reconciled,
    )


if __name__ == "__main__":
    asyncio.run(main())
