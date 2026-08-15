# Monthly Budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add recurring monthly budget limits per expense category with spent/remaining status and a usable `/finances/budgets` page.

**Architecture:** New `category_budgets` table with a unique per-user category limit. Backend exposes CRUD plus a `budget-status` read that rolls up descendant spending for group budgets and returns zero-spend budgets. Frontend composes budget CRUD hooks with a status query and renders progress against the existing category hierarchy.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async, PostgreSQL, Alembic, React 18, TypeScript, TanStack Query v5, Tailwind, pytest, Vitest.

---

## File structure

| File | Responsibility |
|---|---|
| `backend/app/finance/models.py` | `CategoryBudget` model. |
| `backend/migrations/versions/<new>_category_budgets.py` | Migration for the table + unique constraint. |
| `backend/app/finance/schemas.py` | Budget create/update/response and status schemas. |
| `backend/app/finance/service.py` | Budget CRUD, ownership/expense validation, spending roll-up and status. |
| `backend/app/finance/router.py` | Budget HTTP endpoints. |
| `backend/tests/test_finance/test_budgets.py` | Backend coverage. |
| `frontend/src/api/finance.ts` | Budget types, CRUD and status hooks, cache invalidation. |
| `frontend/src/api/finance.test.ts` | Helper coverage for budgets. |
| `frontend/src/pages/FinanceBudgets.tsx` | Budget list, add/edit/delete and unbudgeted section. |
| `frontend/src/pages/FinanceBudgets.test.tsx` | Page component tests. |

### Task 1: Budget model and migration

**Files:**
- Modify: `backend/app/finance/models.py`
- Create: `backend/migrations/versions/<new>_category_budgets.py`
- Test: `backend/tests/test_finance/test_budgets.py`

- [ ] **Step 1: Add the model.**

  Append to `backend/app/finance/models.py`:

  ```python
  class CategoryBudget(Base):
      __tablename__ = "category_budgets"

      user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
      category_id: Mapped[uuid.UUID] = mapped_column(
          UUID(as_uuid=True),
          ForeignKey("categories.id", ondelete="RESTRICT"),
          nullable=False,
          index=True,
      )
      amount_pln: Mapped[int] = mapped_column(BigInteger, nullable=False)

      __table_args__ = (
          CheckConstraint("amount_pln > 0", name="ck_category_budget_amount"),
          UniqueConstraint("user_id", "category_id", name="uq_category_budget_user_category"),
      )

      category: Mapped["Category"] = relationship("Category")
  ```

- [ ] **Step 2: Generate the migration.**

  Run autogenerate against the isolated test database, then review it includes `category_budgets`, the `amount_pln > 0` check, the unique constraint, and `RESTRICT` FK:

  ```bash
  cd /opt/finanse/backend && \
  DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test \
  /opt/finanse/backend/.venv/bin/alembic revision --autogenerate -m "category budgets"
  ```

  If autogenerate is unavailable, hand-write the migration following the `8a6d0c1e2b3f` pattern (columns: `user_id`, `category_id`, `amount_pln`, plus `id`, `created_at`, `updated_at`; `ck_category_budget_amount`; `uq_category_budget_user_category`; FK to `categories.id` RESTRICT; index on `user_id` and `category_id`).

- [ ] **Step 3: Write a migration smoke test.**

  In `backend/tests/test_finance/test_budgets.py`, add an integration test that applies migrations implicitly (the fixture already does) and asserts the table exists with a valid insert + unique-violation behavior:

  ```python
  import uuid
  import pytest
  from sqlalchemy import select
  from app.finance.models import CategoryBudget
  from app.finance.service import create_category, create_budget
  from app.finance.schemas import CategoryCreate, CategoryBudgetCreate

  @pytest.mark.integration
  @pytest.mark.asyncio
  async def test_budget_unique_per_user_and_category(db_session) -> None:
      user_id = uuid.uuid4()
      category = await create_category(
          db_session, user_id, CategoryCreate(name="Jedzenie", type="expense")
      )
      await create_budget(db_session, user_id, CategoryBudgetCreate(category_id=category.id, amount_pln=1000))
      with pytest.raises(Exception):
          await create_budget(db_session, user_id, CategoryBudgetCreate(category_id=category.id, amount_pln=2000))
  ```

