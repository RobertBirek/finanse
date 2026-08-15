# Manual Transaction Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual transaction entry form (income, expense, transfer) to `/finances/transactions`, writing balanced double-entry postings through the existing finance service.

**Architecture:** No new models or migrations. The frontend builds postings via a pure, tested helper `buildTransactionPostings` that encodes the ledger direction convention (`balance = credit − debit`), then submits through the existing `useCreateTransaction` → `POST /finance/transactions`. The server service `create_transaction` remains authoritative for the double-entry invariant.

**Tech Stack:** React 18, TypeScript, TanStack Query v5, Tailwind, Vitest. (No backend changes.)

---

## File structure

| File | Responsibility |
|---|---|
| `frontend/src/api/finance.ts` | Export `buildTransactionPostings` helper (or colocate in a lib) and types. |
| `frontend/src/api/finance.test.ts` | Unit tests for the posting builder. |
| `frontend/src/components/finance/TransactionForm.tsx` | The entry form (type, accounts, category, amount, date, description). |
| `frontend/src/components/finance/TransactionForm.test.tsx` | Form behavior tests. |
| `frontend/src/pages/FinanceTransactions.tsx` | Mount the form above the transaction list. |

### Task 1: Posting builder helper

**Files:**
- Modify: `frontend/src/api/finance.ts`
- Test: `frontend/src/api/finance.test.ts`

- [ ] **Step 1: Write failing tests.**

  Add tests asserting the direction convention and amounts for all three types, plus the signed-sum-zero invariant (debit positive, credit negative):

  ```ts
  import { buildTransactionPostings } from "./finance";

  const pln = { source_currency: "PLN", base_amount_pln: 2500, fx_rate: 1, fx_rate_source: "manual" };

  expect(buildTransactionPostings({
    type: "income", accountId: "a1", categoryId: "c1", amountPlng: 2500,
  })).toEqual([
    { account_id: "a1", category_id: null, source_amount: 2500, direction: "credit", ...pln },
    { account_id: null, category_id: "c1", source_amount: 2500, direction: "debit", ...pln },
  ]);

  expect(buildTransactionPostings({
    type: "expense", accountId: "a1", categoryId: "c1", amountPlng: 2500,
  })[0].direction).toBe("debit");

  expect(buildTransactionPostings({
    type: "transfer", fromAccountId: "a1", toAccountId: "a2", amountPlng: 2500,
  })).toEqual([
    { account_id: "a1", category_id: null, source_amount: 2500, direction: "debit", ...pln },
    { account_id: "a2", category_id: null, source_amount: 2500, direction: "credit", ...pln },
  ]);

  // signed sum zero
  const signed = (p: { direction: string; base_amount_pln: number }) =>
    p.direction === "debit" ? p.base_amount_pln : -p.base_amount_pln;
  expect(buildTransactionPostings({ type: "income", accountId: "a", categoryId: "c", amountPlng: 2500 })
    .reduce((s, p) => s + signed(p), 0)).toBe(0);
  ```

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/api/finance.test.ts`

  Expected: FAIL (helper not exported).

- [ ] **Step 3: Implement the helper.**

  Export a typed helper in `finance.ts`:

  ```ts
  export interface PostingInput {
    account_id: string | null;
    category_id: string | null;
    source_amount: number;
    source_currency: string;
    base_amount_pln: number;
    fx_rate: number;
    fx_rate_source: string;
    direction: "debit" | "credit";
  }

  export type BuildPostingsInput =
    | { type: "income" | "expense"; accountId: string; categoryId: string; amountPlng: number }
    | { type: "transfer"; fromAccountId: string; toAccountId: string; amountPlng: number };

  export function buildTransactionPostings(input: BuildPostingsInput): PostingInput[] {
    const base = (accountId: string | null, categoryId: string | null, direction: "debit" | "credit"): PostingInput => ({
      account_id: accountId,
      category_id: categoryId,
      source_amount: input.amountPlng,
      source_currency: "PLN",
      base_amount_pln: input.amountPlng,
      fx_rate: 1,
      fx_rate_source: "manual",
      direction,
    });
    if (input.type === "income") {
      return [base(input.accountId, null, "credit"), base(null, input.categoryId, "debit")];
    }
    if (input.type === "expense") {
      return [base(input.accountId, null, "debit"), base(null, input.categoryId, "credit")];
    }
    return [base(input.fromAccountId, null, "debit"), base(input.toAccountId, null, "credit")];
  }
  ```

- [ ] **Step 4: Run focused test to verify it passes.**

  Run the Step 2 command. Then `npm --prefix frontend run typecheck`.

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/api/finance.ts frontend/src/api/finance.test.ts
  git commit -m "feat: dodaj budowniczy postingów transakcji"
  ```

