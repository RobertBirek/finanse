"""Explicit, immutable authorization for one source-absent Actual transaction."""

import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.actual_parser import CategoryDict
from app.finance.models import Account, ActualImportMapping, Category, FinancialTransaction, Posting
from app.finance.reconciliation import CategoryBalance, ReconciliationError, SourceBalance


class PreservedHistoryError(ReconciliationError):
    """A pin or its locked reference graph no longer matches the approval."""


class PreservedTransactionPin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actual_id: str = Field(min_length=1, strict=True)
    pa_id: uuid.UUID
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", strict=True)


class PreservedHistoryManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    source_zip_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", strict=True)
    user_id: uuid.UUID
    transaction: PreservedTransactionPin

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("Manifest version must be the integer 1")
        return value


def load_preserved_history(
    path: Path, archive_bytes: bytes, user_id: uuid.UUID
) -> PreservedHistoryManifest:
    manifest = PreservedHistoryManifest.model_validate_json(path.read_bytes())
    if manifest.user_id != user_id:
        raise PreservedHistoryError("Preserved history belongs to another user")
    if not hmac.compare_digest(
        manifest.source_zip_sha256, hashlib.sha256(archive_bytes).hexdigest()
    ):
        raise PreservedHistoryError("Preserved history source ZIP hash mismatch")
    return manifest


def _canonical_value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name == "fx_rate":
        try:
            rate = Decimal(str(value))
            if not rate.is_finite() or rate != rate.quantize(Decimal("0.000001")):
                raise PreservedHistoryError("Pinned FX rate is not an exact six-decimal value")
            return format(rate, ".6f")
        except InvalidOperation as error:
            raise PreservedHistoryError("Pinned FX rate cannot be encoded") from error
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise PreservedHistoryError("Pinned timestamps must have a timezone")
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, bool, int)):
        return value
    raise PreservedHistoryError(f"Unsupported pinned column type: {name}")


def _column_values(row: FinancialTransaction | Posting) -> dict[str, Any]:
    return {
        column.key: _canonical_value(column.key, getattr(row, column.key))
        for column in row.__mapper__.column_attrs
    }