- [ ] **Step 4: Run the smoke test.**

  Run: `TEST_DATABASE_URL=postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_budgets.py -k unique -v`

  Expected: PASS (the fixture applies migrations to the isolated database).

- [ ] **Step 5: Commit.**

  ```bash
  git add backend/app/finance/models.py backend/migrations/versions/<new>_category_budgets.py backend/tests/test_finance/test_budgets.py
  git commit -m "feat: dodaj model budżetu kategorii"
  ```

### Task 2: Budget schemas and service

**Files:**
- Modify: `backend/app/finance/schemas.py`
- Modify: `backend/app/finance/service.py`
- Test: `backend/tests/test_finance/test_budgets.py`

- [ ] **Step 1: Write failing service tests.**

  Cover: create/update/delete only own budget; reject non-expense category; reject foreign category; reject non-positive amount; `get_budget_status` returns a zero-spend budget and rolls up a group's child spending. Use the existing `create_expense`/`create_income` helpers or inline `create_transaction` with a budget account and expense category:

  ```python
  async def test_budget_status_returns_zero_spend_and_rolls_up_group(db_session) -> None:
      user_id = uuid.uuid4()
      account = await create_account(db_session, user_id, AccountCreate(name="Konto", type="checking"))
      group = await create_category(db_session, user_id, CategoryCreate(name="Dom", type="expense"))
      child = await create_category(db_session, user_id, CategoryCreate(name="Czynsz", type="expense", parent_id=group.id))
      await create_budget(db_session, user_id, CategoryBudgetCreate(category_id=child.id, amount_pln=4000))
      await create_budget(db_session, user_id, CategoryBudgetCreate(category_id=group.id, amount_pln=6000))
      # create 2500 expense in child for this month
      await create_transaction(db_session, user_id, TransactionCreate(
          description="Czynsz", type="expense",
          postings=[
              PostingCreate(account_id=account.id, source_amount=2500, base_amount_pln=2500, direction="debit"),
              PostingCreate(category_id=child.id, source_amount=2500, base_amount_pln=2500, direction="credit"),
          ],
      ))
      status = await get_budget_status(db_session, user_id)
      by_id = {item.category_id: item for item in status.items}
      assert by_id[child.id].spent_pln == 2500
      assert by_id[group.id].spent_pln == 2500  # rolled up from child
      assert by_id[child.id].remaining_pln == 1500
  ```

  Also a zero-spend category with a budget must appear with `spent_pln == 0`.

- [ ] **Step 2: Run to verify they fail.**

  Run: `TEST_DATABASE_URL=... /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_budgets.py -k budget -v`

  Expected: FAIL (missing schemas/functions).

- [ ] **Step 3: Add schemas.**

  In `backend/app/finance/schemas.py`:

  ```python
  class CategoryBudgetCreate(BaseModel):
      category_id: uuid.UUID
      amount_pln: int = Field(gt=0)

  class CategoryBudgetUpdate(BaseModel):
      amount_pln: int = Field(gt=0)

  class CategoryBudgetResponse(BaseModel):
      id: uuid.UUID
      category_id: uuid.UUID
      amount_pln: int
      model_config = {"from_attributes": True}

  class BudgetStatusItem(BaseModel):
      category_id: uuid.UUID
      name: str
      parent_id: uuid.UUID | None
      budget_amount_pln: int
      spent_pln: int
      remaining_pln: int

  class BudgetStatusResponse(BaseModel):
      month: int
      year: int
      items: list[BudgetStatusItem]
  ```

