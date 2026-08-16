# Budżety w prognozie płynności — specyfikacja

## Cel

Pokazać w prognozie płynności podsumowanie budżetów bieżącego miesiąca i
ostrzec, gdy suma pozostałych limitów przekracza prognozowane saldo przed
wypłatą (sygnał przekroczenia dyscypliny względem płynności, nie twardy zakaz).

## Backend

- Schemat `CashflowBudgetSummary {total_budget_pln, total_spent_pln,
  remaining_pln}`.
- Pole `budgets: CashflowBudgetSummary` w `CashflowForecastResponse`.
- `get_cashflow_forecast` liczy je z `get_budget_status(db, user_id,
  today.month, today.year)`: sumy limitów, wydatków i pozostałości; przy braku
  budżetów zwraca zera.

## Frontend

- Typ `CashflowBudgetSummary` i pole `budgets` w `CashflowForecast`.
- W widoku cashflow (karta prognozy) sekcja „Budżety w tym miesiącu": wydano,
  limit, pozostało, pasek postępu; ostrzeżenie, gdy `remaining_pln >
  projected_balance_before_next_payday_pln`.

## Poza zakresem

- Integracja limitów z dzienną osią prognozy; budżety przychodów; nadpisania
  budżetów per miesiąc.

## Testy

Backend: prognoza zawiera sumę budżetów (z budżetami i bez). Frontend: karta i
logika ostrzeżenia.
