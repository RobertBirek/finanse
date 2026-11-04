"""Read, canonicalize and validate evidence for an owner-approved expense split."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.categorization_schemas import (
    CategorizationContext,
    CategorizationEligibility,
    CategorizationPart,
    CategorizationPreview,
)
from app.finance.document_guards import lock_document_mutations
from app.finance.ledger_validation import _validate_posting_sum
from app.finance.models import (
    Account,
    ActualImportMapping,
    Category,
    DocumentPaymentAllocation,
    FinancialTransaction,
    LoanPaymentLink,
    Posting,
    TransactionCategorizationState,
    TransactionDateMetadata,
)
from app.finance.rule_models import TransactionCategorizationOrigin
from app.finance.rule_schemas import AssignmentOrigin


class CategorizationError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 409) -> None:
        self.code, self.status = code, status
        super().__init__(detail)


def canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, ".6f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def columns(row: Any) -> dict[str, Any]:
    return canonical({c.key: getattr(row, c.key) for c in row.__mapper__.column_attrs})


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def normalized_parts(parts: list[CategorizationPart]) -> list[dict[str, Any]]:
    return [p.model_dump(mode="json") for p in sorted(parts, key=lambda p: str(p.category_id))]


@dataclass
class LedgerContext:
    txn: FinancialTransaction
    state: TransactionCategorizationState | None
    categories: dict[uuid.UUID, Category]
    account: Account | None
    mappings: list[ActualImportMapping]
    loans: list[LoanPaymentLink]
    allocations: list[DocumentPaymentAllocation]
    dates: TransactionDateMetadata | None
    origin: TransactionCategorizationOrigin | None = None
    origin_grant: dict[str, Any] | None = None

    def snapshot(self) -> str:
        # Complete mapped financial fields. State hash/timestamps excluded to avoid
        # recursion; link absence explicit and ordering deterministic in load().
        return digest(
            {
                "schema": "expense-categorization-v2",
                "origin": {
                    "id": str(self.origin.id),
                    "origin": self.origin.origin,
                    "version": self.origin.version,
                    "rule_id": self.origin.rule_id,
                    "rule_version": self.origin.rule_version,
                    "approval_snapshot_sha256": self.origin.approval_snapshot_sha256,
                }
                if self.origin
                else None,
                "transaction": columns(self.txn),
                "postings": [
                    columns(p) for p in sorted(self.txn.postings, key=lambda p: str(p.id))
                ],
                "account": columns(self.account) if self.account else None,
                "dates": columns(self.dates) if self.dates else None,
                "state": {
                    "id": str(self.state.id),
                    "version": self.state.version,
                    "source": self.state.source,
                }
                if self.state
                else None,
                "mappings": [columns(x) for x in self.mappings],
                "loans": [columns(x) for x in self.loans],
                "allocations": [columns(x) for x in self.allocations],
            }
        )

    def eligibility(self) -> CategorizationEligibility:
        def denied(code: str, message: str) -> CategorizationEligibility:
            return CategorizationEligibility(allowed=False, reason_code=code, message=message)

        t = self.txn
        if t.source not in {"manual", "document_payment"} or self.mappings or self.loans:
            return denied("protected", "Historia importu lub płatność pożyczki jest chroniona.")
        if t.type != "expense" or t.is_pending:
            return denied("unsupported", "Podział obsługuje zaksięgowane wydatki PLN.")
        accounts = [p for p in t.postings if p.account_id is not None]
        cats = [p for p in t.postings if p.account_id is None and p.category_id is not None]
        if len(accounts) != 1 or len(cats) + 1 != len(t.postings) or not cats:
            return denied("ledger_shape", "Ten układ zapisów księgi nie obsługuje podziału.")
        a = accounts[0]
        if (
            self.account is None
            or self.account.user_id != t.user_id
            or self.account.currency != "PLN"
        ):
            return denied("account_currency", "Konto płatności musi być własnym kontem PLN.")
        if a.category_id is not None or a.direction != "debit":
            return denied("ledger_shape", "Nieprawidłowa strona zapisu płatności.")
        if any(
            p.source_currency != "PLN"
            or Decimal(str(p.fx_rate)) != 1
            or p.source_amount != p.base_amount_pln
            or p.source_amount <= 0
            for p in t.postings
        ):
            return denied(
                "currency_or_refund", "Podział obsługuje dodatnie wydatki PLN bez przewalutowania."
            )
        if any(
            p.direction != "credit"
            or p.category_id not in self.categories
            or self.categories[p.category_id].type != "expense"
            for p in cats
        ):
            return denied("ledger_shape", "Nieprawidłowa strona kategorii wydatku.")
        if (
            len({p.category_id for p in cats}) != len(cats)
            or len({p.is_budget_impact for p in cats}) != 1
        ):
            return denied("ledger_shape", "Niejednoznaczny układ kategorii lub wpływu na budżet.")
        if any(p.source_amount > MAX_SAFE_MINOR for p in t.postings):
            return denied(
                "amount_out_of_range", "Kwota przekracza zakres obsługiwany przez edytor."
            )
        if any(x.posting_id != a.id or x.user_id != t.user_id for x in self.allocations):
            return denied("allocation_shape", "Powiązanie dokumentu nie wskazuje strony kontowej.")
        if self.state and self.state.user_id != t.user_id:
            return denied("ledger_shape", "Nieprawidłowy właściciel stanu kategoryzacji.")
        try:
            _validate_posting_sum(t.postings, t.type)
        except ValueError:
            return denied("ledger_shape", "Transakcja nie jest zbilansowana.")
        return CategorizationEligibility(allowed=True)

    def response(self) -> CategorizationContext:
        eligibility = self.eligibility()
        account = next((p for p in self.txn.postings if p.account_id), None)
        safe = account is not None and 0 < account.source_amount <= MAX_SAFE_MINOR
        parts = (
            [
                CategorizationPart(category_id=p.category_id, amount_minor=p.source_amount)
                for p in self.txn.postings
                if p.category_id
            ]
            if eligibility.allowed
            else []
        )
        return CategorizationContext(
            transaction_id=self.txn.id,
            eligibility=eligibility,
            amount_minor=account.source_amount if account is not None and safe else None,
            currency=account.source_currency if account else None,
            parts=sorted(parts, key=lambda p: str(p.category_id)),
            version=self.state.version if self.state else 0,
            source="manual" if self.state else None,
            context_snapshot=self.snapshot(),
            max_parts=settings.FINANCE_CATEGORY_SPLIT_MAX_PARTS,
            assignment_origin=AssignmentOrigin(
                origin="approved_rule" if self.origin.origin == "approved_rule" else "manual",
                version=self.origin.version,
                rule_id=self.origin.rule_id,
                rule_version=self.origin.rule_version,
                display_description=self.origin_grant.get("display_description")
                if self.origin_grant
                else None,
                target_path=self.origin_grant.get("target_path") if self.origin_grant else None,
            )
            if self.origin
            else None,
        )


async def load_context(
    db: AsyncSession, user: uuid.UUID, txn_id: uuid.UUID, *, lock: bool = False
) -> LedgerContext:
    if lock:
        await lock_document_mutations(db, user)
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"category-tree:{user}"))))
    stmt = (
        select(FinancialTransaction)
        .where(FinancialTransaction.id == txn_id, FinancialTransaction.user_id == user)
        .options(selectinload(FinancialTransaction.postings))
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    txn = await db.scalar(stmt)
    if txn is None:
        raise LookupError("Transaction not found")
    if lock:
        txn.postings = list(
            (
                await db.scalars(
                    select(Posting)
                    .where(Posting.transaction_id == txn_id)
                    .order_by(Posting.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
    state_stmt = (
        select(TransactionCategorizationState)
        .where(TransactionCategorizationState.transaction_id == txn_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        state_stmt = state_stmt.with_for_update()
    state = await db.scalar(state_stmt)
    origin_stmt = (
        select(TransactionCategorizationOrigin)
        .where(TransactionCategorizationOrigin.transaction_id == txn_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        origin_stmt = origin_stmt.with_for_update()
    origin = await db.scalar(origin_stmt)
    origin_grant: dict[str, Any] | None = None
    if origin and origin.user_id != user:
        raise CategorizationError("protected", "Nieprawidłowy właściciel proweniencji.")
    if origin and origin.approval_receipt_id:
        from app.finance.models import FinanceCommandReceipt

        receipt = await db.scalar(
            select(FinanceCommandReceipt).where(
                FinanceCommandReceipt.id == origin.approval_receipt_id,
                FinanceCommandReceipt.user_id == user,
            )
        )
        if receipt:
            value = receipt.response_json.get("grant")
            if isinstance(value, dict):
                origin_grant = value
    cat_stmt = (
        select(Category)
        .where(Category.user_id == user)
        .order_by(Category.id)
        .execution_options(populate_existing=True)
    )
    if lock:
        cat_stmt = cat_stmt.with_for_update()
    categories = {x.id: x for x in (await db.scalars(cat_stmt)).all()}
    account_id = next((p.account_id for p in txn.postings if p.account_id), None)
    account = (
        await db.scalar(
            select(Account)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )
        if account_id
        else None
    )
    mappings = list(
        (
            await db.scalars(
                select(ActualImportMapping)
                .where(
                    ActualImportMapping.entity_type == "transaction",
                    ActualImportMapping.entity_id == txn_id,
                )
                .order_by(ActualImportMapping.id)
            )
        ).all()
    )
    loans = list(
        (
            await db.scalars(
                select(LoanPaymentLink)
                .where(LoanPaymentLink.transaction_id == txn_id)
                .order_by(LoanPaymentLink.id)
            )
        ).all()
    )
    allocations = list(
        (
            await db.scalars(
                select(DocumentPaymentAllocation)
                .join(Posting, Posting.id == DocumentPaymentAllocation.posting_id)
                .where(Posting.transaction_id == txn_id)
                .order_by(DocumentPaymentAllocation.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    dates = await db.scalar(
        select(TransactionDateMetadata)
        .where(TransactionDateMetadata.transaction_id == txn_id)
        .execution_options(populate_existing=True)
    )
    return LedgerContext(
        txn, state, categories, account, mappings, loans, allocations, dates, origin, origin_grant
    )


def build_preview(ctx: LedgerContext, parts: list[CategorizationPart]) -> CategorizationPreview:
    eligibility = ctx.eligibility()
    if not eligibility.allowed:
        raise CategorizationError(
            eligibility.reason_code or "protected", eligibility.message or "Operacja chroniona"
        )
    amount = next(p.source_amount for p in ctx.txn.postings if p.account_id)
    if sum(p.amount_minor for p in parts) != amount:
        raise CategorizationError(
            "split_sum", "Suma kategorii musi odpowiadać kwocie płatności co do grosza.", 422
        )
    paths: dict[str, str] = {}
    targets: dict[uuid.UUID, Category] = {}
    for part in parts:
        category = ctx.categories.get(part.category_id)
        if not category or not category.is_active or category.type != "expense":
            raise CategorizationError(
                "invalid_category", "Wybierz własne, aktywne kategorie wydatków.", 422
            )
        visited: set[uuid.UUID] = set()
        names = []
        while category is not None:
            if category.id in visited or category.type != "expense":
                raise CategorizationError(
                    "invalid_category", "Nieprawidłowe drzewo kategorii.", 422
                )
            visited.add(category.id)
            targets[category.id] = category
            names.append(category.name)
            if category.parent_id and category.parent_id not in ctx.categories:
                raise CategorizationError(
                    "invalid_category", "Nieprawidłowe drzewo kategorii.", 422
                )
            category = ctx.categories.get(category.parent_id) if category.parent_id else None
        paths[str(part.category_id)] = " / ".join(reversed(names))
    response = ctx.response()
    token = digest(
        {
            "context": response.context_snapshot,
            "parts": normalized_parts(parts),
            "targets": [columns(targets[key]) for key in sorted(targets, key=str)],
        }
    )
    return CategorizationPreview(
        expected_version=response.version,
        preview_snapshot=token,
        before_parts=response.parts,
        after_parts=sorted(parts, key=lambda p: str(p.category_id)),
        target_paths=paths,
    )
