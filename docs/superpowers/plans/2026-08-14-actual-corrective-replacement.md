# Actual Corrective Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Actual category reconciliation independent and fail closed, then add a backup-gated replacement command that preserves manual data.

**Architecture:** Accounts and categories receive persistent importer provenance. Reconciliation derives expected leaf-category values directly from parser legs and FX quotes, with group aggregation on both the Actual and PA sides. The CLI validates all replacement flags, verifies a PostgreSQL custom-format backup before opening its write session, proves legacy ownership and manual-reference safety inside one transaction, then relies on the reconciliation exception to roll back unsafe imports.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, PostgreSQL 16 tools (`pg_dump`, `pg_restore`), SQLite Actual parser, pytest/pytest-asyncio.

---

## File Structure

- Modify: `backend/app/finance/models.py` - persistent `source` on imported entity models.
- Create: `backend/migrations/versions/<revision>_actual_entity_provenance.py` - add non-null source columns with safe defaults.
- Modify: `backend/scripts/migrate_actual.py` - independent category reconciliation, group totals, verified backup, legacy proof, controlled cleanup, CLI validation.
- Modify: `backend/app/finance/reconciliation.py` - separate category-group report rows and fail-closed status.
- Modify: `backend/tests/test_finance/test_reconciliation.py` - independent reconciliation and group regression tests.
- Modify: `backend/tests/test_finance/test_actual_import.py` - importer provenance and replacement safety integration tests.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` - verified outcome only.

### Task 1: Persist Actual Entity Provenance

**Files:**
- Modify: `backend/app/finance/models.py`
- Create: `backend/migrations/versions/<revision>_actual_entity_provenance.py`
- Modify: `backend/scripts/migrate_actual.py`
- Test: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Write the failing integration test**

Add a test importing a one-account, one-category Actual SQLite fixture and assert:

```python
assert imported_account.source == "actual"
assert imported_category.source == "actual"
assert manual_account.source == "manual"
assert manual_category.source == "manual"
```

- [ ] **Step 2: Run the focused test to verify RED**

Run: `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestMigrationPipeline::test_import_persists_actual_entity_provenance -v`

Expected: FAIL because `Account` and `Category` do not expose `source`.

- [ ] **Step 3: Add the minimal model and migration support**

Add non-null `source: Mapped[str]` fields to `Account` and `Category`, defaulting to `manual`. Create an Alembic revision that adds both columns with a temporary `manual` server default, then removes the server defaults. Pass `source="actual"` only when `resolve_ids` creates importer accounts, category groups, and categories.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run the Step 2 command after applying the migration to the isolated database.

Expected: PASS.

### Task 2: Make Category And Group Reconciliation Independent

**Files:**
- Modify: `backend/app/finance/reconciliation.py`
- Modify: `backend/scripts/migrate_actual.py`
- Test: `backend/tests/test_finance/test_reconciliation.py`

- [ ] **Step 1: Write failing unit tests for independent category totals**

Add a fixture with `Transport -> Fuel`, one 50 PLN expense, and mappings for both IDs. Patch `build_pa_postings` to raise. Assert the expected category calculator returns the signed Fuel balance and a 50 PLN Transport group balance without calling the patched function.

Add a report test asserting a group discrepancy produces:

```python
assert report.category_groups[0].is_reconciled is False
assert report.is_reconciled is False
with pytest.raises(ReconciliationError):
    require_reconciled(report)
```

- [ ] **Step 2: Run focused reconciliation tests to verify RED**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_reconciliation.py -v`

Expected: FAIL because the calculator calls `build_pa_postings` and reports have no group rows.

- [ ] **Step 3: Implement direct source-leg calculation and group aggregation**

Implement a direct expected-category loop that validates mappings and converts source amounts using `_posting_base_amount`, reverses the parser direction without creating `PostingCreate`, and adds errors for any rejected transaction. Extend `ReconciliationReport` with `category_groups`, serialize it, include it in text, and require all group rows to reconcile. Return the category-group map from `resolve_ids`; compute PA group values by summing direct child category posting totals for those mapped parent IDs.

- [ ] **Step 4: Run focused reconciliation tests to verify GREEN**

Run the Step 2 command.

Expected: PASS.