- [ ] **Step 4: Implement service functions.**

  Add `CategoryBudget` to the model import block, and the schema classes to the schema import block. Then:

  ```python
  async def _require_expense_category(db, user_id, category_id) -> Category:
      result = await db.execute(
          select(Category).where(Category.id == category_id, Category.user_id == user_id)
      )
      category = result.scalar_one_or_none()
      if category is None:
          raise ValueError("Budget category not found")
      if category.type != "expense":
          raise ValueError("Budget category must be an expense category")
      return category

  async def create_budget(db, user_id, data: CategoryBudgetCreate) -> CategoryBudget:
      await _require_expense_category(db, user_id, data.category_id)
      budget = CategoryBudget(user_id=user_id, **data.model_dump())
      db.add(budget)
      await db.flush()
      return budget

  async def get_budgets(db, user_id) -> list[CategoryBudget]:
      result = await db.execute(
          select(CategoryBudget).where(CategoryBudget.user_id == user_id)
      )
      return list(result.scalars().all())

  async def update_budget(db, user_id, budget_id, data: CategoryBudgetUpdate) -> CategoryBudget | None:
      result = await db.execute(
          select(CategoryBudget).where(
              CategoryBudget.id == budget_id, CategoryBudget.user_id == user_id
          )
      )
      budget = result.scalar_one_or_none()
      if budget is None:
          return None
      budget.amount_pln = data.amount_pln
      await db.flush()
      return budget

  async def delete_budget(db, user_id, budget_id) -> bool:
      result = await db.execute(
          select(CategoryBudget).where(
              CategoryBudget.id == budget_id, CategoryBudget.user_id == user_id
          )
      )
      budget = result.scalar_one_or_none()
      if budget is None:
          return False
      await db.delete(budget)
      await db.flush()
      return True
  ```

  For `get_budget_status`, reuse the month helpers and the category-spend aggregation:

  ```python
  async def get_budget_status(
      db, user_id, month: int | None = None, year: int | None = None
  ) -> BudgetStatusResponse:
      selected_month, selected_year, month_start, month_end = _month_bounds(month, year)
      budgets = await get_budgets(db, user_id)
      if not budgets:
          return BudgetStatusResponse(month=selected_month, year=selected_year, items=[])
      categories = await get_categories(db, user_id)
      children_by_parent: dict[uuid.UUID, list[Category]] = {}
      for category in categories:
          if category.parent_id is not None:
              children_by_parent.setdefault(category.parent_id, []).append(category)

      def descendants(category_id: uuid.UUID) -> set[uuid.UUID]:
          result = {category_id}
          for child in children_by_parent.get(category_id, []):
              result.update(descendants(child.id))
          return result

      # aggregate expense spend per category for the month (same shape as get_category_summary)
      account_posting = aliased(Posting)
      spend_result = await db.execute(
          select(Posting.category_id, func.sum(Posting.base_amount_pln))
          .join(FinancialTransaction, Posting.transaction_id == FinancialTransaction.id)
          .join(account_posting, (account_posting.transaction_id == FinancialTransaction.id)
                & account_posting.account_id.is_not(None)
                & account_posting.category_id.is_(None))
          .join(Account, Account.id == account_posting.account_id)
          .where(
              FinancialTransaction.user_id == user_id,
              FinancialTransaction.type == "expense",
              FinancialTransaction.date >= month_start,
              FinancialTransaction.date < month_end,
              Posting.account_id.is_(None),
              Posting.category_id.is_not(None),
              Account.is_budget_account.is_(True),
          )
          .group_by(Posting.category_id)
      )
      spend_by_category = {category_id: int(total) for category_id, total in spend_result.all()}
      category_by_id = {category.id: category for category in categories}
      items: list[BudgetStatusItem] = []
      for budget in budgets:
          category = category_by_id.get(budget.category_id)
          if category is None:
              continue
          scope = descendants(budget.category_id)
          spent = sum(spend_by_category.get(cid, 0) for cid in scope)
          items.append(BudgetStatusItem(
              category_id=budget.category_id,
              name=category.name,
              parent_id=category.parent_id,
              budget_amount_pln=budget.amount_pln,
              spent_pln=spent,
              remaining_pln=budget.amount_pln - spent,
          ))
      items.sort(key=lambda item: item.name)
      return BudgetStatusResponse(month=selected_month, year=selected_year, items=items)
  ```