### Task 2: Transaction form component

**Files:**
- Create: `frontend/src/components/finance/TransactionForm.tsx`
- Test: `frontend/src/components/finance/TransactionForm.test.tsx`

- [ ] **Step 1: Write failing component tests.**

  Mock `useAccounts`, `useCategories`, `useCreateTransaction`. Assert:
  - default type `expense`; switching to `income` shows income categories, `transfer` hides the category field and shows two account selects;
  - the account select lists only active PLN accounts;
  - submit with type expense + account + category + amount `"25"` calls `useCreateTransaction().mutate` with `postings` whose account posting is `debit` and category posting `credit`, `base_amount_pln === 2500`, and a non-empty description;
  - empty amount shows a validation message and does not submit.

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/components/finance/TransactionForm.test.tsx`

  Expected: FAIL (component missing).

- [ ] **Step 3: Implement the form.**

  `TransactionForm` props: `{ onSuccess?: () => void }`. Load `useAccounts` and `useCategories`; keep a `type` state (`expense` default). Filter active PLN accounts and categories by type. Controlled fields: account(s), category, amount string (via `parsePlnToGrosze`), date (default local today ISO), description. For transfer, two account selects (to excludes the from account). On submit: validate amount/description/category, call `buildTransactionPostings`, then `create.mutate({ type, description, date, postings })`. Disable submit while pending, show `create.error` inline, reset form on success. No optimistic updates.

- [ ] **Step 4: Run component test, lint, typecheck.**

  Run: `npm --prefix frontend run test -- --run src/components/finance/TransactionForm.test.tsx && npm --prefix frontend run lint && npm --prefix frontend run typecheck`

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/components/finance/TransactionForm.tsx frontend/src/components/finance/TransactionForm.test.tsx
  git commit -m "feat: dodaj formularz transakcji"
  ```

### Task 3: Page integration and verification

**Files:**
- Modify: `frontend/src/pages/FinanceTransactions.tsx`
- Test: `frontend/src/pages/FinanceTransactions.test.tsx`

- [ ] **Step 1: Write failing page test.**

  Assert the page renders a heading and includes `TransactionForm` (query for its accessible name, e.g. "Dodaj transakcję") above the `AccountTransactions` list.

- [ ] **Step 2: Run to verify it fails.**

  Run: `npm --prefix frontend run test -- --run src/pages/FinanceTransactions.test.tsx`

  Expected: FAIL (form not mounted).

- [ ] **Step 3: Mount the form.**

  Add `TransactionForm` above `AccountTransactions` in `FinanceTransactions`, wrapping in a `card`. Give the section an accessible heading "Dodaj transakcję".

- [ ] **Step 4: Run full frontend gate.**

  Run: `npm --prefix frontend run test && npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run build`

  Expected: PASS.

- [ ] **Step 5: Commit.**

  ```bash
  git add frontend/src/pages/FinanceTransactions.tsx frontend/src/pages/FinanceTransactions.test.tsx
  git commit -m "feat: podepnij formularz transakcji"
  ```

### Task 4: Verification, docs, deployment

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run full backend + frontend quality gates.**

  Run backend `make VENV=/opt/finanse/backend/.venv/bin lint typecheck test` and frontend `npm --prefix frontend run lint/typecheck/test/build`. Backend is unchanged but must stay green.

  Expected: PASS.

- [ ] **Step 2: Update docs from verified output.**

  Record scope, direction convention, PLN-only limitation, and test results in CHANGELOG/TASKS/JOURNAL.

- [ ] **Step 3: Commit docs.**

  ```bash
  git add docs/CHANGELOG.md docs/TASKS.md docs/JOURNAL.md
  git commit -m "docs: opisz ręczne księgowanie transakcji"
  ```

- [ ] **Step 4: Deploy.**

  This feature is frontend-only (no migration). Build and restart backend/frontend, then verify `/api/health` and the frontend bundle. Request approval if required.