def transaction_fingerprint(transaction: FinancialTransaction) -> str:
    payload = {
        "transaction": _column_values(transaction),
        "postings": [
            _column_values(posting)
            for posting in sorted(transaction.postings, key=lambda posting: str(posting.id))
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _inverse(mapping: dict[str, uuid.UUID]) -> dict[uuid.UUID, str]:
    inverse = {entity_id: actual_id for actual_id, entity_id in mapping.items()}
    if len(inverse) != len(mapping):
        raise PreservedHistoryError("Ambiguous preserved history reference mapping")
    return inverse


async def validate_preserved_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    manifest: PreservedHistoryManifest,
    source_actual_ids: set[str],
) -> FinancialTransaction:
    if manifest.user_id != user_id or manifest.transaction.actual_id in source_actual_ids:
        raise PreservedHistoryError("Preserved history owner or source-absence mismatch")
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"actual-import:{user_id}"))))
    mappings = list(
        (
            await db.execute(
                select(ActualImportMapping)
                .where(ActualImportMapping.user_id == user_id)
                .order_by(ActualImportMapping.entity_type, ActualImportMapping.actual_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    pin = manifest.transaction
    provenance = [
        mapping
        for mapping in mappings
        if mapping.entity_type == "transaction" and mapping.actual_id == pin.actual_id
    ]
    if len(provenance) != 1 or provenance[0].entity_id != pin.pa_id:
        raise PreservedHistoryError("Preserved transaction mapping does not match the pin")
    transaction = await db.scalar(
        select(FinancialTransaction)
        .where(FinancialTransaction.id == pin.pa_id, FinancialTransaction.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        transaction is None
        or transaction.source != "actual"
        or not transaction.description.startswith(f"[actual:{pin.actual_id}]")
    ):
        raise PreservedHistoryError("Preserved transaction ownership/source/provenance mismatch")
    # Lock parent before children; refreshing the relationship after acquiring
    # locks avoids stale identity-map values or ORM ordering affecting the pin.
    await db.execute(
        select(Posting)
        .where(Posting.transaction_id == transaction.id)
        .order_by(Posting.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    await db.refresh(transaction, attribute_names=["postings"])
    account_map = {m.actual_id: m.entity_id for m in mappings if m.entity_type == "account"}
    category_map = {m.actual_id: m.entity_id for m in mappings if m.entity_type == "category"}
    group_map = {m.actual_id: m.entity_id for m in mappings if m.entity_type == "category_group"}
    account_inverse, category_inverse, group_inverse = (
        _inverse(mapping) for mapping in (account_map, category_map, group_map)
    )
    accounts = {
        a.id: a
        for a in (
            await db.execute(
                select(Account)
                .where(Account.user_id == user_id, Account.id.in_(account_inverse))
                .order_by(Account.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    }
    categories = {
        c.id: c
        for c in (
            await db.execute(
                select(Category)
                .where(
                    Category.user_id == user_id,
                    Category.id.in_(set(category_inverse) | set(group_inverse)),
                )
                .order_by(Category.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    }
    if not hmac.compare_digest(transaction_fingerprint(transaction), pin.snapshot_sha256):
        raise PreservedHistoryError("Preserved transaction snapshot changed since approval")
    if len(transaction.postings) < 2 or any(
        p.direction not in {"debit", "credit"} or p.source_amount <= 0 or p.base_amount_pln <= 0
        for p in transaction.postings
    ):
        raise PreservedHistoryError("Preserved transaction has invalid postings")
    if (
        sum(p.base_amount_pln * (1 if p.direction == "debit" else -1) for p in transaction.postings)
        != 0
    ):
        raise PreservedHistoryError("Preserved transaction is not balanced")
    for posting in transaction.postings:
        if (posting.account_id is None) == (posting.category_id is None):
            raise PreservedHistoryError("Preserved posting must have exactly one reference")
        if posting.account_id is not None:
            account = accounts.get(posting.account_id)
            if account is None or posting.source_currency != account.currency:
                raise PreservedHistoryError(
                    "Preserved account is unmapped, unowned or wrong-currency"
                )
        else:
            category = (
                categories.get(posting.category_id) if posting.category_id is not None else None
            )
            if category is None or category.id not in category_inverse:
                raise PreservedHistoryError("Preserved category is unmapped or unowned")
            if category.parent_id is not None:
                group = categories.get(category.parent_id)
                if group is None or group.id not in group_inverse or group.parent_id is not None:
                    raise PreservedHistoryError("Preserved category group is unmapped or unowned")
    return transaction


def add_preserved_history_balances(
    transaction: FinancialTransaction,
    account_map: dict[str, uuid.UUID],
    category_map: dict[str, uuid.UUID],
    group_map: dict[str, uuid.UUID],
    source_categories: list[CategoryDict],
    accounts: dict[str, SourceBalance],
    categories: dict[str, CategoryBalance],
    groups: dict[str, CategoryBalance],
) -> tuple[dict[str, SourceBalance], dict[str, CategoryBalance], dict[str, CategoryBalance]]:
    account_inverse, category_inverse = _inverse(account_map), _inverse(category_map)
    _inverse(group_map)
    source_by_id = {category["actual_id"]: category for category in source_categories}
    if len(source_by_id) != len(source_categories):
        raise PreservedHistoryError("Ambiguous source category IDs")
    expected_accounts, expected_categories, expected_groups = (
        dict(accounts),
        dict(categories),
        dict(groups),
    )
    for posting in transaction.postings:
        if posting.account_id is not None:
            account_id = account_inverse.get(posting.account_id)
            if account_id not in expected_accounts:
                raise PreservedHistoryError("Preserved account is not present in the source")
            account = expected_accounts[account_id]
            if account.currency != posting.source_currency:
                raise PreservedHistoryError("Preserved native currency differs from source account")
            amount = posting.source_amount * (1 if posting.direction == "credit" else -1)
            expected_accounts[account_id] = replace(account, amount=account.amount + amount)
        else:
            category_id = (
                category_inverse.get(posting.category_id)
                if posting.category_id is not None
                else None
            )
            if category_id not in expected_categories or category_id not in source_by_id:
                raise PreservedHistoryError("Preserved category is not present in the source")
            category = expected_categories[category_id]
            amount = posting.base_amount_pln * (1 if posting.direction == "debit" else -1)
            expected_categories[category_id] = replace(
                category, amount_pln=category.amount_pln + amount
            )
            group_id = source_by_id[category_id]["group_actual_id"]
            if group_id is not None:
                if group_id not in expected_groups or group_id not in group_map:
                    raise PreservedHistoryError(
                        "Preserved category group is not present in the source"
                    )
                group = expected_groups[group_id]
                expected_groups[group_id] = replace(group, amount_pln=group.amount_pln + amount)
    return expected_accounts, expected_categories, expected_groups
