"""Batch descriptive projections without touching source fields or ledger state."""

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.finance.annotation_models import FinanceTag, TransactionAnnotation, TransactionTag
from app.finance.models import FinancialTransaction
from app.work.models import Project


async def attach_annotations(
    db: AsyncSession,
    owner: uuid.UUID,
    transactions: list[FinancialTransaction],
) -> list[FinancialTransaction]:
    # entities imports queries during initialization; the command module also
    # depends on ledger validation. Resolve its pure builder only at read time.
    from app.finance.annotations import build_annotation_response

    if not transactions:
        return transactions
    if any(txn.user_id != owner for txn in transactions):
        raise LookupError("Transaction not found")
    ids = [txn.id for txn in transactions]
    records = {
        r.transaction_id: r
        for r in (
            await db.scalars(
                select(TransactionAnnotation)
                .where(
                    TransactionAnnotation.transaction_id.in_(ids),
                    TransactionAnnotation.user_id == owner,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    linked = (
        await db.execute(
            select(TransactionTag, FinanceTag)
            .join(
                FinanceTag,
                (FinanceTag.id == TransactionTag.tag_id)
                & (FinanceTag.user_id == TransactionTag.user_id),
            )
            .where(
                TransactionTag.transaction_id.in_(ids),
                TransactionTag.user_id == owner,
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    tags: dict[uuid.UUID, list[FinanceTag]] = defaultdict(list)
    links: dict[uuid.UUID, list[TransactionTag]] = defaultdict(list)
    for link, tag in linked:
        tags[link.transaction_id].append(tag)
        links[link.transaction_id].append(link)
    project_ids = {txn.project_id for txn in transactions if txn.project_id}
    projects = (
        {
            p.id: p
            for p in (
                await db.scalars(
                    select(Project)
                    .where(
                        Project.id.in_(project_ids),
                        Project.user_id == owner,
                    )
                    .execution_options(populate_existing=True)
                )
            ).all()
        }
        if project_ids
        else {}
    )
    for txn in transactions:
        record = records.get(txn.id)
        set_committed_value(txn, "annotation_record", record)
        set_committed_value(txn, "finance_taglinks", links[txn.id])
        txn.__dict__["_annotations"] = build_annotation_response(
            txn, record, tags[txn.id], projects.get(txn.project_id) if txn.project_id else None
        )
    return transactions
