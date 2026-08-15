import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.finance.models import CategoryBudget
from app.finance.schemas import CategoryCreate
from app.finance.service import create_category


@pytest.mark.integration
@pytest.mark.asyncio
async def test_category_budget_is_unique_per_user_and_category(db_session) -> None:
    user_id = uuid.uuid4()
    category = await create_category(
        db_session,
        user_id,
        CategoryCreate(name="Jedzenie", type="expense"),
    )

    budget = CategoryBudget(user_id=user_id, category_id=category.id, amount_pln=50_000)
    db_session.add(budget)
    await db_session.flush()

    assert budget.id is not None

    duplicate = CategoryBudget(user_id=user_id, category_id=category.id, amount_pln=70_000)
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        await db_session.flush()
