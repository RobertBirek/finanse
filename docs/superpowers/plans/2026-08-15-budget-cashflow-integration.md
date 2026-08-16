# Budget↔Cashflow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the current month's budget summary inside the cashflow forecast and warn when remaining budgets exceed projected liquidity before payday.

**Architecture:** Backend adds `CashflowBudgetSummary` to `CashflowForecastResponse`, computed via `get_budget_status` inside `get_cashflow_forecast`. Frontend renders a budget summary card in the cashflow view and derives a soft over-budget warning by comparing `remaining_pln` to `projected_balance_before_next_payday_pln`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, React 18, TypeScript, pytest, Vitest.

---

### Task 1: Backend budget summary in forecast

**Files:**
- Modify: `backend/app/finance/schemas.py`
- Modify: `backend/app/finance/service.py`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing test** that `get_cashflow_forecast` returns `budgets` with summed totals when budgets exist, and zeros when none.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement.**

  ```python
  class CashflowBudgetSummary(BaseModel):
      total_budget_pln: int
      total_spent_pln: int
      remaining_pln: int
  ```

  Add `budgets: CashflowBudgetSummary` to `CashflowForecastResponse`. In `get_cashflow_forecast`, before building the response:

  ```python
  budget_status = await get_budget_status(db, user_id, today.month, today.year)
  budget_summary = CashflowBudgetSummary(
      total_budget_pln=sum(item.budget_amount_pln for item in budget_status.items),
      total_spent_pln=sum(item.spent_pln for item in budget_status.items),
      remaining_pln=sum(item.remaining_pln for item in budget_status.items),
  )
  ```

  Pass `budgets=budget_summary` in the returned `CashflowForecastResponse`.

- [ ] **Step 4: Run focused + ruff/mypy.**

- [ ] **Step 5: Commit.**

  ```bash
  git add backend/app/finance/schemas.py backend/app/finance/service.py backend/tests/test_finance/test_cashflow.py
  git commit -m "feat: dodaj podsumowanie budżetów do prognozy"
  ```

### Task 2: Frontend budget summary card

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Modify: `frontend/src/components/finance/CashflowForecast.tsx`
- Test: `frontend/src/components/finance/CashflowForecast.test.tsx` (or existing page test)

- [ ] **Step 1: Write failing tests**: `CashflowForecast` type has `budgets`; the card shows spent/limit/remaining; a warning appears when `remaining_pln > projected_balance_before_next_payday_pln`.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement.**

  Add `CashflowBudgetSummary` type and `budgets` field to `CashflowForecast` in `finance.ts`. In `CashflowForecast.tsx`, add a "Budżety w tym miesiącu" block using `budgetProgress` and `formatPLN`, and a warning when `budgets.remaining_pln > forecast.projected_balance_before_next_payday_pln`.

- [ ] **Step 4: Run test + lint + typecheck.**

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/components/finance/CashflowForecast.tsx frontend/src/components/finance/CashflowForecast.test.tsx
  git commit -m "feat: pokaż budżety w prognozie płynności"
  ```

### Task 3: Verification, docs, deploy

- [ ] **Step 1: Run full backend + frontend gates.**

- [ ] **Step 2: Update docs, commit.**

- [ ] **Step 3: Deploy** (no migration), verify health.
