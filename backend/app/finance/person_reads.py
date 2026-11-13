"""Owner-scoped gift projections, independent of account balance/report queries."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.finance.annotation_reads import attach_annotations
from app.finance.models import FinancialTransaction, Posting
from app.finance.person_context import PersonError
from app.finance.person_models import FinancePerson, PersonTransactionLink
from app.finance.person_schemas import PersonGiftPage, PersonPage, PersonResponse, PersonSummary
from app.finance.rule_origin_reads import attach_assignment_origins
from app.finance.schemas import TransactionResponse


def _page(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise PersonError("invalid_page", "Nieprawidłowa strona wyników.", 422)


async def get_person(db: AsyncSession, owner: uuid.UUID, person_id: uuid.UUID) -> PersonResponse:
    row = await db.scalar(
        select(FinancePerson).where(FinancePerson.id == person_id, FinancePerson.user_id == owner)
    )
    if row is None:
        raise LookupError("Person not found")
    return PersonResponse.model_validate(row)


async def list_people(
    db: AsyncSession,
    owner: uuid.UUID,
    *,
    include_archived: bool = False,
    reference_account_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> PersonPage:
    _page(limit, offset)
    criteria = [FinancePerson.user_id == owner]
    if not include_archived:
        criteria.append(FinancePerson.is_active.is_(True))
    if reference_account_id is not None:
        criteria.append(FinancePerson.reference_account_id == reference_account_id)
    total = await db.scalar(select(func.count()).select_from(FinancePerson).where(*criteria))
    rows = (
        await db.scalars(
            select(FinancePerson)
            .where(*criteria)
            .order_by(FinancePerson.name, FinancePerson.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PersonPage(
        items=[PersonResponse.model_validate(row) for row in rows],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


async def get_person_summary(
    db: AsyncSession, owner: uuid.UUID, person_id: uuid.UUID
) -> PersonSummary:
    await get_person(db, owner, person_id)
    groups = (
        await db.execute(
            select(
                Posting.source_currency,
                func.count(func.distinct(FinancialTransaction.id)),
                func.sum(Posting.base_amount_pln),
                func.sum(Posting.source_amount),
            )
            .join(FinancialTransaction, FinancialTransaction.id == Posting.transaction_id)
            .join(
                PersonTransactionLink,
                PersonTransactionLink.transaction_id == FinancialTransaction.id,
            )
            .where(
                PersonTransactionLink.user_id == owner,
                PersonTransactionLink.person_id == person_id,
                PersonTransactionLink.kind == "gift_received",
                FinancialTransaction.user_id == owner,
                Posting.account_id.is_not(None),
                Posting.category_id.is_(None),
                Posting.direction == "credit",
            )
            .group_by(Posting.source_currency)
        )
    ).all()
    return PersonSummary(
        person_id=person_id,
        gift_count=sum(g[1] for g in groups),
        received_gifts_pln=sum(g[2] for g in groups),
        received_by_currency={g[0]: int(g[3]) for g in groups},
    )


async def get_person_gifts(
    db: AsyncSession, owner: uuid.UUID, person_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> PersonGiftPage:
    _page(limit, offset)
    await get_person(db, owner, person_id)
    linked = select(PersonTransactionLink.transaction_id).where(
        PersonTransactionLink.user_id == owner,
        PersonTransactionLink.person_id == person_id,
        PersonTransactionLink.kind == "gift_received",
    )
    criteria = [FinancialTransaction.user_id == owner, FinancialTransaction.id.in_(linked)]
    total = await db.scalar(select(func.count()).select_from(FinancialTransaction).where(*criteria))
    txns = list(
        (
            await db.scalars(
                select(FinancialTransaction)
                .where(*criteria)
                .options(
                    selectinload(FinancialTransaction.postings),
                )
                .order_by(
                    FinancialTransaction.date.desc(),
                    FinancialTransaction.created_at.desc(),
                    FinancialTransaction.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )
    txns = await attach_annotations(db, owner, await attach_assignment_origins(db, owner, txns))
    return PersonGiftPage(
        items=[TransactionResponse.model_validate(t) for t in txns],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
