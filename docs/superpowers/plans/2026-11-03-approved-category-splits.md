# Approved Category Splits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native inline TDD after approval. One independent whole-change review follows implementation. Track the steps below.

**Goal:** Let the owner approve a new PLN expense category distribution while retaining the existing payment, amounts, dates and document allocations.

**Architecture:** A focused finance command changes only category postings. A dependent categorization-state row records manual provenance/version and before/after digests; existing FinanceCommandReceipt provides replay. Context, non-mutating preview and approval endpoints expose eligibility and frozen tokens, not a generic ledger editor.

**Tech Stack:** Existing FastAPI/Pydantic/async SQLAlchemy/PostgreSQL/Alembic and React/TypeScript/TanStack Query. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-03-approved-category-splits-design.md`, stage 2 of `2026-11-03-smart-categorization-design.md`.

## Approval and boundaries

User asked to continue after stage 1 (`63e2b9c`). This plan is the next approval gate before product code. Work stays local: no deployment, production migration, historical batch, real AI/OCR, main merge or push. The existing linked worktree and unrelated Velo/Q7 files stay intact.

## Global Constraints

- Keep one FinancialTransaction and the account-side Posting ID and all of its mapped columns unchanged.
- Keep amounts in positive integer grosze, PLN only, minimum two postings and signed sum zero. A transfer, income, FX exchange or refund cannot enter this expense command.
- Preserve both dates and their metadata, allocations, source identity, document originals, loan links and Actual history pins.
- Existing categories only; each selected category belongs to the owner, is active and has type expense. No category creation, automatic merge or tree changes.
- A click on “Zatwierdź podział” authorizes a manual decision. Typing, closing, retrying a stale request or background refetch must not approve one.
- Manual classification metadata protects a decision from future automation. Absence of metadata does not mark a legacy assignment unclassified.
- Generic transaction update/delete guards remain strict. The new service does not call a blanket guard bypass.
- Snapshot, version, idempotency receipt, ledger changes and audit commit atomically. Error paths leave all unchanged.
- Add only dependent metadata after revision `84f28fe23ab8`; do not add mapped FinancialTransaction columns, alter Actual fingerprints or backfill existing rows.
- Preserve auth/CSRF/sessionVersion and per-session QueryClient from stage 1. No cross-session optimistic updates.

## Review Focus

1. A bill allocation references the account Posting. Splitting and merging categories must preserve that Posting and every allocation column (Task 1 preservation test).
2. Parent updated_at alone misses posting/metadata changes. A stale editor must lose with 409 even if another change does not touch the parent (Task 1 snapshot/race tests).
3. Category archive/type/tree edits race with approval. The command must validate fresh locked categories and refuse incompatible state without partial writes (Task 1 category race).
4. Retried acknowledgements must not duplicate postings or audit, and a reused operation ID with different intent must not apply (Task 1 retry tests).
5. A prior owner's delayed query/mutation or a same-owner re-login must not populate another session or submit an old approval (Task 2 session tests).

## File map

- `backend/app/finance/categorization.py`: eligibility, snapshots, locking, category-only apply and retry logic.
- `backend/app/finance/categorization_schemas.py`: strict read/write DTOs, error codes and minor-unit validation.
- `backend/app/finance/categorization_router.py`: owner-scoped GET/PATCH; included by finance/router.py.
- `backend/app/finance/models.py`: dependent categorization state, no transaction columns.
- `backend/app/finance/entities.py`: synchronize category deletion with the existing category-tree lock before its usage checks.
- `backend/app/config.py` and `.env.example`: configurable maximum split parts, default 50 (`FINANCE_CATEGORY_SPLIT_MAX_PARTS`). This is a builder default, not a user requirement.
- `backend/migrations/versions/<generated>_transaction_categorization_state.py`: additive migration only.
- `backend/tests/test_finance/test_categorization.py`, `test_categorization_races.py`, `test_categorization_migration.py`: focused service/API/invariant/race/migration coverage.
- `frontend/src/api/categorization.ts`: context query and session-fenced approval mutation.
- `frontend/src/components/finance/TransactionCategorizationDialog.tsx`: fetch and frozen editor state, existing Dialog/CategoryPicker.
- `frontend/src/components/finance/CategorySplitEditor.tsx`: controlled rows and safe minor-unit totals, no API writes.
- `frontend/src/components/finance/AccountTransactions.tsx` and `TransactionDetail.tsx`: entry point and current category distribution, preserving current details/date UI.
- `frontend/src/components/finance/TransactionCategorization.test.tsx`, `frontend/src/api/categorization.test.tsx`, `frontend/e2e/categorization.spec.ts`: UI, session and browser regression tests.

## Task 1: Controlled backend command and additive metadata

**Interfaces:**

- `GET /api/finance/transactions/{id}/categorization` produces `CategorizationContext`: transaction_id, eligibility `{allowed, reason_code, message}`, amount_minor/currency, current parts, manual source/version (0 without metadata), `context_snapshot` SHA-256 and server max_parts. Unsupported owned transactions return an explanation; foreign/missing return 404. It writes nothing.
  If an amount cannot fit the existing MAX_SAFE_MINOR API range, return it as unavailable (`amount_minor=null`, no editable parts) with `amount_out_of_range`; do not serialize a rounded editable number. Eligibility does not require the account to be active: existing archived-account history may be classified if its posting/account currency is PLN; the command cannot change that account.
- `POST .../categorization/preview` consumes `CategorizationPreviewRequest(expected_version: strict int >= 0, expected_context_snapshot: str[64 hex], parts: list[CategorizationPart])`. It validates the frozen context and chosen targets; returns `CategorizationPreview` with before/after parts, target paths, expected_version and `preview_snapshot`. It creates no receipt, state or audit.
- `POST .../categorization/apply` requires `Idempotency-Key` (1–255 chars) and consumes `CategorizationApply(expected_version, expected_preview_snapshot, parts, confirmed: Literal[True])`. Each part contains category_id and strict positive minor-unit amount, bounded by the existing MAX_SAFE_MINOR API constant to avoid JSON integer precision loss. Extra fields and duplicate category IDs reject. Order has no financial meaning; request hashing sorts by category UUID.
- A successful apply returns current `CategorizationContext` captured by the command. Foreign/missing is 404, protected/unsupported/stale/reused key is 409 with stable code/detail, malformed input or wrong sum is 422. Error responses reveal no foreign category information. Check current ownership before receipt replay; replay is a stored acknowledgement, not a command re-execution or current-state guarantee.
- `TransactionCategorizationState` stores transaction_id (unique dependent CASCADE FK), user_id, version > 0, source='manual', before_snapshot_sha256/after_snapshot_sha256 (64 hex) and standard Base fields. No duplicated amount list. Context hashing excludes the digest columns to avoid recursion. GET never creates the row.
- `apply_categorization(db: AsyncSession, user_id: UUID, transaction_id: UUID, data: CategorizationApply, *, idempotency_key: str) -> CategorizationContext` reuses FinanceCommandReceipt under action `apply_expense_categorization`. Same key + normalized request returns its saved JSON without writes; a different normalized request under that key returns 409. The request hash includes transaction ID, snapshot, version, confirmation and parts. A fresh command matching already manually approved parts is a no-op only after version/snapshot validation. First manual confirmation of unchanged legacy parts creates state/audit once.
- `get_categorization_context(...) -> CategorizationContext` and `preview_categorization(..., data: CategorizationPreviewRequest) -> CategorizationPreview` use the same eligibility/canonical snapshot builder as apply. Canonical schema `expense-categorization-v1` includes owner/transaction ID, every mapped transaction/posting column (postings sorted by ID, Decimal encoded at fixed six places), date metadata, metadata ID/version/source, Actual transaction mappings, loan links and allocation fields (all sorted, absent links explicit empty lists). The preview hash adds normalized parts and current target categories/ancestor paths with IDs/type/is_active/source/parent_id/updated_at. The service re-reads them on apply.
- Supported sources: manual/document_payment, booked expense, exactly one account debit and one or more category credits, all PLN/rate1/source=base and balanced. Account must be owned and currently PLN; reject malformed/null-category rows and nonuniform budget-impact semantics rather than repair them. Existing own active expense categories are valid even when imported from Actual. Actual transaction source/mapping, every LoanPaymentLink, pending, other sources/types, refunds or FX are protected. All allocations must point to the preserved account Posting, not any category Posting.
- Lock order for a new apply: receipt advisory lock → owner document-allocation advisory lock → owner category-tree advisory lock → parent transaction row → sorted Posting rows → metadata row → sorted target/current Category rows. Read account information without taking account row locks; do not call `_validate_transaction_postings` because it locks accounts late. Validate the restricted PLN shape with a focused pure validator plus `_validate_posting_sum`; category mutations share the category-tree lock. GET may be advisory; preview/apply validate under those mutation locks. No Bill rows need locks because the command cannot change them.
  Sort and lock ancestors too when building the displayed target paths. Preserve the existing uniform category-side is_budget_impact on every new part, not an unreviewed client flag or a recomputed current account setting. For deterministic ID reuse, retain rows with matching category IDs first, then reuse remaining rows in UUID order for new categories in UUID order; create missing rows, audit and remove only surplus category rows. The account row is never a reusable slot.
  A real category change or first manual confirmation advances the parent updated_at along with metadata version, so an already-open stage-1 date editor also detects a stale transaction. Replay/no-op does not advance either. Refresh updated_at explicitly before serialization; do not trigger async lazy loads during DTO construction.

- [ ] Write failing tests for 10000→8000/2000→10000, one transaction/account Posting, stable account mapped columns and both date metadata; unchanged account balances, 8000/2000 category reports and purchase-month budgets.
- [ ] Write failing tests for a document-allocated expense: same allocation IDs/columns and bill balance after split/merge; generic update/delete still rejects protected identity edits.
- [ ] Write failing API tests for foreign 404, exact +/-1 grosz rejection, empty/zero/negative/fractional/bool/overflow amounts, duplicate categories, missing/inactive/foreign/wrong-type category, malformed snapshots and spoofed ledger/provenance fields. Assert zero writes/audit on rejection.
- [ ] Write failing tests for protected Actual source/mappings/pins, loan-linked expenses, pending, other sources, FX/refund/transfer/income and unsupported legacy posting layouts. Verify own active imported categories remain selectable for a manual expense without changing category/mapping/pin rows.
- [ ] Run the new tests with the guarded `/test` equivalent in localhost55432/finanse_test; observe expected RED. Do not use a missing-module import error as the sole evidence.
- [ ] Implement strict DTOs, dependent state and context/apply services. Do not mutate FinancialTransaction monetary/date/source fields or the account Posting. Reuse category Posting IDs for matching categories; add new parts and remove only obsolete category postings after all validation, with old/new ledger state in audit.
- [ ] Implement canonical context/preview hashing, FinanceCommandReceipt replay and configurable part limit. Keep bill command code unchanged rather than refactor it into a generic runner for this task. Keep the generic document guard strict; verify unchanged account Posting/allocations before the category-only write and again before response.
- [ ] In `delete_category`, acquire the shared owner category-tree advisory lock before loading the category and checking usage; refresh under that lock. Test that a deletion admitted before approval makes approval fail, and a deletion admitted after approval sees the new category posting and refuses. Cover ONDELETESETNULL so it cannot erase a category from the just-approved ledger.
- [ ] Add deterministic concurrent tests: two different approvals, approval versus generic date edit/delete/allocation, category archive/type change, and audit failure. Use barriers, not timing assumptions; assert one permitted result, no orphan metadata, preserved identity and complete rollback.
- [ ] Generate the additive migration with `/migration "transaction categorization state"` equivalent only in a newly owned, identity-checked schema of finanse_test upgraded to 84. Remove unrelated drift, inspect DDL, test old rows/columns/indexes unchanged and no backfill. Refuse populated downgrade under EXCLUSIVE lock; test safe empty downgrade/re-upgrade only in that test schema.
- [ ] Run focused categorization + existing bill/loan/Actual/category/report/budget/date tests, ruff and mypy. Keep implementation uncommitted until the combined frozen stage is reviewed and verified.

## Task 2: Reviewable category editor

**Interfaces:** `useCategorization(id)` loads context only when the dialog opens. `usePreviewCategorization()` calls the non-mutating preview and freezes the returned diff/token. `useApplyCategorization()` captures sessionVersion, sends the frozen preview with a stable Idempotency-Key and invalidates finance ledger + categorization contexts only in that session. The editor uses `parsePlnToGrosze` and safe integer checks for each part and the sum; unsafe legacy amounts are read-only rather than rounded. Reuse the existing per-session QueryClient, no new global store.

- [ ] Write failing UI tests: open with current categories, add the second row, type 80/20, show remaining 0, forbid preview on 99.99/100.01 or missing category; closing/typing does not call apply. “Sprawdź podział” only previews; “Zatwierdź podział” applies that frozen diff. Changing parts invalidates preview. One-category confirmation uses the same command.
- [ ] Write failing UI tests: unsupported context shows the backend reason without an approval button; read error has retry; typing does not unfreeze the server snapshot during background refetch; 409 retains rows and disables approval pending close/refetch; 422 preserves rows for correction.
- [ ] Write failing session tests: old reply cannot invalidate the next client's finance cache or close a new dialog; same-session /auth/me refresh retains the editor; logout/re-login discards old reviewed state.
- [ ] Run vitest focused tests and observe RED for the expected missing behavior.
- [ ] Implement the focused editor and API hooks with existing controls/style. Show full payment amount, current/new category distribution, remaining amount and warning that budgets/reports change while payment and document allocations remain intact. Distinct preview then approval is the UI choice for the frozen target token; do not infer receipt items or create categories.
- [ ] Preserve typed values and Idempotency-Key during retry after uncertain network failure. A change of intended parts requires a fresh preview and key. A stale conflict requires close/read/review, not automatic retry. Replayed stored responses only invalidate/refetch; never install their old snapshot into the live cache.
- [ ] Add mocked E2E at 375/1440: 100→80/20, one bank payment, updated category summary/budget, 409 and exact-sum error paths, keyboard focus/a11y/no overflow. Block backend/provider traffic.
- [ ] Run full frontend vitest/lint/tsc and focused E2E/build. Backend remains the authority for sums; the mock scenario is not proof of ledger correctness.

## Task 3: Whole-stage gate and local handoff

- [ ] Dispatch one independent whole-change review against the spec/Review Focus. Verify findings, fix Critical/Important RED→GREEN; record minor follow-ups. No per-task reviewer loop or production/provider tests.
- [ ] Freeze source and run full `/test`, `/lint`, `/typecheck` equivalents against the guarded local test database, serial PostgreSQL suites. Fresh build/full E2E and source/dist manifest must match the reviewed/fixed code.
- [ ] Update CHANGELOG/TASKS/JOURNAL and local audit; commit only own files after gates. Report stage 2 locally complete, stages 3–6 pending, no deployment or production history changes. Keep the branch/worktree and unrelated files.

## Self-review and builder check

This stage covers controlled category changes and approval only. LLM proposals/rules (stage 3), receipt item extraction (stage 4), improved matching (stage 5) and historical batches (stage 6) stay out of scope. The broad spec's identity requirement means mandatory preservation of the account Posting; category-side rows change only through this audited command.

Builder check `ses_e5c9b005effeJ1ZKa1OTo63A7v` completed; no user-only blockers. Accepted: separate metadata, existing receipt table, strict source/ledger guards, account identity/allocation preservation and no late account locks. Kept repeat manual edits/merges and imported-category selection because they belong to the agreed product contract; rejected one-shot-only restriction. Target-sensitive snapshots require the added non-mutating preview. Direct code check also found category delete lacks the shared tree lock; Task 1 covers it explicitly. No application code, schema or data has changed. Native execution follows plan approval.
