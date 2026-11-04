"""Bounded, owner/shop-local human history. Similarity is evidence, never authority."""

import uuid
from typing import Literal

from sqlalchemy import String, and_, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.finance.categorization_context import CategorizationError, digest
from app.finance.models import FinancialDocument
from app.finance.receipt_context import (
    load_receipt_context,
    receipt_category_paths,
    receipt_header_sha256,
)
from app.finance.receipt_models import (
    ReceiptItemDiscountShare as Share,
)
from app.finance.receipt_models import (
    ReceiptItemLine as Line,
)
from app.finance.receipt_models import (
    ReceiptItemRevision as Revision,
)
from app.finance.receipt_models import (
    ReceiptItemState as State,
)
from app.finance.receipt_models import (
    ReceiptStore as Store,
)
from app.finance.receipt_schemas import (
    ReceiptBody,
    ReceiptHistoryHint,
    ReceiptHistoryPage,
    ReceiptHistoryRef,
    normalize_receipt_name,
)

ALGORITHM_VERSION = "receipt-history-v1"
normalize_receipt_product_name = normalize_receipt_name


def _query(owner: uuid.UUID, bill_id: uuid.UUID, store_id: uuid.UUID):
    discounts = (
        select(func.sum(Share.amount_minor))
        .where(
            Share.user_id == Line.user_id,
            Share.revision_id == Line.revision_id,
            Share.line_key == Line.line_key,
        )
        .correlate(Line)
        .scalar_subquery()
    )
    net = Line.amount_minor - func.coalesce(discounts, 0)
    return (
        select(Line, Revision, FinancialDocument, net)
        .join(Revision, and_(Revision.id == Line.revision_id, Revision.user_id == Line.user_id))
        .join(
            State,
            and_(
                State.current_approved_revision_id == Revision.id,
                State.user_id == owner,
                State.bill_id == Revision.bill_id,
            ),
        )
        .join(
            FinancialDocument,
            and_(FinancialDocument.id == Revision.bill_id, FinancialDocument.user_id == owner),
        )
        .join(
            Store,
            and_(
                Store.id == Revision.store_id,
                Store.user_id == owner,
                Store.version == Revision.store_version,
                Store.active.is_(True),
            ),
        )
        .where(
            Line.user_id == owner,
            Revision.kind == "approved",
            Revision.store_id == store_id,
            FinancialDocument.id != bill_id,
            FinancialDocument.kind == "receipt",
            FinancialDocument.review == "approved",
            FinancialDocument.lifecycle == "active",
            FinancialDocument.currency == "PLN",
            net > 0,
        )
    )


def _hint(
    line: Line,
    revision: Revision,
    bill: FinancialDocument,
    net: int,
    paths: dict[uuid.UUID, tuple[str, str]],
    kind: Literal["exact", "prefix"],
) -> ReceiptHistoryHint | None:
    path = paths.get(line.category_id) if line.category_id else None
    if (
        not path
        or path[1] != line.category_path_sha256
        or revision.header_sha256 != receipt_header_sha256(bill)
    ):
        return None
    hashed = digest(
        {
            "bill": revision.header_sha256,
            "revision": revision.id,
            "body": revision.body_sha256,
            "store": revision.store_id,
            "store_version": revision.store_version,
            "line_key": line.line_key,
            "name": line.name,
            "category": line.category_id,
            "net": net,
            "path": path[1],
        }
    )
    assert line.category_id is not None
    return ReceiptHistoryHint(
        ref=ReceiptHistoryRef(
            source_bill_id=bill.id,
            source_revision_id=revision.id,
            source_line_key=line.line_key,
            category_id=line.category_id,
            match_kind=kind,
            algorithm_version=ALGORITHM_VERSION,
            source_sha256=hashed,
        ),
        product_name=line.name,
        category_path=path[0],
        purchased_on=bill.sale_date or bill.issue_date,
        approved_at=revision.created_at,
    )


