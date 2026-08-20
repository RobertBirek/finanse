# Finance pages and cashflow management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build usable financial subpages and a human-confirmed cashflow workflow for configuring pay cycles, scheduling items, forecasting liquidity, and recording confirmed suggestions.

**Architecture:** Keep the double-entry ledger authoritative in the finance service. Extend the existing cashflow API with explicit delete and human-confirm endpoints, then split the current finance view into route-level pages that share typed TanStack Query hooks and focused financial components. A confirmation recalculates the suggestion on the server, refuses future, unknown, uncertain, matched, or foreign items, and creates balanced postings only through `create_transaction`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, PostgreSQL, React 18, TypeScript, React Router v6, TanStack Query v5, Tailwind CSS, pytest, Vitest, Testing Library.

---

## File structure

| File | Responsibility |
|---|---|
| `backend/app/finance/schemas.py` | Query and confirmation response schemas. |
| `backend/app/finance/service.py` | Date-bounded reporting, scheduler deletion and server-side confirmation. |
| `backend/app/finance/router.py` | HTTP parameters and cashflow mutation endpoints. |
| `backend/tests/test_finance/test_cashflow.py` | Cashflow service and API integration coverage. |
| `frontend/src/api/finance.ts` | Finance query types, mutation hooks, money/date helpers and cache invalidation. |
| `frontend/src/api/finance.test.ts` | Pure helper coverage for amounts and confirmation eligibility. |
| `frontend/src/components/finance/` | Reusable period picker, account/transaction view, category tree, cashflow cards and scheduler form. |
| `frontend/src/pages/Finances.tsx` | Compact overview only. |
| `frontend/src/pages/FinanceTransactions.tsx` | Account-filtered history. |
| `frontend/src/pages/FinanceCashflow.tsx` | Settings, daily forecast, scheduler and confirmation dialog. |
| `frontend/src/pages/FinanceBudgets.tsx` | Selected-month actual category spending. |
| `frontend/src/pages/FinanceReports.tsx` | Selected-month income, expense, balance and category report. |
| `frontend/src/App.tsx` | Real finance subroutes. |
| `frontend/src/components/navigation.ts` | Real finance links rather than disabled menu entries. |
| `frontend/src/components/navigation.test.tsx` | Active, accessible real finance navigation tests. |

### Task 1: Date-bounded finance summaries

**Files:**
- Modify: `backend/app/finance/service.py:309-476`
- Modify: `backend/app/finance/router.py:212-225`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing integration tests for a selected reporting month.**

  Add transactions in August and September, then assert that both endpoint families return only August values for `?month=8&year=2026`:

  ```python
  summary = await client.get("/api/finance/summary", params={"month": 8, "year": 2026})
  categories = await client.get(
      "/api/finance/category-summary", params={"month": 8, "year": 2026}
  )

  assert summary.json()["income_total_pln"] == 10_000
  assert summary.json()["expense_total_pln"] == 2_500
  assert categories.json()["month"] == 8
  assert [entry["total_pln"] for entry in categories.json()["categories"]] == [2_500]
  ```

- [ ] **Step 2: Run the focused test to verify it fails.**

  Run: `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -k selected_reporting_month -v`

  Expected: FAIL because `/summary` and `/category-summary` ignore month/year and include later transactions.

- [ ] **Step 3: Add explicit period handling in the service and router.**

  Introduce one internal helper and optional endpoint query parameters:

  ```python
  def _month_bounds(month: int | None, year: int | None) -> tuple[int, int, date, date]:
      now = datetime.now(UTC)
      selected_month = month if month is not None else now.month
      selected_year = year if year is not None else now.year
      month_start = date(selected_year, selected_month, 1)
      month_end = date(
          selected_year + (selected_month == 12),
          (selected_month % 12) + 1,
          1,
      )
      return selected_month, selected_year, month_start, month_end

  async def get_financial_summary(
      db: AsyncSession, user_id: uuid.UUID, month: int | None = None, year: int | None = None
  ) -> FinancialSummary:
      current_month, current_year, month_start, month_end = _month_bounds(month, year)
      # Keep account balances current, but add both date bounds to income/expense queries.
      # Return current_month/current_year in the response.

  async def get_category_summary(
      db: AsyncSession, user_id: uuid.UUID, month: int | None = None, year: int | None = None
  ) -> CategorySummaryResponse:
      current_month, current_year, month_start, month_end = _month_bounds(month, year)
      # Add FinancialTransaction.date < month_end to the existing category query.
  ```

  In the router, inject validated parameters and forward them to both services:

  ```python
  month: Annotated[int | None, Query(ge=1, le=12)] = None,
  year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
  ```

