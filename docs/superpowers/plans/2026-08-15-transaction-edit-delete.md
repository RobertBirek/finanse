# Transaction Edit/Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add inline edit (description, date) and delete for transactions on the transactions page, with a backend delete endpoint.

**Architecture:** Backend adds `delete_transaction` (cascade postings) + `DELETE /transactions/{id}`. Frontend adds `useUpdateTransaction`/`useDeleteTransaction` hooks and per-row edit/delete controls in `TransactionList`. Amount/account/category edits remain out of scope (delete + re-create).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, React 18, TypeScript, TanStack Query v5, Tailwind, pytest, Vitest.

---

### Task 1: Backend delete endpoint

**Files:**
- Modify: `backend/app/finance/service.py`
- Modify: `backend/app/finance/router.py`
- Test: `backend/tests/test_finance/test_ledger.py`

- [ ] **Step 1: Write failing tests.**

  Add integration tests: deleting an own transaction removes it and its postings; deleting another user's or missing returns `False`/404. Use `create_transaction` + `create_account`/`create_category` helpers and assert posting row counts drop to zero.

  ```python
  @pytest.mark.integration
  @pytest.mark.asyncio
  async def test_delete_transaction_removes_postings(db_session) -> None:
      user_id = uuid.uuid4()
      account = await create_account(db_session, user_id, AccountCreate(name="Konto", type="checking"))
      category = await create_category(db_session, user_id, CategoryCreate(name="Jedzenie", type="expense"))
      txn = await create_transaction(db_session, user_id, TransactionCreate(
          description="test", type="expense",
          postings=[
              PostingCreate(account_id=account.id, source_amount=100, base_amount_pln=100, direction="debit"),
              PostingCreate(category_id=category.id, source_amount=100, base_amount_pln=100, direction="credit"),
          ],
      ))
      assert await delete_transaction(db_session, user_id, txn.id) is True
      assert await delete_transaction(db_session, uuid.uuid4(), txn.id) is False
  ```

- [ ] **Step 2: Run to verify they fail.**

  Run: `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_ledger.py -k delete_transaction -v`

  Expected: FAIL (function missing).

- [ ] **Step 3: Implement service + route.**

  ```python
  async def delete_transaction(db: AsyncSession, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool:
      txn = await get_transaction(db, user_id, transaction_id)
      if txn is None:
          return False
      await db.delete(txn)
      await db.flush()
      return True
  ```

  Router:

  ```python
  @router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
  async def delete_transaction_endpoint(transaction_id, current_user, db):
      if not await delete_transaction(db, current_user.id, transaction_id):
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
  ```

  Import `delete_transaction`.

- [ ] **Step 4: Run focused + ruff/mypy.**

  Run the Step 2 command, then `ruff check app/finance tests/test_finance/test_ledger.py` and `mypy app/finance`.

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add backend/app/finance/service.py backend/app/finance/router.py backend/tests/test_finance/test_ledger.py
  git commit -m "feat: dodaj usuwanie transakcji"
  ```

### Task 2: Frontend update/delete hooks

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write failing tests** for the two hooks' existence (or a thin serializer test). Since hook wiring is hard to unit test without a provider, assert at minimum the exported names and that `useUpdateTransaction`/`useDeleteTransaction` are functions.

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/api/finance.test.ts`

  Expected: FAIL.

- [ ] **Step 3: Implement hooks.**

  ```ts
  export function useUpdateTransaction() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: async ({ id, data }: { id: string; data: { transaction_date?: string; description?: string } }) => {
        const { data: updated } = await api.patch<Transaction>(`/finance/transactions/${id}`, data);
        return updated;
      },
      onSuccess: () => invalidateFinanceLedger(queryClient),
    });
  }

  export function useDeleteTransaction() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: async (id: string) => { await api.delete(`/finance/transactions/${id}`); },
      onSuccess: () => invalidateFinanceLedger(queryClient),
    });
  }
  ```

  Factor `invalidateFinanceLedger(queryClient)` to invalidate `["finance","transactions"]`, `["finance","accounts"]`, `["finance","summary"]`, `["finance","category-summary"]`.

- [ ] **Step 4: Run focused test + typecheck.**

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts
  git commit -m "feat: dodaj hooki edycji i usuwania transakcji"
  ```

### Task 3: Inline edit/delete UI

**Files:**
- Modify: `frontend/src/components/finance/AccountTransactions.tsx`
- Test: `frontend/src/components/finance/AccountTransactions.test.tsx`

- [ ] **Step 1: Write failing tests** for a row with edit + delete controls: rendering an "Edytuj" button, entering edit mode shows description/date inputs, delete shows a confirm and calls the mutation. Mock the new hooks.

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/components/finance/AccountTransactions.test.tsx`

  Expected: FAIL.

- [ ] **Step 3: Implement inline edit/delete.**

  Add to each transaction row a small actions area with `Edytuj` and `Usuń`. Edit toggles an inline form (description input + date input + `Zapisz`/`Anuluj`) calling `useUpdateTransaction`. Delete calls `window.confirm` then `useDeleteTransaction`; disable both while pending; surface error inline. Preserve the direction/sign rendering.

- [ ] **Step 4: Run component test + lint + typecheck.**

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/components/finance/AccountTransactions.tsx frontend/src/components/finance/AccountTransactions.test.tsx
  git commit -m "feat: dodaj edycję i usuwanie w liście transakcji"
  ```

### Task 4: Verification, docs, deploy

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run full backend + frontend gates** (backend `make lint/typecheck/test`, integration; frontend `lint/typecheck/test/build`).

- [ ] **Step 2: Update docs**, commit.

- [ ] **Step 3: Deploy** backend + frontend (no migration), verify health.
