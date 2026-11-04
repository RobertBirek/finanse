# Approved Category Splits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for native inline TDD after approval. One independent whole-change review follows implementation. Track the steps below.

**Goal:** Let the owner approve a new PLN expense category distribution while retaining the existing payment, amounts, dates and document allocations.

**Architecture:** A focused finance command changes only category postings. A dependent categorization-state row records manual provenance/version and before/after digests; existing FinanceCommandReceipt provides replay. Context, non-mutating preview and approval endpoints expose eligibility and frozen tokens, not a generic ledger editor.

**Tech Stack:** Existing FastAPI/Pydantic/async SQLAlchemy/PostgreSQL/Alembic and React/TypeScript/TanStack Query. No new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-03-approved-category-splits-design.md`, stage 2 of `2026-11-03-smart-categorization-design.md`.

## Approval and boundaries

User approved the full plan in commit `656e9e6` with “tak” after stage 1 (`63e2b9c`). Work stays local: no deployment, production migration, historical batch, real AI/OCR, main merge or push. The existing linked worktree and unrelated Velo/Q7 files stay intact.

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
- `backend/app/finance/categorization_router.py`: owner-scoped GET/context and POST/preview/apply; included by finance/router.py.
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
- Supported sources: manual/document_payment, booked expense, exactly one account debit and one or more category credits, all PLN/rate1/`source_amount == base_amount_pln` and balanced. This is a numerical invariant, not a required `fx_rate_source="base"` label; retain the established manual PLN provenance convention. Account must be owned and currently PLN; reject malformed/null-category rows and nonuniform budget-impact semantics rather than repair them. Existing own active expense categories are valid even when imported from Actual. Actual transaction source/mapping, every LoanPaymentLink, pending, other sources/types, refunds or FX are protected. All allocations must point to the preserved account Posting, not any category Posting.
- Lock order for a new apply: receipt advisory lock → owner document-allocation advisory lock → owner category-tree advisory lock → parent transaction row → sorted Posting rows → metadata row → sorted target/current Category rows. Read account information without taking account row locks; do not call `_validate_transaction_postings` because it locks accounts late. Validate the restricted PLN shape with a focused pure validator plus `_validate_posting_sum`; category mutations share the category-tree lock. GET may be advisory; preview/apply validate under those mutation locks. No Bill rows need locks because the command cannot change them.
  Sort and lock ancestors too when building the displayed target paths. Preserve the existing uniform category-side is_budget_impact on every new part, not an unreviewed client flag or a recomputed current account setting. For deterministic ID reuse, retain rows with matching category IDs first, then reuse remaining rows in UUID order for new categories in UUID order; create missing rows, audit and remove only surplus category rows. The account row is never a reusable slot.
  A real category change or first manual confirmation advances the parent updated_at along with metadata version, so an already-open stage-1 date editor also detects a stale transaction. Replay/no-op does not advance either. Refresh updated_at explicitly before serialization; do not trigger async lazy loads during DTO construction.
  Review hardening: all `update_account` operations take the same owner document-allocation advisory lock before reads/row locks, not just currency changes. This serializes the approved full account-state snapshot without a late account-row lock; account edits admitted first invalidate the preview, and edits admitted later wait until approval ends.

- [x] Initial20RED→GREEN proved context/apply, 10000→8000/2000→10000, stable account Posting, totals/balances, replay/no-op and protected source/type states. Additional tests cover purchase date metadata/budgets and imported target categories.
- [x] Allocation preservation test plus existing full bill/date/loan guards verify payment/reference identity and protected generic update/delete; the split/merge identity invariant is covered in the category-only mutation tests.
- [x] Negative API matrix covers foreign404, exact +/-1 grosz, empty/zero/negative/fractional/bool/overflow, duplicate/missing/inactive/foreign/wrong-type categories. Supplemental pure probes verify malformed token, spoofed source/account/FX, boolversion, configured part limit and literal confirmation. No rejection creates a category receipt/state.
- [x] Actual mappings/pins, loan/refund/pending/other sources/types/FX and malformed ledgers covered by new tests plus inherited fullfinance suites. Existing imported categories remain selectable without rewriting definitions/mappings.
- [x] Guarded RED executed in localhost55432/finanse_test:20routebehavior failures, not a missing-module error. Subsequent race/preview regressions recorded RED→GREEN separately.
- [x] Implement strict DTOs, dependent state and context/apply services. No FinancialTransaction monetary/date/source fields or account Posting changes. Matching category IDs reused, only surplus category postings removed with old/new audit.
- [x] Canonical context/preview, FinanceCommandReceipt replay and configurable limit implemented; bill runner and generic document guard unchanged. Owner allocation mutex serializes references and account edits; account Posting invariant compared, allocation invariance checked in integration tests.
- [x] In `delete_category`, acquire shared owner category-tree advisory lock before loading/checking usage and refresh under it. Deterministic ONDELETESETNULL race reproduced RED and fixed GREEN; category disappearance/archive invalidates the approved preview.
- [x] Deterministic concurrency covers two approvals, authorized delete, category delete/SETNULL and both account-update orders; archive/token staleness and audit-failure rollback covered separately. Existing shared owner mutex and full bill/date suites cover the inherited allocation/date mutation paths; no second bespoke test for every combination.
- [x] Generated2268bca97cb8 via `/migration` equivalent only in owned finanse_test schema upgraded to84; unrelated index drift removed. Real alloldrows/columns/indexesretention/nobackfill/emptyrollback/reupgrade/populateddowngradeguardPASS under EXCLUSIVE lock.
- [x] Focused140backend +7eligibility/1auth-CSRF/28account-races PASS; final full1250backend/lint/mypyPASS. No implementation commit before reviewed/frozen stage gate.

## Task 2: Reviewable category editor

**Interfaces:** `useCategorization(id)` loads context only when the dialog opens. `usePreviewCategorization()` calls the non-mutating preview and freezes the returned diff/token. `useApplyCategorization()` captures sessionVersion, sends the frozen preview with a stable Idempotency-Key and invalidates finance ledger + categorization contexts only in that session. The editor uses `parsePlnToGrosze` and safe integer checks for each part and the sum; unsafe legacy amounts are read-only rather than rounded. Reuse the existing per-session QueryClient, no new global store.

- [x] UI tests and browser scenario cover current rows, 80/20, exact-sum blocking, no apply on typing/close, separate preview/approval and merge back. Diff and pendingEscape regressions verified RED→GREEN.
- [x] Unsupported-reason/409 retention tested; shared QueryFeedback provides read retry. Frozen useState context and error handling retain edits on nonstale errors; reviewed with inherited component/session suites.
- [x] New preview/apply session-fence tests and inherited SessionQueryProvider/auth refresh suites pass; old replies do not install or invalidate the next session's cache.
- [x] Vitest5initialRED→GREEN; before/after+busyEscape2RED→GREEN and detailentry1RED→GREEN.
- [x] Focused editor/hooks use existing style and controls with full payment/before-after/remainder/financial-impact warning; no item extraction/category creation or automatic approval.
- [x] Typed values/key retained for uncertain retry; editing invalidates preview/key, stale409 requires new read/review. Receipt replies only invalidate current reads, never install old snapshots.
- [x] Mocked browser375/1440 proves100→80/20→100, one payment, reports/budgets, exact-sum blocking, a11y/nooverflow/focus and no backend/provider traffic.409 behavior tested at UI/API boundaries.
- [x] Full429frontend/lint/tsc and freshbuild/fullE2E107+1expectedskipPASS. Real backend tests, not mocked browser data, prove ledger sums and identity.

## Task 3: Whole-stage gate and local handoff

- [x] One whole-review ses_e5c6ac4e2ffeY67NUsPOSm3fwl: Important accountstateTOCTOU2RED→GREEN/focused28PASS; source=base shorthand clarified as numeric equality. No secondreview or production/provider actions.
- [x] Frozen fullgate1250backend/429frontend/lint/typesPASS; freshbuild/fullE2E107+1expectedskip and exact source/dist/migrationhash proofPASS. PostgreSQL suites serial and guarded, no production/provider calls.
- [x] CHANGELOG/TASKS/JOURNAL and local audit finalized; own-files-only commit follows verified gates. Stage2 locally complete, stages3–6 pending, not deployed. Branch/worktree and unrelatedVelo/Q7 preserved.

## Self-review and builder check

This stage covers controlled category changes and approval only. LLM proposals/rules (stage 3), receipt item extraction (stage 4), improved matching (stage 5) and historical batches (stage 6) stay out of scope. The broad spec's identity requirement means mandatory preservation of the account Posting; category-side rows change only through this audited command.

Builder check `ses_e5c9b005effeJ1ZKa1OTo63A7v` completed without user-only blockers. Accepted separate state/receipt, strict guards and immutable payment. Kept repeat manual edits/merges and existing imported-category selection. Context helper separation and consolidated verification matrix are ledgered rulings. User approved before implementation; native stage2 now verified locally. Audit: `docs/audits/2026-11-04-approved-category-splits-local.md`.