- [ ] **Step 4: Run the focused test to verify it passes.**

  Run the Step 2 command.

  Expected: PASS; selected-period summary and category totals exclude September data.

- [ ] **Step 5: Commit the reporting slice.**

  ```bash
  git add backend/app/finance/service.py backend/app/finance/router.py backend/tests/test_finance/test_cashflow.py
  git commit -m "feat: dodaj okres raportów finansowych"
  ```

### Task 2: Safe scheduler delete and confirmation

**Files:**
- Modify: `backend/app/finance/schemas.py:152-239`
- Modify: `backend/app/finance/service.py:546-767`
- Modify: `backend/app/finance/router.py:228-295`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing service tests for deletion and confirmation.**

  Add tests that create a due expense item for a budget account and category. Confirm it with an injected date, then assert one balanced transaction with source `scheduled_confirmation`, and reject a second confirmation. Also cover a foreign item, future due date, `overdue_uncertain`, and `amount_unknown`:

  ```python
  transaction = await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 10))

  assert transaction.type == "expense"
  assert transaction.source == "scheduled_confirmation"
  assert sum(
      posting.base_amount_pln if posting.direction == "debit" else -posting.base_amount_pln
      for posting in transaction.postings
  ) == 0
  with pytest.raises(ValueError, match="already matched"):
      await confirm_scheduled_item(db_session, user_id, item.id, today=date(2026, 8, 10))
  assert await delete_scheduled_item(db_session, other_user_id, item.id) is False
  ```

- [ ] **Step 2: Run focused tests to verify they fail.**

  Run: `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -k "confirm_scheduled or delete_scheduled" -v`

  Expected: FAIL because the service functions and endpoints do not exist.

- [ ] **Step 3: Add minimal schemas and service functions.**

  Add a response model with the generated transaction and make confirmation accept no client-controlled account, category, amount, description, or date:

  ```python
  class ScheduledFinanceConfirmationResponse(BaseModel):
      transaction: TransactionResponse

  async def delete_scheduled_item(
      db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID
  ) -> bool:
      result = await db.execute(
          select(ScheduledFinanceItem).where(
              ScheduledFinanceItem.id == item_id,
              ScheduledFinanceItem.user_id == user_id,
          )
      )
      item = result.scalar_one_or_none()
      if item is None:
          return False
      await db.delete(item)
      await db.flush()
      return True
  ```

  Implement `confirm_scheduled_item(db, user_id, item_id, *, today=None)` as follows:

  1. Load only the caller's active item with `with_for_update()`; return `None` when absent.
  2. Call `get_cashflow_forecast(db, user_id, today=effective_today)`, then find the suggestion by `scheduled_item_id` and due occurrence where `due_date <= effective_today`.
  3. Raise `ValueError` for missing/future, `matched_actual`, `overdue_uncertain`, `amount_unknown`, or a `None` amount; accept only `due` and `overdue`.
  4. Build `TransactionCreate` with `transaction_date=effective_today`, `description=f"{item.name} — {suggestion.due_date.isoformat()}"`, `source="scheduled_confirmation"`, and two PLN postings. Income uses account `credit` / category `debit`; expense uses account `debit` / category `credit`. Both posting amounts equal the server-resolved suggestion amount.
  5. Delegate to `create_transaction`; do not create postings directly.

- [ ] **Step 4: Expose the mutations with correct HTTP results.**

  Add routes after the existing `PATCH /cashflow/items/{item_id}` route:

  ```python
  @router.delete("/cashflow/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_scheduled_finance_item(...):
      if not await delete_scheduled_item(db, current_user.id, item_id):
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled item not found")

  @router.post(
      "/cashflow/items/{item_id}/confirm",
      response_model=ScheduledFinanceConfirmationResponse,
  )
  async def confirm_scheduled_finance_item(...):
      try:
          transaction = await confirm_scheduled_item(db, current_user.id, item_id)
      except ValueError as error:
          raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))
      if transaction is None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled item not found")
      return ScheduledFinanceConfirmationResponse(transaction=transaction)
  ```

  Add the imports for `delete_scheduled_item`, `confirm_scheduled_item`, and the response schema.

