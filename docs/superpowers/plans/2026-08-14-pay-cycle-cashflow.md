# Pay-Cycle Cashflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a user-configured monthly pay cycle with scheduled income and expenses, a 30-day PLN cashflow forecast, and non-mutating overdue suggestions.

**Architecture:** Store per-user pay-cycle settings and recurring monthly schedule definitions in the finance domain. The forecast service reads budget-account balances, recognized actual transactions, and active schedules to produce an in-memory day-by-day projection; it never creates `FinancialTransaction` or `Posting` rows. Existing actuals are recognized by matching the schedule's owned budget account, category, amount, type, and a three-day due-date window, preventing double counting.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2.x async, Alembic, PostgreSQL 16, pytest, React 18, TanStack Query, TypeScript, Vitest.

---

## File Structure

- Create: `backend/migrations/versions/8a6d0c1e2b3f_pay_cycle_cashflow.py` - creates finance settings and recurring schedule tables with ownership, amount, and domain constraints.
- Modify: `backend/app/finance/models.py` - maps `FinanceSettings` and `ScheduledFinanceItem`.
- Modify: `backend/app/finance/schemas.py` - validates settings, schedule write requests, schedule list rows, forecast rows, and suggestions.
- Modify: `backend/app/finance/service.py` - validates owned budget account/category links, manages settings/schedules, recognizes actuals, and computes the read-only forecast.
- Modify: `backend/app/finance/router.py` - exposes authenticated settings, schedule, and forecast endpoints.
- Create: `backend/tests/test_finance/test_cashflow.py` - integration/API coverage for cashflow rules and the no-ledger-mutation guarantee.
- Modify: `frontend/src/api/finance.ts` - adds typed cashflow queries.
- Modify: `frontend/src/pages/Finances.tsx` - adds a compact forecast card and scheduled-item list without ledger write controls.
- Modify: `frontend/src/api/finance.test.ts` - covers cashflow presentation helpers if a pure helper is added.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` - records implementation and fresh verification.

### Task 1: Database and Domain Contracts

**Files:**
- Create: `backend/migrations/versions/8a6d0c1e2b3f_pay_cycle_cashflow.py`
- Modify: `backend/app/finance/models.py`
- Modify: `backend/app/finance/schemas.py`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing schema/model tests**

```python
def test_schedule_requires_a_fixed_amount_for_fixed_method() -> None:
    with pytest.raises(ValidationError):
        ScheduledFinanceItemCreate(
            name="Czynsz", type="expense", account_id=uuid.uuid4(),
            category_id=uuid.uuid4(), currency="PLN", due_day=5,
            amount_method="fixed", fixed_amount_pln=None,
        )
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py::test_schedule_requires_a_fixed_amount_for_fixed_method -v`

Expected: FAIL because the cashflow schema does not exist.

- [ ] **Step 3: Add the minimal contracts and migration**

Add `FinanceSettings` with unique `user_id`, `payday_day` (1-28), nullable owned `payday_account_id`, `forecast_horizon_days` (default 30), and `overdue_grace_days` (default 3). Add `ScheduledFinanceItem` with user ownership, required account/category foreign keys, `income|expense` type, `monthly` cadence, `due_day` (1-28), `fixed|last_actual` amount method, nullable positive `fixed_amount_pln`, `currency`, `is_active`, and timestamps. Encode SQL `CHECK` constraints for enum-like fields, days, and fixed amount semantics; add indexes on user and active schedule lookups.

```python
class ScheduledFinanceItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["income", "expense"]
    account_id: uuid.UUID
    category_id: uuid.UUID
    currency: str = Field(min_length=3, max_length=3)
    due_day: int = Field(ge=1, le=28)
    amount_method: Literal["fixed", "last_actual"]
    fixed_amount_pln: int | None = Field(default=None, gt=0)
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py::test_schedule_requires_a_fixed_amount_for_fixed_method -v`

Expected: PASS.

### Task 2: TDD Settings and Schedule Ownership Rules

**Files:**
- Modify: `backend/app/finance/service.py`
- Modify: `backend/app/finance/router.py`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing integration tests for ownership and budget validation**

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_schedule_rejects_offbudget_account(db_session):
    account = await create_account(
        db_session, user_id, AccountCreate(name="Kredyt", type="credit", is_budget_account=False)
    )
    category = await create_category(
        db_session, user_id, CategoryCreate(name="Czynsz", type="expense")
    )
    with pytest.raises(ValueError, match="budget account"):
        await create_scheduled_item(db_session, user_id, valid_schedule(account.id, category.id))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -k "schedule_rejects_offbudget or schedule_rejects_wrong_category_type" -v`

Expected: FAIL because schedule service functions are absent.

- [ ] **Step 3: Implement minimal settings and schedule services/endpoints**

Implement `get_or_create_finance_settings`, `update_finance_settings`, `create_scheduled_item`, `get_scheduled_items`, and `update_scheduled_item`. Verify the account and category belong to the caller; require an active budget account, matching account/item currency, and a category whose `type` equals the item type. Expose:

```text
GET/PATCH /api/finance/cashflow/settings
GET/POST /api/finance/cashflow/items
PATCH /api/finance/cashflow/items/{item_id}
```

