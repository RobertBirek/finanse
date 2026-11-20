"""Bounded owned taxonomy; only aliases/names cross the provider boundary."""

import hashlib
import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.documents.finance_draft_models import DocumentFinanceDraftIntent
from app.finance.models import Category, FinancialDocument, FinancialDocumentSource

EXCLUDED_CATEGORY_SOURCES = ("opening_balance", "system", "technical", "uncategorized")


@dataclass(frozen=True)
class CategoryCatalog:
    public: list[dict[str, str]] = field(default_factory=list)
    private_key_map: dict[str, uuid.UUID] = field(default_factory=dict)
    fingerprint: str = ""


def build_category_catalog(categories: Sequence[Category], owner: uuid.UUID) -> CategoryCatalog:
    if len(categories) > settings.DOCUMENT_CATEGORY_MAX_CATEGORIES:
        return CategoryCatalog()
    owned = {
        cat.id: cat
        for cat in categories
        if cat.user_id == owner
        and cat.type == "expense"
        and cat.is_active
        and cat.source not in EXCLUDED_CATEGORY_SOURCES
    }
    paths: list[dict[str, str]] = []
    private: dict[str, uuid.UUID] = {}
    for cat_id in sorted(owned, key=str):
        node: Category | None = owned[cat_id]
        names: list[str] = []
        seen: set[uuid.UUID] = set()
        valid = True
        while node is not None:
            if node.id in seen or not node.name.strip():
                valid = False
                break
            seen.add(node.id)
            names.append(node.name)
            if node.parent_id is not None and node.parent_id not in owned:
                valid = False
                break
            node = owned.get(node.parent_id) if node.parent_id else None
        if valid:
            key = f"c{len(paths) + 1:02d}"
            paths.append({"key": key, "path": " / ".join(reversed(names))})
            private[key] = cat_id
    public_json = json.dumps(paths, ensure_ascii=False, sort_keys=True)
    if len(public_json.encode()) > settings.DOCUMENT_CATEGORY_MAX_BYTES:
        return CategoryCatalog()
    fingerprint = hashlib.sha256(
        json.dumps(
            {"public": paths, "ids": {k: str(v) for k, v in private.items()}}, sort_keys=True
        ).encode()
    ).hexdigest()
    return CategoryCatalog(paths, private, fingerprint)


async def _owned_categories(db: AsyncSession, user_id: uuid.UUID) -> list[Category]:
    return list(
        (
            await db.execute(
                select(Category)
                .where(
                    Category.user_id == user_id,
                    Category.type == "expense",
                    Category.is_active.is_(True),
                )
                .order_by(Category.id)
                .limit(settings.DOCUMENT_CATEGORY_MAX_CATEGORIES + 1)
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )


async def load_owned_category_catalog(db: AsyncSession, user_id: uuid.UUID) -> CategoryCatalog:
    return build_category_catalog(await _owned_categories(db, user_id), user_id)


async def match_category_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    supplier: str,
    supplier_tax_id: str | None,
) -> tuple[uuid.UUID, int] | None:
    tax_id = re.sub(r"[-\s]", "", supplier_tax_id or "").upper()
    if re.fullmatch(r"(?:PL)?[0-9]{10}", tax_id):
        stored_tax_id = func.regexp_replace(
            func.upper(FinancialDocument.supplier_tax_id), "[[:space:]-]+", "", "g"
        )
        match = func.regexp_replace(stored_tax_id, "^PL", "") == tax_id.removeprefix("PL")
    elif supplier.strip():
        stored_name = func.lower(
            func.btrim(
                func.regexp_replace(FinancialDocument.supplier_name, "[[:space:]]+", " ", "g")
            )
        )
        match = stored_name == func.lower(" ".join(supplier.split()))
    else:
        return None

    matches = (
        await db.execute(
            select(FinancialDocument.category_id, func.count().label("total"))
            .where(
                FinancialDocument.user_id == user_id,
                FinancialDocument.review == "approved",
                FinancialDocument.lifecycle != "cancelled",
                FinancialDocument.category_id.is_not(None),
                match,
                ~select(FinancialDocumentSource.id)
                .where(
                    FinancialDocumentSource.user_id == user_id,
                    FinancialDocumentSource.document_id == document_id,
                    FinancialDocumentSource.financial_document_id == FinancialDocument.id,
                )
                .exists(),
            )
            .group_by(FinancialDocument.category_id)
            .limit(2)
        )
    ).all()
    if len(matches) != 1 or matches[0].total < settings.DOCUMENT_CATEGORY_HISTORY_MIN_MATCHES:
        return None
    category_id = await db.scalar(
        select(Category.id).where(
            Category.id == matches[0].category_id,
            Category.user_id == user_id,
            Category.is_active.is_(True),
            Category.type == "expense",
            Category.source.not_in(EXCLUDED_CATEGORY_SOURCES),
        )
    )
    return (category_id, matches[0].total) if category_id is not None else None


async def load_document_category_catalog(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID
) -> CategoryCatalog:
    # Existing documents without an explicit new-upload/manual intent are not exported.
    intent = (
        await db.execute(
            select(DocumentFinanceDraftIntent.id).where(
                DocumentFinanceDraftIntent.user_id == user_id,
                DocumentFinanceDraftIntent.document_id == document_id,
            )
        )
    ).scalar_one_or_none()
    if intent is None:
        return CategoryCatalog()
    return await load_owned_category_catalog(db, user_id)


async def resolve_category(
    db: AsyncSession, user_id: uuid.UUID, catalog: CategoryCatalog, key: str | None
) -> uuid.UUID | None:
    if key is None or key not in catalog.private_key_map:
        return None
    current = await load_owned_category_catalog(db, user_id)
    if current.fingerprint != catalog.fingerprint:
        return None
    return current.private_key_map.get(key)
