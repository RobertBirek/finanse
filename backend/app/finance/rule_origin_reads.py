"""Batched optional provenance projection, not new ledger columns or amounts."""

import uuid

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.models import FinanceCommandReceipt, FinancialTransaction
from app.finance.rule_models import TransactionCategorizationOrigin as Origin
from app.finance.rule_schemas import AssignmentOrigin


async def attach_assignment_origins(
    db: AsyncSession, owner: uuid.UUID, transactions: list[FinancialTransaction]
) -> list[FinancialTransaction]:
    if not transactions:
        return transactions
    rows = (
        await db.execute(
            select(Origin, FinanceCommandReceipt.response_json)
            .outerjoin(
                FinanceCommandReceipt,
                and_(
                    FinanceCommandReceipt.id == Origin.approval_receipt_id,
                    FinanceCommandReceipt.user_id == owner,
                ),
            )
            .where(Origin.user_id == owner, Origin.transaction_id.in_([t.id for t in transactions]))
        )
    ).all()
    origins = {}
    for origin, response in rows:
        grant = response.get("grant", {}) if response else {}
        origins[origin.transaction_id] = AssignmentOrigin(
            origin="approved_rule" if origin.origin == "approved_rule" else "manual",
            version=origin.version,
            rule_id=origin.rule_id,
            rule_version=origin.rule_version,
            display_description=grant.get("display_description"),
            target_path=grant.get("target_path"),
        )
    for txn in transactions:
        txn.assignment_origin = origins.get(txn.id)
    return transactions