- [ ] **Step 5: Add an HTTP integration assertion.**

  In the existing overridden-client test, delete a created item and assert `204`; create a currently due item, `POST` its `/confirm` endpoint, assert `200`, then assert the second POST is `422` and `GET /forecast` returns `matched_actual`.

- [ ] **Step 6: Run focused backend tests to verify they pass.**

  Run the Step 2 command and then:

  `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -v`

  Expected: PASS; no confirmation can create an unbalanced or duplicate transaction.

- [ ] **Step 7: Commit the scheduler mutation slice.**

  ```bash
  git add backend/app/finance/schemas.py backend/app/finance/service.py backend/app/finance/router.py backend/tests/test_finance/test_cashflow.py
  git commit -m "feat: potwierdzaj pozycje harmonogramu"
  ```

### Task 3: Typed frontend finance API

**Files:**
- Modify: `frontend/src/api/finance.ts:1-323`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write failing unit tests for frontend-safe helpers.**

  Add tests for converting a user-entered PLN amount to integer grosze and deciding whether a suggestion can be confirmed only on/after its due date:

  ```ts
  expect(parsePlnToGrosze("1 234,50")).toBe(123450);
  expect(parsePlnToGrosze("0")).toBeNull();
  expect(canConfirmSuggestion({ status: "due", amount_pln: 2500, due_date: "2026-08-10" }, "2026-08-10")).toBe(true);
  expect(canConfirmSuggestion({ status: "due", amount_pln: 2500, due_date: "2026-08-11" }, "2026-08-10")).toBe(false);
  expect(canConfirmSuggestion({ status: "overdue_uncertain", amount_pln: 2500, due_date: "2026-08-05" }, "2026-08-10")).toBe(false);
  ```

- [ ] **Step 2: Run the frontend test to verify it fails.**

  Run: `npm run test -- --run src/api/finance.test.ts`

  Expected: FAIL because the helpers are not exported.

- [ ] **Step 3: Add API types, helpers, queries, and mutations.**

  Add `FinanceSettings`, `FinanceSettingsUpdate`, `ScheduledFinanceItemInput`, and `ScheduledFinanceConfirmation` types. Export `parsePlnToGrosze` and `canConfirmSuggestion`; the former normalizes spaces and `,` to `.`, rejects non-finite/non-positive values and fractions beyond two decimal places, and returns `Math.round(value * 100)`.

  Add hooks for `useCashflowSettings`, `useUpdateCashflowSettings`, `useCreateScheduledFinanceItem`, `useUpdateScheduledFinanceItem`, `useDeleteScheduledFinanceItem`, and `useConfirmScheduledFinanceItem`. The scheduler mutation payload must use `fixed_amount_pln: null` for `last_actual`. The confirmation hook posts an empty body to `/finance/cashflow/items/${id}/confirm`.

  Centralize invalidation after cashflow mutations:

  ```ts
  const invalidateCashflow = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["finance", "cashflow"] }),
      queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["finance", "transactions"] }),
      queryClient.invalidateQueries({ queryKey: ["finance", "summary"] }),
      queryClient.invalidateQueries({ queryKey: ["finance", "category-summary"] }),
    ]);
  ```

  Change `useFinancialSummary` and `useCategorySummary` to accept `{ month, year }` and send those parameters. Preserve no-argument current-month behavior.

- [ ] **Step 4: Run the focused frontend test to verify it passes.**

  Run the Step 2 command.

  Expected: PASS.