### Task 3: Add Verified PostgreSQL Backup And Flag Validation

**Files:**
- Modify: `backend/scripts/migrate_actual.py`
- Test: `backend/tests/test_finance/test_reconciliation.py`

- [ ] **Step 1: Write failing tests for corrective CLI guards and backup verification**

Test that `main()` rejects `--replace-legacy-actual` without all of `--execute`, `--require-reconciled`, and `--backup-path`. Mock the subprocess runner and assert a valid invocation runs:

```python
pg_dump --format=custom --file <temporary path>
pg_restore --list <temporary path>
```

and atomically creates the requested backup. Test an existing target and `pg_restore` failure leave no published backup and do not invoke migration.

- [ ] **Step 2: Run backup tests to verify RED**

Run: `/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_reconciliation.py -k "backup or replacement_cli" -v`

Expected: FAIL because the flags and backup helper do not exist.

- [ ] **Step 3: Implement verified backup and CLI guards**

Parse `settings.DATABASE_URL` through SQLAlchemy's URL parser; pass connection fields to `pg_dump` through a child environment rather than command-line credentials. Write to a same-directory temporary file, require a successful `pg_restore --list`, set mode `0600`, and use `Path.replace` only after verification. Require a non-existing target with an existing parent. Invoke this helper immediately before calling replacement migration logic.

- [ ] **Step 4: Run backup tests to verify GREEN**

Run the Step 2 command.

Expected: PASS.

### Task 4: Replace Only Proven Actual Rows

**Files:**
- Modify: `backend/scripts/migrate_actual.py`
- Test: `backend/tests/test_finance/test_actual_import.py`

- [ ] **Step 1: Write failing replacement integration tests**

Create one legacy Actual account/category/transaction and one manual account/category/transaction for a single user. Make the legacy transaction description reference the fixture's Actual ID. Run replacement with mocked verified backup and assert the manual IDs and transaction remain while the resulting Actual import has the corrected rows and a zero report.

Add a second test that references the legacy account or category from a manual transaction and asserts `LegacyActualMappingError`; after the exception, assert the legacy and manual rows still exist unchanged.

- [ ] **Step 2: Run focused replacement tests to verify RED**

Run: `TEST_DATABASE_URL=postgresql+asyncpg://<user>@127.0.0.1:55432/finanse_test /opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py -k "replace_legacy_actual" -v`

Expected: FAIL because replacement mode does not exist.

- [ ] **Step 3: Implement one-transaction ownership proof, cleanup, and reimport**

Inside the existing session and advisory lock, derive legacy entity candidates from matching Actual transaction descriptions and parser legs. Reject missing, ambiguous, or pre-existing mappings that do not match the derived candidate; reject every candidate referenced by a non-Actual transaction. Mark only proven candidates `actual`, delete the specified user's `FinancialTransaction.source == "actual"` rows, Actual mappings, and `Account`/`Category` rows whose source is `actual`. Delete child categories before parents. Reuse the existing write pipeline and force `ensure_reconciled` before `db.commit`.

- [ ] **Step 4: Run focused replacement tests to verify GREEN**

Run the Step 2 command.

Expected: PASS.

### Task 5: Quality Gates And Operating Documentation

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Remove trailing whitespace**

Run `git diff --check`; repair every tracked-file whitespace failure using the repository formatter or a minimal patch.

- [ ] **Step 2: Run isolated migration and production-safety checks**

Run the actual DOM blob import only against `finanse_test` with `--execute --require-reconciled`; inspect `reconciliation.json` for zero account, category, and group differences. Do not pass `--replace-legacy-actual` against production.

- [ ] **Step 3: Run full quality gates**

Run `make VENV=/opt/finanse/backend/.venv/bin lint`, `make VENV=/opt/finanse/backend/.venv/bin typecheck`, `make VENV=/opt/finanse/backend/.venv/bin test`, `make VENV=/opt/finanse/backend/.venv/bin test-integration`, and `git diff --check`.

- [ ] **Step 4: Document only observed results**

Record test counts, isolated reconciliation result, the required production command, backup verification, rollback semantics, and the explicit fact that production correction was not run.

- [ ] **Step 5: Commit verified work**

```bash
git add backend docs
git commit -m "fix: zabezpiecz korektę importu Actual"
```