async def get_receipt_history(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, *, store_id: uuid.UUID, name: str
) -> ReceiptHistoryPage:
    ctx = await load_receipt_context(db, owner, bill_id)
    store = await db.scalar(
        select(Store)
        .where(Store.user_id == owner, Store.id == store_id, Store.active.is_(True))
        .execution_options(populate_existing=True)
    )
    if not store:
        raise LookupError("Sklep nie istnieje.")
    normalized = normalize_receipt_name(name)
    if (
        not normalized
        or max(len(name), len(normalized)) > settings.FINANCE_RECEIPT_ITEM_NAME_MAX_CHARS
    ):
        raise CategorizationError("invalid_name", "Podaj nazwę produktu w dozwolonym limicie.", 422)
    paths = receipt_category_paths(ctx.categories, ctx.marker_id)
    for kind in ("exact", "prefix"):
        if kind == "prefix" and len(normalized) < settings.FINANCE_RECEIPT_HISTORY_PREFIX_MIN_CHARS:
            break
        predicate = (
            Line.normalized_name == normalized
            if kind == "exact"
            else and_(
                func.length(Line.normalized_name)
                >= settings.FINANCE_RECEIPT_HISTORY_PREFIX_MIN_CHARS,
                or_(
                    func.starts_with(Line.normalized_name, literal(normalized, type_=String)),
                    func.starts_with(literal(normalized, type_=String), Line.normalized_name),
                ),
            )
        )
        rows = (
            await db.execute(
                _query(owner, bill_id, store_id)
                .where(predicate)
                .order_by(Revision.created_at.desc(), Revision.id, Line.line_key)
                .limit(settings.FINANCE_RECEIPT_HISTORY_SCAN_LIMIT + 1)
            )
        ).all()
        truncated = len(rows) > settings.FINANCE_RECEIPT_HISTORY_SCAN_LIMIT
        candidates = [
            hint
            for line, rev, bill, net in rows[: settings.FINANCE_RECEIPT_HISTORY_SCAN_LIMIT]
            if (hint := _hint(line, rev, bill, net, paths, kind))
        ]
        if candidates or truncated:
            size = settings.FINANCE_RECEIPT_HISTORY_PAGE_SIZE
            return ReceiptHistoryPage(
                items=candidates[:size],
                match_kind=kind,
                conflict=len({h.ref.category_id for h in candidates}) > 1,
                has_more=truncated or len(candidates) > size,
                history_incomplete=truncated,
            )
    return ReceiptHistoryPage(
        items=[], match_kind="none", conflict=False, has_more=False, history_incomplete=False
    )


async def validate_receipt_history_refs(
    db: AsyncSession, owner: uuid.UUID, bill_id: uuid.UUID, body: ReceiptBody
) -> dict[uuid.UUID, ReceiptHistoryRef]:
    wanted = {r.line_key: r for r in body.lines if r.hint}
    if not wanted:
        return {}
    ids = {r.hint.source_revision_id for r in wanted.values() if r.hint}
    own_ids = set(
        (
            await db.scalars(
                select(Revision.id)
                .join(FinancialDocument, FinancialDocument.id == Revision.bill_id)
                .where(
                    Revision.id.in_(ids),
                    Revision.user_id == owner,
                    FinancialDocument.user_id == owner,
                )
            )
        ).all()
    )
    if own_ids != ids:
        raise LookupError("Źródło wskazówki nie istnieje.")
    if not body.store_id:
        raise CategorizationError("hint_changed", "Wskazówka wymaga tego samego sklepu.")
    ctx = await load_receipt_context(db, owner, bill_id)
    paths = receipt_category_paths(ctx.categories, ctx.marker_id)
    pairs = [(r.hint.source_revision_id, r.hint.source_line_key) for r in wanted.values() if r.hint]
    rows = (
        await db.execute(
            _query(owner, bill_id, body.store_id).where(
                tuple_(Line.revision_id, Line.line_key).in_(pairs)
            )
        )
    ).all()
    sources = {
        (line.revision_id, line.line_key): (line, rev, bill, net) for line, rev, bill, net in rows
    }
    result = {}
    for key, row in wanted.items():
        ref = row.hint
        assert ref is not None
        source = sources.get((ref.source_revision_id, ref.source_line_key))
        if source is None:
            raise CategorizationError(
                "hint_changed", "Źródło wskazówki zmieniło się; sprawdź kategorię ponownie."
            )
        hint = _hint(*source, paths, ref.match_kind)
        current = normalize_receipt_name(row.name)
        old = normalize_receipt_name(source[0].name)
        match = (
            current == old
            if ref.match_kind == "exact"
            else min(len(current), len(old)) >= settings.FINANCE_RECEIPT_HISTORY_PREFIX_MIN_CHARS
            and (current.startswith(old) or old.startswith(current))
        )
        if (
            not hint
            or hint.ref != ref
            or ref.algorithm_version != ALGORITHM_VERSION
            or row.category_id != ref.category_id
            or not match
        ):
            raise CategorizationError(
                "hint_changed", "Wskazówka nie pasuje do aktualnego produktu, sklepu lub kategorii."
            )
        result[key] = ref
    return result
