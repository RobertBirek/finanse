# Purchase And Booking Dates — First Vertical Slice

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, native sequential TDD. User approved local iterative implementation after the six-stage chat plan; no deployment/production migration/provider calls. Track checkboxes.

**Goal:** Manual expenses can retain two explicitly identified dates; spending/budgets use purchase date while bank lists retain booking date, without guessing old dates or breaking payment/import references.

**Architecture:** Add a one-to-one dependent `transaction_date_metadata` table, not columns on FinancialTransaction. Existing `date` remains the compatibility booking projection only after an explicit manual booking-date decision; untouched historical rows remain legacy/unknown. One controlled correction command validates actor, source, links, versions and audit; reports left join the metadata.

**Tech Stack:** Existing asyncSQLAlchemy/FastAPI/Pydantic/Alembic/PostgreSQL and React/TanStackQuery/TypeScript; no new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-smart-categorization-design.md`. This plan implements stage1 only; stages2–6 remain separately tracked in TASKS, not represented as completed by date metadata.

## Global Constraints

- No product/provider/production writes beyond local implementation and guarded testDB migration. No real LLM/OCR, classification batch, deploy/mainmerge/push or source-file deletion.
- Preserve all existing FinancialTransaction/Posting mapped columns and Actual fingerprint algorithm. New metadata rows only on explicit manual date input; no backfill.
- Keep UUIDs, amounts, currencies, FX, allocation/loan/source/recurring links and double-entry invariant unchanged by date edits.
- Manual input may create `manual` provenance only. `bank`, `document`, `import` reserved for future trusted evidence paths; client cannot select provenance.
- First slice supports new manual expense dates and controlled manual-expense correction only. Existing APIs and other transaction types retain their legacy behavior. Bill payment recording may add explicit manual booking date, never infer purchase from invoice sale_date.
- Existing Actual-source/mapped transactions and transactions linked to bill allocations or loan payments reject explicit date corrections; narrative edits remain unchanged. This is deliberate first-slice protection, not the future document matching policy.
- Booking metadata and legacy `date` stay consistent through controlled writes. Generic legacy date edits must not desynchronize existing metadata; legacy-only records remain backwards compatible.
- Unknown historical dates are displayed as unknown kind; never label them bank-confirmed. Missing purchase date falls back to legacy booking projection in reports with visible explanation.
- New date metadata has the transaction's lifecycle: dependent-row CASCADE only for this new annotation on an already-authorized transaction deletion. No existing FK or original/history deletion behavior changes; date audit entries are retained.
- Expense reports use purchase basis; income/transfer/exchange, cashflow/loan matching and account balance arithmetic are not silently moved to purchase basis.

## Review Focus

- Actual preserved-history pins must remain valid: no new mapped transaction columns or legacy-date backfill (Task1 fingerprint/migration tests).
- Shared payment IDs and protected loans/bills must survive corrections; stale/out-of-owner commands cannot edit anything (Task1 integration/races/API).
- A January purchase posted in February appears once in January spending and February bank lists; joins must not multiply split postings (Task2 reporting/budget/search tests).
- Generic legacy date edits/deletion cannot leave stale metadata or bypass protected payment identity (Task1 update/delete tests).
- Old and new frontend fixtures/session changes must not relabel unknown dates or invalidate another session's cache (Task2 UI/mutation tests).

## Task 1: Additive model, controlled create/correction and migration

**Files:** models.py, schemas.py, new transaction_dates.py; transactions.py, router.py and bill_payments.py; additive migration after2f; new tests/test_finance/test_transaction_dates.py and test_transaction_dates_api.py.

**Interfaces:** `TransactionCreate` gains optional purchase_date/booking_date; legacy transaction_date remains accepted alone, conflicting explicit/legacy input rejected. Expense explicit purchase requires booking. Response gains optional date_metadata with purchase_date/booking_date, their sources and positive version; no metadata means legacy_unknown. New `TransactionDatesUpdate(purchase_date: date|None, booking_date: date, expected_version: int, expected_updated_at: datetime)`; `PATCH /finance/transactions/{id}/dates` returns TransactionResponse, owner404, stale409, protected409, validation422. Missing metadata has expected_version0; updates increment version, no-op stays stable. Parent transaction/advisory lock precedes annotation lock. Payload cannot set sources/amounts.

- [x] RED: explicit manual10000PLN expense with purchase2026-01-30/booking2026-02-02 yields one transaction, original account/category postings, manual provenance; legacy expense remains no metadata; client Actual explicit dates rejected by schema.
- [x] RED: owned manual correction retains posting IDs/amounts/balance; foreign404, stale metadata/updated_at409; linked bill/loan/import protected; description-only edits unchanged; same payload no-op, generic legacy date divergence rejected; authorized transaction deletion removes annotation but retains audit.
- [x] Implement table/date-source pair constraints/version/one-to-one/selectin relationship and create/correct service. Do not alter Actual fingerprint. Audit before/after date metadata, no private document contents.
- [x] Generate via `/migration "transaction date metadata"` equivalent only after checking empty owned schema in localfinanse_test and upgrading it to2f. Reviewed84f28fe23ab8: CREATE-only diff, downgrade guard refusing populated metadata, actual oldrows/columns/indexesretentionPASS; never applied to production.
- [x] GREEN focused149 tests plus backendlint/types; retain full-suite verification for final frozen combined slice. No unverified implementation commit between tasks.

## Task 2: Purchase-basis reports and explicit-date UI

**Files:** reporting.py, budgets.py, existing queries/search/response paths; frontend api/finance.ts, TransactionForm.tsx, AccountTransactions.tsx; new TransactionDatesDialog.tsx and small shared TransactionDateLabel.tsx, transaction search/detail labels; tests and mockedE2E.

**Interfaces:** report expense date expression `coalesce(TransactionDateMetadata.purchase_date, FinancialTransaction.date)` with one-to-one LEFTJOIN; account/search dates remain `FinancialTransaction.date` because explicit booking projection is synchronized. Existing amounts and aggregate trees unchanged. Frontend receives nested metadata, uses explicit booking/purchase controls only for expense path; other types retain old payload. Correction hook captures session identity, invalidates finance queries only for matching session, does not optimistic-rewrite imported data.

- [x] RED: Januarypurchase/Februarybooking reports/categorybudgetJanuary10000, February0, banksearchFebruary10000; legacy fallback unchanged; multi-category80/20 sums once; income dates unchanged.
- [x] Implement shared purchase date expression and report joins; label purchase basis/fallback in reports and booking/unknown basis in transaction views. No account balance, import, recurrence or loan-date semantic rewrite.
- [x] RED UI: manual create has purchase and booking date with same-date convenience; emits no conflicting legacy field. Legacy row says unknown date kind. Date correction is separate from narrative edit, captures version/snapshot, retains typed values on409 and demands refetch; no stale-session invalidation.
- [x] Implement hooks/labels/dialog using existing theme/TanStackQuery. Preserve session/owner isolation, no new global store/dependencies. Avoid extra per-row queries by selectin metadata loading. Review additionally required per-session QueryClient provider and authStore generation, not user object reference.
- [x] GREEN fullfrontend416/lint/types and fullmockedE2E105+1skip before review;375/1440 datecreate/conflict/basis/a11y/nooverflowPASS. After review14focused auth/cache/date regressionsPASS. Final whole frozen gate pending below.

## Task 3: Whole-slice acceptance and local handoff

- [x] One independent whole-change review ses_e5ccc37e3ffeA4gw1JvV5CC2p6; Critical0, Important1 financecache +Minor1 same-sessionrefresh both verified3RED→GREEN with14focusedPASS. No production/provider checks or second review.
- [x] Run full `/test`, `/lint`, `/typecheck` equivalents in guardedenv serialDB:1205backend/420frontend/lint/typesPASS; freshbuild/fullE2E105+1expectedskipPASS, additive migration/retentionPASS; exactsource/dist proofPASS. Nonfatalbuildwarnings recorded in audit, not hidden.
- [x] Update CHANGELOG/TASKS/JOURNAL and local audit after gates; commit own date-slice files only, leave existing Velo/Q7 dirty files and host/worktree intact. Stage1 delivered locally, stages2–6 pending, not deployed.

## Builder check and rulings

Read-only builder check ses_e5d4b34f0ffeW0y33suCxOx4bb found no blocking user-only question. One-to-one metadata avoids breaking Actual fingerprint, parent locking avoids orphan/concurrent edits. Conservative phase1 protection rejects imported/linked date changes; future evidence-based linking is not implemented here. Numeric ledger rows never come from LLM.
