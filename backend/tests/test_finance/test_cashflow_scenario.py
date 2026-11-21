from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.advisor import router as routes
from app.database import get_db
from app.finance.schemas import CashflowBudgetSummary, CashflowDay, CashflowForecastResponse
from app.identity.router import get_current_user


def _forecast() -> CashflowForecastResponse:
    return CashflowForecastResponse(
        opening_balance_pln=25000,
        last_payday=date(2026, 10, 10),
        next_payday=date(2026, 11, 10),
        projected_balance_before_next_payday_pln=None,
        safe_daily_limit_pln=None,
        lowest_balance_pln=12000,
        lowest_balance_before_payday=CashflowDay(
            date=date(2026, 11, 3), projected_balance_pln=12000
        ),
        days=[
            CashflowDay(date=date(2026, 11, 2), projected_balance_pln=20000),
            CashflowDay(date=date(2026, 11, 3), projected_balance_pln=12000),
        ],
        suggestions=[],
        budgets=CashflowBudgetSummary(total_budget_pln=0, total_spent_pln=0, remaining_pln=0),
        has_excluded_obligations=True,
        excluded_obligation_reasons=["recurring_amount_unknown"],
    )


def test_one_off_expense_only_changes_later_closing_balances():
    from app.finance.cashflow_scenario import simulate_expense

    forecast = _forecast()
    result = simulate_expense(forecast, expense_date=date(2026, 11, 2), amount_pln_minor=15000)
    assert result.baseline_minimum is not None
    assert result.baseline_minimum.projected_balance_pln == 12000
    assert result.scenario_minimum.projected_balance_pln == -3000
    assert result.scenario_minimum.date == result.first_negative_date == date(2026, 11, 3)
    assert not result.covers_day_before_payday
    assert result.excluded_obligation_reasons == ["recurring_amount_unknown"]
    assert [day.projected_balance_pln for day in forecast.days] == [20000, 12000]


def test_last_day_is_allowed_and_opening_deficit_is_separate():
    from app.finance.cashflow_scenario import simulate_expense

    forecast = _forecast().model_copy(update={"opening_balance_pln": -100})
    result = simulate_expense(forecast, expense_date=date(2026, 11, 3), amount_pln_minor=1000)
    assert result.opening_balance_negative
    assert result.scenario_minimum.projected_balance_pln == -100
    assert result.first_negative_date is None


@pytest.mark.parametrize("day", [1, 4])
def test_date_outside_forecast_rejected(day):
    from app.finance.cashflow_scenario import simulate_expense

    with pytest.raises(ValueError, match="horyzon"):
        simulate_expense(_forecast(), expense_date=date(2026, 11, day), amount_pln_minor=1000)


async def test_scenario_http_validates_input_and_does_not_write_or_call_openai(monkeypatch):
    db = AsyncMock()
    owner = SimpleNamespace(id=uuid4())
    forecast = AsyncMock(return_value=_forecast())
    model = AsyncMock()
    monkeypatch.setattr(routes, "get_cashflow_forecast", forecast)
    monkeypatch.setattr(routes, "explain_facts", model)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/decisions/cashflow-scenario"
        assert (
            await client.post(
                path,
                json={
                    "expense_date": "2026-11-03",
                    "amount_pln_minor": True,
                },
            )
        ).status_code == 422
        forecast.assert_not_awaited()
        assert (
            await client.post(
                path,
                json={
                    "expense_date": "2026-11-04",
                    "amount_pln_minor": 15000,
                },
            )
        ).status_code == 422
        response = await client.post(
            path,
            json={
                "expense_date": "2026-11-03",
                "amount_pln_minor": 15000,
            },
        )
    assert response.status_code == 200
    assert response.json()["scenario_minimum"]["projected_balance_pln"] == -3000
    assert forecast.await_count == 2
    forecast.assert_awaited_with(db, owner.id)
    assert db.mock_calls == []
    model.assert_not_awaited()
