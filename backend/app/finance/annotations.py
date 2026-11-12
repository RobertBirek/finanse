"""Human-owned descriptions and labels, never source or monetary corrections."""

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import log_event
from app.config import settings
from app.finance.annotation_models import FinanceTag, TransactionAnnotation, TransactionTag
from app.finance.annotation_schemas import (
    AnnotationResponse,
    AnnotationTag,
    AnnotationUpdate,
    annotation_limits,
    normalize_tag,
)
from app.finance.categorization_context import digest
from app.finance.document_guards import lock_document_mutations
from app.finance.models import FinanceCommandReceipt, FinancialTransaction
from app.work.models import Project

ACTION = "update_transaction_annotations"


class AnnotationError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def build_annotation_response(
    txn: FinancialTransaction,
    record: TransactionAnnotation | None,
    tags: list[FinanceTag],
    project: Project | None,
) -> AnnotationResponse:
    ordered = sorted(tags, key=lambda t: (t.normalized_name, str(t.id)))
    values = {
        "display_description": record.display_description if record else None,
        "original_description": txn.description,
        "note": record.note if record else None,
        "tags": [AnnotationTag.model_validate(t) for t in ordered],
        "project_id": txn.project_id,
        "project_name": project.name if project else None,
        "version": record.version if record else 0,
    }
    return AnnotationResponse.model_validate(
        {
            **values,
            "limits": annotation_limits(),
            "context_snapshot": digest(
                {
                    "annotation": {
                        **values,
                        "tags": [{"id": t.id, "name": t.name} for t in ordered],
                    },
                    "transaction_id": txn.id,
                    "transaction_updated_at": txn.updated_at,
                }
            ),
        }
    )


