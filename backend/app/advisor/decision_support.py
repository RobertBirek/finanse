from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor.decision_schemas import AttentionItem, AttentionResult
from app.documents.service import get_documents
from app.finance.cashflow import get_cashflow_forecast
from app.finance.dates import _local_today
from app.work.service import get_overdue_tasks

_LIMIT = 3


async def get_attention(
    db: AsyncSession, user_id: UUID, *, today: date | None = None
) -> AttentionResult:
    today = today or _local_today()
    forecast = await get_cashflow_forecast(db, user_id, today=today)
    documents = await get_documents(db, user_id, limit=_LIMIT, worklist="review")
    tasks = await get_overdue_tasks(db, user_id, before=today, limit=_LIMIT)
    ranked: list[tuple[int, AttentionItem]] = []
    seen: set[str] = set()
    for payment in forecast.suggestions:
        due = payment.due_date
        key = payment.source_key
        if (
            payment.type != "expense"
            or payment.status == "matched_actual"
            or not key
            or key in seen
            or due is None
            or due > today + timedelta(days=6)
        ):
            continue
        seen.add(key)
        if due < today:
            rank, reason = 0, "Termin minął; sprawdź status płatności w prognozie."
        elif due == today:
            rank, reason = 1, "Termin płatności przypada dziś."
        else:
            rank, reason = 4, "Termin płatności przypada w ciągu siedmiu dni."
        ranked.append(
            (
                rank,
                AttentionItem(
                    kind="payment",
                    source_id=key,
                    title=payment.name,
                    due_date=due,
                    reason=reason,
                    href="/finances/cashflow",
                ),
            )
        )
    ranked.extend(
        (
            2,
            AttentionItem(
                kind="document",
                source_id=str(doc.id),
                title=doc.original_name,
                reason="Dokument czeka na przegląd.",
                href="/documents?worklist=review",
            ),
        )
        for doc in documents
    )
    ranked.extend(
        (
            3,
            AttentionItem(
                kind="task",
                source_id=str(task.id),
                title=task.title,
                due_date=task.due_date,
                reason="Termin otwartego zadania minął.",
                href=f"/projects/{task.project_id}" if task.project_id else "/today",
            ),
        )
        for task in tasks
    )
    ranked.sort(
        key=lambda pair: (
            pair[0],
            pair[1].due_date or date.max,
            pair[1].kind,
            pair[1].source_id,
        )
    )
    return AttentionResult(as_of=today, items=[row for _, row in ranked[:_LIMIT]])
