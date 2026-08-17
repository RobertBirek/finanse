# Accounts & Categories CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete CRUD for accounts and categories with the user's rule: entities with records cannot be deleted — only deactivated and hidden from lists; empty entities can be hard-deleted.

**Architecture:** Backend adds `categories.is_active` (migration), delete services with reference checks (409 blocked), `is_active` on category update, and inactive-entity rejection in transaction/scheduler/budget creation. Frontend adds management hooks and a `/finances/accounts` page, and filters inactive entities from all selection lists.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, React 18, TypeScript, TanStack Query v5, pytest, Vitest.

---

### Task 1: Backend migration + delete/update services + validation + routes

**Files:**
- Modify: `backend/app/finance/models.py`
- Create: `backend/migrations/versions/<new>_category_active.py`
- Modify: `backend/app/finance/schemas.py`
- Modify: `backend/app/finance/service.py`
- Modify: `backend/app/finance/router.py`
- Test: `backend/tests/test_finance/test_entities_crud.py` (new)

- [ ] **Step 1: Write failing tests** (integration):
  - delete empty account → True and gone; delete account with a posting → blocked (`ValueError`) and account remains; delete foreign account → False.
  - delete empty category → True; category with posting → blocked; category with budget → blocked; category with scheduled item → blocked; category with child category → blocked; foreign → False.
  - `update_category` sets `is_active=False` and `CategoryResponse` includes it.
  - create transaction with inactive account → ValueError; inactive category → ValueError; create budget with inactive category → ValueError; create scheduled item with inactive category → ValueError.
  - API: `DELETE /accounts/{id}` 204 empty / 404 foreign / 409 blocked; `DELETE /categories/{id}` same.

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement migration.**

  Add `is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)` to `Category` and generate/hand-write the migration (pattern `8a6d0c1e2b3f`): `op.add_column("categories", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))`; downgrade drops it.

- [ ] **Step 4: Implement schemas.**

  `CategoryUpdate.is_active: bool | None = None`; `CategoryResponse.is_active: bool`.

- [ ] **Step 5: Implement services.**

  ```python
  async def delete_account(db, user_id, account_id) -> bool:
      account = await get_account(db, user_id, account_id)
      if account is None:
          return False
      postings = await db.execute(select(func.count()).select_from(Posting).where(Posting.account_id == account_id))
      scheduled = await db.execute(select(func.count()).select_from(ScheduledFinanceItem).where(ScheduledFinanceItem.account_id == account_id))
      if postings.scalar_one() or scheduled.scalar_one():
          raise ValueError("Account has records; deactivate it instead of deleting")
      await db.delete(account)
      await db.flush()
      return True

  async def delete_category(db, user_id, category_id) -> bool:
      result = await db.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id))
      category = result.scalar_one_or_none()
      if category is None:
          return False
      refs = [
          select(func.count()).select_from(Posting).where(Posting.category_id == category_id),
          select(func.count()).select_from(ScheduledFinanceItem).where(ScheduledFinanceItem.category_id == category_id),
          select(func.count()).select_from(CategoryBudget).where(CategoryBudget.category_id == category_id),
          select(func.count()).select_from(Category).where(Category.parent_id == category_id),
      ]
      for stmt in refs:
          if (await db.execute(stmt)).scalar_one():
              raise ValueError("Category has records; deactivate it instead of deleting")
      await db.delete(category)
      await db.flush()
      return True
  ```

  Update `_validate_transaction_postings`: account must be active; category must exist, be active, and type match semantics already enforced elsewhere (category active check add). Update `_validate_scheduled_item_links`: category `is_active` check. Update `_require_expense_category`: category `is_active` check.

- [ ] **Step 6: Implement routes.**

  `DELETE /accounts/{account_id}` and `DELETE /categories/{category_id}`: service False → 404; ValueError → 409 (HTTP_409_CONFLICT) with the message; else 204.

- [ ] **Step 7: Run focused + ruff/mypy + full finance tests.**

- [ ] **Step 8: Commit.**

  ```bash
  git add backend/app/finance backend/migrations/versions backend/tests/test_finance/test_entities_crud.py
  git commit -m "feat: dodaj usuwanie i dezaktywację kont i kategorii"
  ```

### Task 2: Frontend hooks

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write failing tests** for `useUpdateAccount`, `useDeleteAccount`, `useUpdateCategory`, `useDeleteCategory` (URL/method assertions via renderHook pattern; update payloads include `is_active`).

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement hooks** (PATCH/DELETE, invalidate `["finance","accounts"]`, `["finance","categories"]`, ledger). Add `is_active` to the `Category` type.

- [ ] **Step 4: Run focused test + typecheck.**

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts
  git commit -m "feat: dodaj hooki zarządzania kontami i kategoriami"
  ```

### Task 3: Management page `/finances/accounts`

**Files:**
- Create: `frontend/src/pages/FinanceAccounts.tsx`
- Test: `frontend/src/pages/FinanceAccounts.test.tsx`
- Modify: `frontend/src/App.tsx` (route), `frontend/src/components/navigation.ts` (link „Konta"), `frontend/src/components/navigation.test.tsx`

- [ ] **Step 1: Write failing tests** for the page: create account form, edit name, active toggle, delete calls hook, 409 error message shown; categories section with create/edit/toggle/delete.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement page** with two sections (Konta / Kategorie), each: list all (including inactive, with badge), create form, inline edit (name/type/budget flag; category: name/type/parent select), active toggle, delete with confirm and 409 error surfacing. Dark palette, a11y.

- [ ] **Step 4: Run page test + lint + typecheck.**

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/pages/FinanceAccounts.tsx frontend/src/pages/FinanceAccounts.test.tsx frontend/src/App.tsx frontend/src/components/navigation.ts frontend/src/components/navigation.test.tsx
  git commit -m "feat: dodaj stronę zarządzania kontami"
  ```

### Task 4: Filter inactive entities in lists

**Files:**
- Modify: `frontend/src/components/finance/TransactionForm.tsx` (categories filter + tests)
- Modify: `frontend/src/components/finance/ScheduledItemForm.tsx` (categories filter)
- Modify: `frontend/src/pages/FinanceBudgets.tsx` (add-form category filter)
- Modify: `frontend/src/components/finance/AccountTransactions.tsx` (hide inactive accounts)
- Modify: `frontend/src/pages/Finances.tsx` (hide inactive accounts)

- [ ] **Step 1: Write failing tests** asserting inactive categories/accounts are excluded from selectors/lists.

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement filters** (`is_active !== false` where lists are used).

- [ ] **Step 4: Run tests + lint + typecheck + build.**

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src
  git commit -m "feat: ukryj nieaktywne konta i kategorie z list"
  ```

### Task 5: Verification, docs, deploy

- [ ] **Step 1: Run full backend + frontend gates** including integration (migration applied on isolated DB).

- [ ] **Step 2: Update docs, commit.**

- [ ] **Step 3: Run production migration** (`alembic upgrade head` in the backend container) and deploy; verify health.
