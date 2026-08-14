# Actual Corrective Replacement - Design

Date: 2026-08-14
Status: approved for implementation and isolated verification

## Problem

Category reconciliation currently derives Actual's expected category totals by
calling `build_pa_postings`. A defect in import posting construction can
therefore affect both sides of the comparison and falsely make the report
reconcile. The report also omits category-group totals.

The original production import predates account/category provenance. Its
transaction rows have `source='actual'`, but its accounts and categories cannot
be safely deleted by name. A replacement must not alter manually created data.

## Goals

- Derive expected Actual category totals directly from parsed transaction legs
  and verified FX quotes, independently of `build_pa_postings`.
- Reconcile both leaf categories and Actual category groups; any mismatch or
  import error must fail closed.
- Persist `source` provenance for accounts and categories, with `manual` as the
  default and `actual` for importer-created entities.
- Provide an explicit corrective mode that backs up and verifies PostgreSQL
  before changing data, replaces only proven Actual data for one user, imports
  the DOM blob, and commits only after a zero reconciliation report.

## Provenance

`Account.source` and `Category.source` are non-null strings. Existing rows
migrate to `manual`; new Actual imports set `actual`. This is intentionally
conservative: no existing row gains Actual provenance merely because its name
matches the blob.

Corrective mode identifies legacy account and category candidates from Actual
transactions whose descriptions contain an Actual identifier present in the
provided DOM blob. It accepts a candidate only when its transaction-leg evidence
is unique. Before deletion it rejects any candidate referenced by a transaction
whose `source` is not `actual`. It also rejects a mapped entity without matching
legacy evidence. This check is performed in the replacement transaction, before
any delete. Proven candidates are marked `actual` only within that transaction,
then removed by the same `source='actual'` predicates. An exception rolls back
the marking and every deletion.

## Reconciliation

The expected-category calculator iterates parser transaction legs directly. For
each category leg it validates the account/category mapping and derives the
signed PLN value using the verified `NbpRate`; it does not construct a
`PostingCreate`. A rejected transaction records an import error and contributes
no expected amount.

Leaf-category totals are reconciled with category-only PA postings. Group totals
are the sum of their direct imported children on each side. `ReconciliationReport`
serializes `category_groups` separately and `is_reconciled` requires every
account, leaf category, group, and import-error check to pass.

## Corrective Command

The mode is enabled only by all of:

```text
--execute --require-reconciled --replace-legacy-actual --backup-path PATH
```

It cannot be combined with `--dry-run`. `PATH` must not already exist and its
parent must exist. Before a write session starts, the command runs `pg_dump` in
custom format to a temporary sibling file, verifies it using `pg_restore --list`,
sets owner-only file permissions, and atomically renames it to `PATH`. Failure
to create or verify the backup prevents any database work.

After the backup, the command opens one database transaction. It locks the
user's Actual import key, proves legacy ownership, rejects manual references,
deletes that user's `source='actual'` financial transactions (their postings
cascade), maps, accounts, and categories, then imports the supplied blob. The
existing reconciliation gate runs before `commit`; a non-zero report raises and
rolls back the entire transaction. The command never deletes manual
transactions, accounts, categories, or their postings.

## Recovery

If backup creation fails, no write session is opened. If cleanup, import, or
reconciliation fails, PostgreSQL rolls back the replacement transaction and the
verified backup remains unchanged. If a completed correction later requires a
rollback, an operator restores the verified custom-format backup with
`pg_restore` while the application is stopped; this restores the whole database,
not an unsafe partial subset.

## Acceptance Criteria

- A regression in `build_pa_postings` cannot make expected category totals
  reconcile.
- Reconciliation JSON and text include zero-difference category-group totals.
- A category or group mismatch, missing mapping, missing FX quote, or import
  error makes `--require-reconciled` fail before commit.
- New importer accounts/categories have `source='actual'`; manually created
  rows retain `source='manual'`.
- Replacement mode requires every explicit safety flag and a newly verified
  backup.
- Replacement rejects ambiguous legacy provenance and any manual reference.
- Replacement changes only the specified user's Actual data and commits only a
  fully reconciled import.