- [ ] **Step 5: Commit the typed frontend API.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts
  git commit -m "feat: dodaj mutacje cashflow we frontendzie"
  ```

### Task 4: Finance routing and read-only subpages

**Files:**
- Create: `frontend/src/components/finance/MonthPicker.tsx`
- Create: `frontend/src/components/finance/CategorySpendTree.tsx`
- Create: `frontend/src/components/finance/AccountTransactions.tsx`
- Create: `frontend/src/pages/FinanceTransactions.tsx`
- Create: `frontend/src/pages/FinanceBudgets.tsx`
- Create: `frontend/src/pages/FinanceReports.tsx`
- Modify: `frontend/src/pages/Finances.tsx:1-359`
- Modify: `frontend/src/App.tsx:1-48`
- Modify: `frontend/src/components/navigation.ts:57-67`
- Test: `frontend/src/components/navigation.test.tsx`

- [ ] **Step 1: Write failing navigation tests for real finance views.**

  Replace the expectation that Budżet is disabled with assertions for active link behavior:

  ```tsx
  expect(screen.getByRole("link", { name: "Płynność" })).toHaveAttribute(
    "href",
    "/finances/cashflow",
  );
  expect(screen.getByRole("link", { name: "Budżet" })).toHaveAttribute(
    "href",
    "/finances/budgets",
  );
  expect(isMenuItemActive(budgetItem, "/finances/budgets")).toBe(true);
  ```

- [ ] **Step 2: Run the failing navigation test.**

  Run: `npm run test -- --run src/components/navigation.test.tsx`

  Expected: FAIL because these menu entries are disabled or absent.

- [ ] **Step 3: Implement route components and shared read-only components.**

  - `MonthPicker` owns month/year selection with previous/next controls and returns `{ month, year }`; block next-month navigation after the current month.
  - `CategorySpendTree` renders `buildCategoryTree(summary)` with group totals, children, selected month label, loading and empty states.
  - `AccountTransactions` takes `accounts`, keeps the selected account ID locally, and uses `useAccountTransactions`; it clearly labels informational accounts as excluded from analysis.
  - `FinanceTransactions` renders `AccountTransactions` with `useAccounts()`.
  - `FinanceBudgets` renders `MonthPicker` and `CategorySpendTree` using `useCategorySummary(period)`, titled “Wydatki według kategorii”; do not show invented budget limits.
  - `FinanceReports` renders `MonthPicker`, `useFinancialSummary(period)`, and `useCategorySummary(period)` with income, expense and net cards plus `CategorySpendTree`.
  - Reduce `Finances` to the current monthly summary, budget/informational account cards, and a compact cashflow summary that links to `/finances/cashflow`; remove the in-page scheduled-item list and account transaction detail.
  - Register all four routes in `App.tsx` and add `Transakcje`, `Płynność`, `Budżet`, and `Raporty` links in the finance navigation context.

- [ ] **Step 4: Run navigation and type tests.**

  Run: `npm run test -- --run src/components/navigation.test.tsx && npm run typecheck`

  Expected: PASS; nested finance URLs keep the finance context and all menu links resolve to registered routes.

- [ ] **Step 5: Commit the finance-page routing slice.**

  ```bash
  git add frontend/src/App.tsx frontend/src/components/navigation.ts frontend/src/components/navigation.test.tsx frontend/src/components/finance frontend/src/pages/Finances.tsx frontend/src/pages/FinanceTransactions.tsx frontend/src/pages/FinanceBudgets.tsx frontend/src/pages/FinanceReports.tsx
  git commit -m "feat: rozdziel widoki finansowe"
  ```

### Task 5: Cashflow management page

**Files:**
- Create: `frontend/src/components/finance/CashflowSettingsForm.tsx`
- Create: `frontend/src/components/finance/ScheduledItemForm.tsx`
- Create: `frontend/src/components/finance/ScheduledItemsList.tsx`
- Create: `frontend/src/components/finance/CashflowForecast.tsx`
- Create: `frontend/src/components/finance/ConfirmScheduledItemDialog.tsx`
- Create: `frontend/src/pages/FinanceCashflow.tsx`
- Test: `frontend/src/pages/FinanceCashflow.test.tsx`

- [ ] **Step 1: Write failing component tests.**

  Mock the finance hooks and assert each user-control boundary:

  ```tsx
  expect(screen.getByLabelText("Konto wypłaty")).toHaveTextContent("Konto główne");
  expect(screen.getByRole("option", { name: "Kredyt" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Metoda kwoty"), "last_actual");
  expect(screen.queryByLabelText("Kwota (PLN)")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Potwierdź wydatek" })).toBeDisabled();
  ```

  Add a positive case where a due-today item opens the dialog and pressing the final confirmation calls `useConfirmScheduledFinanceItem().mutate` with only its item ID.

- [ ] **Step 2: Run the component test to verify it fails.**

  Run: `npm run test -- --run src/pages/FinanceCashflow.test.tsx`

  Expected: FAIL because the page and controls do not exist.

- [ ] **Step 3: Implement settings and scheduler forms.**

  `CashflowSettingsForm` loads settings/accounts, initializes only after the query resolves, filters to active budget accounts, and PATCHes `payday_day`, `payday_account_id`, `forecast_horizon_days`, and `overdue_grace_days`. It shows API validation errors from `AxiosError<{ detail: string }>` next to the submit action.

  `ScheduledItemForm` supports create and edit states. It filters active budget accounts, filters categories by selected `income`/`expense` type, locks currency to the selected account currency, and converts a fixed PLN amount through `parsePlnToGrosze`. For `last_actual`, omit a visible amount and send `fixed_amount_pln: null`. Submit and cancel controls disable while a mutation is pending.

- [ ] **Step 4: Implement forecast, item list, and confirmation dialog.**

  `CashflowForecast` displays the four existing forecast measures and an accessible 30/90-day textual daily-balance list; it must not imply a mutation. `ScheduledItemsList` displays cadence, amount method, active state and forecast status; its edit, deactivate/reactivate, and delete buttons use their corresponding mutation hooks. Delete requires a browser `window.confirm` containing the item name.

  `ConfirmScheduledItemDialog` accepts only a suggestion and its scheduled item. It uses `canConfirmSuggestion(suggestion, localIsoDate)` to hide the primary action before the due date or for unknown/uncertain/matched statuses. It displays the server-derived name, due date, PLN amount and scheduled type, then calls the confirmation mutation with `scheduled_item_id` only after a second explicit button click. On success it closes; on error it keeps the dialog open and shows the server detail.

  `FinanceCashflow` composes these components from `useAccounts`, `useCategories`, `useCashflowSettings`, `useScheduledFinanceItems`, and `useCashflowForecast`, handling each query's loading and error state independently.

- [ ] **Step 5: Run component, lint, typecheck, and build verification.**

  Run: `npm run test -- --run src/pages/FinanceCashflow.test.tsx && npm run lint && npm run typecheck && npm run build`

  Expected: PASS; no action creates a transaction until the dialog's final human confirmation.

- [ ] **Step 6: Commit the cashflow page.**

  ```bash
  git add frontend/src/components/finance frontend/src/pages/FinanceCashflow.tsx frontend/src/pages/FinanceCashflow.test.tsx
  git commit -m "feat: dodaj zarządzanie płynnością"
  ```

### Task 6: Full verification, documentation, and deployment readiness

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run backend quality gates.**

  Run: `make VENV=/opt/finanse/backend/.venv/bin lint && make VENV=/opt/finanse/backend/.venv/bin typecheck && make VENV=/opt/finanse/backend/.venv/bin test`

  Expected: PASS. If integration tests are skipped because the isolated database is unavailable, start only the documented isolated test database and run `make VENV=/opt/finanse/backend/.venv/bin test-integration`; never point tests at production.

- [ ] **Step 2: Run frontend quality gates.**

  Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test && npm --prefix frontend run build`

  Expected: PASS.

- [ ] **Step 3: Run a browser smoke test.**

  Use the local Vite app with mocked authenticated API data. Verify each finance link opens its matching URL, the cashflow page shows settings and a due item, and the confirmation dialog requires the final action before issuing its POST request.

- [ ] **Step 4: Update session documentation from actual command output.**

  Record only verified results in `CHANGELOG.md`, mark this finance-slice task complete in `TASKS.md`, and prepend `JOURNAL.md` with scope, API safety decisions, tests, known limitations, and the next session's work. Mention that budget limits remain out of scope.

- [ ] **Step 5: Commit verification and docs.**

  ```bash
  git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md
  git commit -m "docs: opisz zarządzanie płynnością"
  ```

- [ ] **Step 6: Request explicit deployment approval.**

  Present the verification evidence and request approval before running `/deploy`; deploy changes production containers and is not implicit in implementation.
