from datetime import date, timedelta

from pydantic import BaseModel, Field, StrictInt

from app.finance.bills_schemas import MAX_SAFE_MINOR
from app.finance.schemas import CashflowDay, CashflowForecastResponse


class CashflowScenarioInput(BaseModel):
    expense_date: date
    amount_pln_minor: StrictInt = Field(gt=0, le=MAX_SAFE_MINOR)


class CashflowScenarioResult(BaseModel):
    baseline_minimum: CashflowDay
    scenario_minimum: CashflowDay
    first_negative_date: date | None
    opening_balance_negative: bool
    next_payday: date
    forecast_start: date
    forecast_end: date
    excluded_obligation_reasons: list[str]
    covers_day_before_payday: bool


def simulate_expense(
    forecast: CashflowForecastResponse, *, expense_date: date, amount_pln_minor: int
) -> CashflowScenarioResult:
    days = forecast.days
    if not days or not any(day.date == expense_date for day in days):
        raise ValueError("Data wydatku jest poza horyzontem prognozy.")
    if not 0 < amount_pln_minor <= MAX_SAFE_MINOR:
        raise ValueError("Nieprawidłowa kwota wydatku.")
    opening = CashflowDay(date=days[0].date, projected_balance_pln=forecast.opening_balance_pln)
    adjusted = [
        CashflowDay(
            date=day.date,
            projected_balance_pln=day.projected_balance_pln
            - (amount_pln_minor if day.date >= expense_date else 0),
        )
        for day in days
    ]

    def minimum(entries: list[CashflowDay]) -> CashflowDay:
        return min(entries, key=lambda point: (point.projected_balance_pln, point.date))

    return CashflowScenarioResult(
        baseline_minimum=minimum([opening, *days]),
        scenario_minimum=minimum([opening, *adjusted]),
        first_negative_date=next(
            (day.date for day in adjusted if day.projected_balance_pln < 0), None
        ),
        opening_balance_negative=opening.projected_balance_pln < 0,
        next_payday=forecast.next_payday,
        forecast_start=days[0].date,
        forecast_end=days[-1].date,
        excluded_obligation_reasons=forecast.excluded_obligation_reasons,
        covers_day_before_payday=days[-1].date >= forecast.next_payday - timedelta(days=1),
    )
