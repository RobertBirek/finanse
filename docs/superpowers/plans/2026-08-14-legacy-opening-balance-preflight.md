# Legacy Opening Balance Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permit only recognized synthetic Actual opening balances during legacy replacement preflight while rejecting every other unmatched transaction.

**Architecture:** `replace_legacy_actual_data` keeps the existing Actual-ID provenance gate. For a nonmatching description it loads that transaction's postings and accepts only the documented two-sided, same-account, category-free, balanced BO shape. No schema or command-line behavior changes.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, PostgreSQL, pytest/pytest-asyncio.

---

## File Structure

- Modify: `backend/scripts/migrate_actual.py` - recognize the narrow synthetic BO exception in replacement preflight.
- Modify: `backend/tests/test_finance/test_actual_import.py` - unit coverage for accepted and rejected BO-like transactions.
- Modify: `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md` - record verified outcome and production-command exclusion.

### Task 1: Prove The Replacement Preflight Is Fail Closed

**Files:**
- Test: `backend/tests/test_finance/test_actual_import.py`

- [x] **Step 1: Write failing unit tests**

Add parametrized `SimpleNamespace` postings to exercise the intended predicate.
Accept an Actual-sourced `[BO] Bilans otwarcia` with two category-free postings
for one account and equal debit/credit base amounts. Reject a lookalike
description, a manual-source record, imbalanced amounts, a category, and two
different accounts.

- [x] **Step 2: Run the focused test to verify RED**

Run:

```bash
/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py::TestLegacyOpeningBalancePreflight -v
```

Observed: all cases failed with `AttributeError` because the predicate did not
exist.

### Task 2: Recognize Only The Exact Legacy BO Shape

**Files:**
- Modify: `backend/scripts/migrate_actual.py`
- Test: `backend/tests/test_finance/test_actual_import.py`

- [x] **Step 1: Implement the minimal predicate**

Add a private predicate receiving source, description, and loaded postings.
Return `False` unless the description starts with `[BO] Bilans otwarcia`; then
return `True` only for exactly two postings with the same non-null `account_id`,
null `category_id`, one debit and one credit direction, and equal
`base_amount_pln`. Use it only as the fallback when an Actual-description match
is absent from `blob_transaction_ids`.

- [x] **Step 2: Run the focused test to verify GREEN**

Run the Task 1 command.

Observed: all six BO-focused cases pass.

- [x] **Step 3: Run regression coverage**

Run:

```bash
/opt/finanse/backend/.venv/bin/pytest tests/test_finance/test_actual_import.py -v
```

Observed: `38 passed, 11 skipped` before the final focused-test expansion.

### Task 3: Verify And Document

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/TASKS.md`
- Modify: `docs/JOURNAL.md`

- [x] **Step 1: Run static and focused verification**

Run:

```bash
/opt/finanse/backend/.venv/bin/ruff check scripts/migrate_actual.py tests/test_finance/test_actual_import.py
/opt/finanse/backend/.venv/bin/mypy scripts/migrate_actual.py
git diff --check
```

Expected: each command exits with code 0.

- [x] **Step 2: Record observed results**

Update the session documentation with the added exception, its fail-closed
shape constraints, verification output, and confirmation that no production
replacement command was run.

- [ ] **Step 3: Commit merge-ready work**

```bash
git add backend docs
```