async def _load(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    *,
    lock: bool = False,
) -> tuple[FinancialTransaction, TransactionAnnotation | None, list[FinanceTag], Project | None]:
    stmt = (
        select(FinancialTransaction)
        .where(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.user_id == owner,
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    txn = await db.scalar(stmt)
    if txn is None:
        raise LookupError("Transaction not found")
    record_stmt = (
        select(TransactionAnnotation)
        .where(
            TransactionAnnotation.transaction_id == transaction_id,
            TransactionAnnotation.user_id == owner,
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        record_stmt = record_stmt.with_for_update()
    record = await db.scalar(record_stmt)
    tags = list(
        (
            await db.scalars(
                select(FinanceTag)
                .join(
                    TransactionTag,
                    (TransactionTag.tag_id == FinanceTag.id)
                    & (TransactionTag.user_id == FinanceTag.user_id),
                )
                .where(
                    TransactionTag.transaction_id == transaction_id, TransactionTag.user_id == owner
                )
            )
        ).all()
    )
    project = (
        await db.scalar(
            select(Project)
            .where(Project.id == txn.project_id, Project.user_id == owner)
            .execution_options(populate_existing=True)
        )
        if txn.project_id
        else None
    )
    return txn, record, tags, project


async def get_annotations(
    db: AsyncSession, owner: uuid.UUID, transaction_id: uuid.UUID
) -> AnnotationResponse:
    return build_annotation_response(*await _load(db, owner, transaction_id))


async def list_annotation_tags(
    db: AsyncSession, owner: uuid.UUID, *, q: str, limit: int
) -> list[AnnotationTag]:
    _, key = normalize_tag(q)
    stmt = select(FinanceTag).where(FinanceTag.user_id == owner)
    if key:
        stmt = stmt.where(FinanceTag.normalized_name.contains(key, autoescape=True))
    tags = await db.scalars(
        stmt.order_by(FinanceTag.normalized_name, FinanceTag.id).limit(
            max(0, min(limit, settings.FINANCE_TAG_PAGE_SIZE))
        )
    )
    return [AnnotationTag.model_validate(tag) for tag in tags]


async def update_annotations(
    db: AsyncSession,
    owner: uuid.UUID,
    transaction_id: uuid.UUID,
    data: AnnotationUpdate,
    *,
    idempotency_key: str,
) -> AnnotationResponse:
    if (
        await db.scalar(
            select(FinancialTransaction.id).where(
                FinancialTransaction.id == transaction_id, FinancialTransaction.user_id == owner
            )
        )
        is None
    ):
        raise LookupError("Transaction not found")
    await db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtext(f"transaction-annotation:{owner}:{idempotency_key}")
            )
        )
    )
    request_hash = digest({"transaction_id": transaction_id, **data.model_dump(mode="json")})
    receipt = await db.scalar(
        select(FinanceCommandReceipt).where(
            FinanceCommandReceipt.user_id == owner,
            FinanceCommandReceipt.action == ACTION,
            FinanceCommandReceipt.key == idempotency_key,
        )
    )
    if receipt:
        if receipt.request_hash != request_hash:
            raise AnnotationError(
                "idempotency_key_reused", "Ten klucz zapisu dotyczy innej zmiany."
            )
        return AnnotationResponse.model_validate(receipt.response_json)
    await lock_document_mutations(db, owner)
    # Project DELETE takes the project row then updates referencing transactions.
    # Match that order before the transaction lock to avoid an FK SET NULL cycle.
    target_project = (
        await db.scalar(
            select(Project)
            .where(
                Project.id == data.project_id,
                Project.user_id == owner,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if data.project_id
        else None
    )
    txn, record, old_tags, project = await _load(db, owner, transaction_id, lock=True)
    before = build_annotation_response(txn, record, old_tags, project)
    if (
        before.version != data.expected_version
        or before.context_snapshot != data.expected_context_snapshot
    ):
        raise AnnotationError(
            "annotation_snapshot_conflict",
            "Dane zmieniły się. Odśwież transakcję i sprawdź oznaczenia ponownie.",
        )
    if data.project_id and target_project is None:
        raise AnnotationError("invalid_project", "Wybierz własny, istniejący projekt.", 422)
    # Validate all fields before any tag is inserted, including direct service calls.
    data = AnnotationUpdate.model_validate(data.model_dump())
    tags: list[FinanceTag] = []
    for key, name in sorted((normalize_tag(n)[1], normalize_tag(n)[0]) for n in data.tags):
        await db.execute(
            insert(FinanceTag)
            .values(user_id=owner, name=name, normalized_name=key)
            .on_conflict_do_nothing(constraint="uq_finance_tag_owner_name")
        )
        tag = await db.scalar(
            select(FinanceTag).where(FinanceTag.user_id == owner, FinanceTag.normalized_name == key)
        )
        assert tag is not None
        tags.append(tag)
    changed = (
        before.display_description != data.display_description
        or before.note != data.note
        or before.project_id != data.project_id
        or {t.id for t in old_tags} != {t.id for t in tags}
    )
    if changed:
        if record is None:
            record = TransactionAnnotation(transaction_id=txn.id, user_id=owner, version=1)
            db.add(record)
        else:
            record.version += 1
        record.display_description, record.note = data.display_description, data.note
        if txn.project_id != data.project_id:
            txn.project_id = data.project_id
        await db.execute(
            delete(TransactionTag).where(
                TransactionTag.transaction_id == txn.id, TransactionTag.user_id == owner
            )
        )
        db.add_all(
            [TransactionTag(transaction_id=txn.id, user_id=owner, tag_id=tag.id) for tag in tags]
        )
        await db.flush()
        await db.refresh(txn, attribute_names=["updated_at"])
    result = build_annotation_response(txn, record, tags, target_project)
    if changed:
        await log_event(
            db,
            owner,
            "financial_transaction",
            str(txn.id),
            ACTION,
            old_state=before.model_dump(mode="json"),
            new_state=result.model_dump(mode="json"),
        )
    db.add(
        FinanceCommandReceipt(
            user_id=owner,
            action=ACTION,
            key=idempotency_key,
            request_hash=request_hash,
            entity_id=txn.id,
            result_ids=[str(txn.id)],
            version=result.version,
            response_json=result.model_dump(mode="json"),
        )
    )
    await db.flush()
    return result