Return HTTP 422 for invalid cross-domain links and 404 for an item not owned by the caller. Do not expose a delete endpoint in this first slice; deactivation preserves forecast history and is sufficient.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -k "schedule_rejects_offbudget or schedule_rejects_wrong_category_type or settings" -v`

Expected: PASS.

### Task 3: TDD Read-Only Forecast and Suggestions

**Files:**
- Modify: `backend/app/finance/service.py`
- Modify: `backend/app/finance/router.py`
- Modify: `backend/app/finance/schemas.py`
- Test: `backend/tests/test_finance/test_cashflow.py`

- [ ] **Step 1: Write failing forecast tests**

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_forecast_excludes_offbudget_balance_and_applies_fixed_expense(db_session):
    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))
    assert forecast.opening_balance_pln == 10_000
    assert forecast.lowest_balance_pln == 6_000

@pytest.mark.integration
@pytest.mark.asyncio
async def test_overdue_item_is_uncertain_after_three_days_and_does_not_change_projection(db_session):
    forecast = await get_cashflow_forecast(db_session, user_id, today=date(2026, 8, 14))
    assert forecast.suggestions[0].status == "overdue_uncertain"
    assert forecast.suggestions[0].included_in_forecast is False
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -k "forecast_excludes or overdue_item" -v`

Expected: FAIL because `get_cashflow_forecast` is absent.

- [ ] **Step 3: Implement the minimal pure read flow**

`get_cashflow_forecast(db, user_id, today=None)` defaults to the local date. It sums only active budget-account balances in PLN. For each active monthly item, generate due dates from the current month through the configured horizon, resolve `fixed_amount_pln` or the latest owned matching actual's category-side PLN amount, and look for an actual transaction with matching type/account/category/amount dated from three days before through three days after that due date.

For an unmatched item whose due date is more than `overdue_grace_days` behind `today`, return an `overdue_uncertain` suggestion and exclude it. For a due item within the grace window, apply it on the first projection day and return `due` or `overdue`; for future occurrences, apply it on their date. A recognized actual is returned as `matched_actual` and is not projected. Items with no usable last actual are returned as `amount_unknown` and excluded. Income adds and expense subtracts. Return the current pay-cycle bounds (`last_payday`, `next_payday`), opening balance, lowest projected balance, remaining days, safe daily limit, day rows, and suggestions.

Use only `SELECT` and in-memory projection. This endpoint must not call `create_transaction`, add a `Posting`, or mutate item/settings rows.

- [ ] **Step 4: Add regression tests for amount source, matched actual, and no ledger mutation**

```python
assert suggestion.amount_pln == 12_345  # last_actual uses latest matching historical actual
assert matched_suggestion.included_in_forecast is False
assert await count_rows(db_session, FinancialTransaction) == transaction_count_before
assert await count_rows(db_session, Posting) == posting_count_before
```

- [ ] **Step 5: Expose and verify the forecast endpoint**

Add `GET /api/finance/cashflow/forecast` and return `CashflowForecastResponse`. Test an authenticated request, including that an off-budget account is absent from `opening_balance_pln` and that suggestions have no transaction-creation action.

Run: `cd backend && ../backend/.venv/bin/pytest tests/test_finance/test_cashflow.py -v`

Expected: PASS.

### Task 4: Basic Finances Surface

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Modify: `frontend/src/pages/Finances.tsx`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write a failing UI-helper test if a helper is needed**

```typescript
it("labels uncertain overdue suggestions without an action", () => {
  expect(cashflowStatusLabel("overdue_uncertain")).toBe("Po terminie - kwota niepewna");
});
```

- [ ] **Step 2: Run it to verify RED**

Run: `cd frontend && npm run test -- finance.test.ts`

Expected: FAIL because the status helper is absent.

- [ ] **Step 3: Add typed read queries and compact presentation**

Add `CashflowForecast` and `ScheduledFinanceItem` TypeScript interfaces plus `useCashflowForecast` and `useScheduledFinanceItems`. At the top of `Finances`, render a responsive forecast card with next payday, projected low, daily safe limit, and the explicit note that this is a forecast only. Render the schedule list with type, due day, amount method/value, and status. Mark `overdue_uncertain` clearly and provide no button that creates a ledger transaction.

- [ ] **Step 4: Run frontend test and type verification**

Run: `cd frontend && npm run test -- finance.test.ts && npm run typecheck`

Expected: PASS.

### Task 5: Migration, Quality Gate, Documentation, and Commit

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`
- Modify: `docs/superpowers/specs/2026-08-14-pay-cycle-cashflow-design.md`
- Create: `docs/superpowers/plans/2026-08-14-pay-cycle-cashflow.md`

- [ ] **Step 1: Validate the Alembic migration in the isolated test database**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test ../backend/.venv/bin/alembic upgrade head`

Expected: migration reaches the new revision without using production credentials.

- [ ] **Step 2: Run all required checks**

Run: `make VENV=/opt/finanse/backend/.venv/bin lint`

Run: `make VENV=/opt/finanse/backend/.venv/bin typecheck`

Run: `make VENV=/opt/finanse/backend/.venv/bin test`

Run: `git diff --check`

Expected: all commands exit 0; report known pre-existing warnings separately if emitted.

- [ ] **Step 3: Update session documentation**

Add an Unreleased changelog entry, mark the cashflow task complete in `TASKS.md`, and prepend a journal entry describing the no-ledger-mutation boundary, the three-day uncertainty rule, test results, and that neither migration nor deployment was performed on production.

- [ ] **Step 4: Inspect and commit exactly the feature files**

Run: `git status --short && git diff --check && git diff --cached --check`

Stage only the specification, plan, migration, finance/backend/frontend tests and code, and session documentation. Commit with:

```bash
git commit -m "feat: dodaj prognozę płynności cyklu wypłaty"
```

Expected: one clean commit; no deployment command is run.