- [ ] **Step 5: Run focused tests to verify they pass.**

  Run: `TEST_DATABASE_URL=... /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_budgets.py -v`

  Expected: PASS.

- [ ] **Step 6: Commit.**

  ```bash
  git add backend/app/finance/schemas.py backend/app/finance/service.py backend/tests/test_finance/test_budgets.py
  git commit -m "feat: dodaj serwis budżetów kategorii"
  ```

### Task 3: Budget HTTP endpoints

**Files:**
- Modify: `backend/app/finance/router.py`
- Test: `backend/tests/test_finance/test_budgets.py`

- [ ] **Step 1: Write failing API tests.**

  Using the existing ASGITransport + `app.dependency_overrides` pattern (see `test_cashflow_api_exposes_settings_items_and_forecast`), assert: `POST /finance/budgets` returns 201 with `amount_pln`; `GET /finance/budgets` lists it; `PATCH` updates amount; `DELETE` returns 204 and removes it; `POST` with an income category returns 422; `GET /finance/budget-status?month=8&year=2026` returns the item with `remaining_pln`.

- [ ] **Step 2: Run to verify they fail.**

  Run: `TEST_DATABASE_URL=... /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_budgets.py -k api -v`

  Expected: FAIL (routes missing).

- [ ] **Step 3: Add routes.**

  Import the new schemas and service functions, then add:

  ```python
  @router.get("/budgets", response_model=list[CategoryBudgetResponse])
  async def list_budgets(current_user, db):
      return await get_budgets(db, current_user.id)

  @router.post("/budgets", response_model=CategoryBudgetResponse, status_code=status.HTTP_201_CREATED)
  async def create_budget_endpoint(data: CategoryBudgetCreate, current_user, db):
      try:
          return await create_budget(db, current_user.id, data)
      except ValueError as e:
          raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

  @router.patch("/budgets/{budget_id}", response_model=CategoryBudgetResponse)
  async def update_budget_endpoint(budget_id: uuid.UUID, data: CategoryBudgetUpdate, current_user, db):
      budget = await update_budget(db, current_user.id, budget_id, data)
      if budget is None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
      return budget

  @router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_budget_endpoint(budget_id: uuid.UUID, current_user, db):
      if not await delete_budget(db, current_user.id, budget_id):
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")

  @router.get("/budget-status", response_model=BudgetStatusResponse)
  async def get_budget_status_endpoint(
      current_user,
      db,
      month: Annotated[int | None, Query(ge=1, le=12)] = None,
      year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
  ):
      return await get_budget_status(db, current_user.id, month, year)
  ```

  Note: the unique-violation on duplicate `(user_id, category_id)` surfaces as an `IntegrityError`; catch it in `create_budget_endpoint` and re-raise 422 with a clear detail message.

- [ ] **Step 4: Run focused tests to verify they pass.**

  Run: `TEST_DATABASE_URL=... /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_budgets.py -v`

  Expected: PASS. Also run `ruff check app/finance tests/test_finance/test_budgets.py` and `mypy app/finance`.

- [ ] **Step 5: Commit.**

  ```bash
  git add backend/app/finance/router.py backend/tests/test_finance/test_budgets.py
  git commit -m "feat: dodaj endpointy budżetów"
  ```

### Task 4: Frontend budget API

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write failing tests.**

  Add a pure helper `budgetProgress(budgetAmount: number, spent: number): { percent: number; over: boolean }` that clamps percent to 0–100 and flags over when `spent > budgetAmount`; test boundary cases (0 budget is impossible upstream; equal amount → 100, over → 100 + true).

  ```ts
  expect(budgetProgress(4000, 2500)).toEqual({ percent: 62.5, over: false });
  expect(budgetProgress(4000, 4000)).toEqual({ percent: 100, over: false });
  expect(budgetProgress(4000, 4500)).toEqual({ percent: 100, over: true });
  ```

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/api/finance.test.ts`

  Expected: FAIL (helper not exported).

- [ ] **Step 3: Add types, helper, and hooks.**

  Add `CategoryBudget { id; category_id; amount_pln }`, `BudgetStatusItem`, `BudgetStatusResponse`, and hooks `useBudgets`, `useCreateBudget`, `useUpdateBudget`, `useDeleteBudget`, `useBudgetStatus(period?: FinancialPeriod)`. The status hook key is `["finance","budget-status",{month,year}]` with params. Mutations invalidate `["finance","budgets"]` and `["finance","budget-status"]` (and `["finance","category-summary"]`). Export `budgetProgress`.

- [ ] **Step 4: Run focused test to verify it passes.**

  Run the Step 2 command. Then `npm --prefix frontend run typecheck`.

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts
  git commit -m "feat: dodaj API budżetów we frontendzie"
  ```

### Task 5: Budgets page

**Files:**
- Modify: `frontend/src/pages/FinanceBudgets.tsx`
- Test: `frontend/src/pages/FinanceBudgets.test.tsx`

- [ ] **Step 1: Write failing page tests.**

  Mock hooks; assert: a budget row shows name, budget, spent, and remaining; an over-budget row shows the red "over" state; the add form filters to expense categories without an existing budget; submitting add calls `useCreateBudget().mutate`; delete calls `useDeleteBudget().mutate`; the unbudgeted section renders `CategorySpendTree`. Reuse `formatPLN` and `parsePlnToGrosze`.

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/pages/FinanceBudgets.test.tsx`

  Expected: FAIL (page not implemented).

- [ ] **Step 3: Implement the page.**

  Keep the existing `MonthPicker` + title. Load `useBudgets`, `useBudgetStatus(period)`, `useCategories`, and `useCategorySummary(period)`. Render:

  - A budget list from `useBudgetStatus` sorted by name: each row shows `name`, editable amount (inline `PATCH`), `spent_pln`, `remaining_pln`, and a progress bar from `budgetProgress` (red fill when `over`, otherwise advisor accent). Show `remaining_pln < 0` as "Przekroczono o …".
  - An add form: category `<select>` filtered to `type === "expense"` minus already-budgeted ids, plus a PLN amount field using `parsePlnToGrosze`; disabled while the create mutation is pending; inline API error.
  - Delete button per row with `window.confirm`.
  - A "Wydatki bez budżetu" section rendering `CategorySpendTree` (existing component) for categories not in the budget list (pass a filtered summary if feasible; otherwise show full tree with a note).

  Handle independent loading/error states per query. No optimistic updates.

- [ ] **Step 4: Run page test, lint, typecheck, build.**

  Run: `npm --prefix frontend run test -- --run src/pages/FinanceBudgets.test.tsx && npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run build`

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/pages/FinanceBudgets.tsx frontend/src/pages/FinanceBudgets.test.tsx
  git commit -m "feat: dodaj stronę budżetów"
  ```

### Task 6: Verification, docs, deployment readiness

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run backend quality gates.**

  Run: `make VENV=/opt/finanse/backend/.venv/bin lint && make VENV=/opt/finanse/backend/.venv/bin typecheck && make VENV=/opt/finanse/backend/.venv/bin test`

  Expected: PASS. Then run `make VENV=/opt/finanse/backend/.venv/bin test-integration` on the isolated database (which the Makefile starts and cleans up); never against production.

- [ ] **Step 2: Run frontend quality gates.**

  Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test && npm --prefix frontend run build`

  Expected: PASS.

- [ ] **Step 3: Update session documentation from verified output.**

  Record only verified results in CHANGELOG, mark the budget task done in TASKS, and prepend JOURNAL with scope, decisions (recurring monthly budget, group roll-up, expense-only), test results, and next steps.

- [ ] **Step 4: Commit docs.**

  ```bash
  git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md
  git commit -m "docs: opisz miesięczne budżety"
  ```

- [ ] **Step 5: Request deployment approval.**

  Present verification evidence; note that this feature introduces a new migration (`category_budgets`) that must be applied via `alembic upgrade head` on production before/with the backend deploy. Request approval before running `/deploy`.
