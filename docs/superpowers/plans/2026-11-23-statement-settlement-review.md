# Statement Settlement Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Develop and verify each task before moving on.

**Goal:** Prepare one read-only review of an existing statement and post only explicitly selected rows in one authorized command.

**Architecture:** Read owner-scoped source and ledger facts, use deterministic rules to suggest links and categories, and fingerprint the review. At confirmation, reacquire the existing import/account locks, rebuild the review, and reuse the existing decision, pricing and financial commit path in a single savepoint and durable receipt.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React, TanStack Query and Vitest.

**Spec:** Approved conversation (2026-11-23): one row to one transaction, no aggregation, no amount-only matching, one explicit confirmation, leave existing transactions and import decisions alone.

## Global Constraints

- No production access, application data changes, or deployments during implementation.
- No migrations, external AI, automatic posting, or implicit acknowledgement of mismatched opening balance.
- First slice: one explicitly chosen PLN account per review; unsupported currencies and complex movements remain open. Preserve the existing per-row workflow.
- No joining/summing movement rows or reusing one transaction for two selected rows. No guessing the treatment of cash withdrawals, related fees, repayments or installment principal.
- A same-amount candidate, ambiguity or relevant ledger drift must never silently result in a new transaction.

## Review Focus

- Competing proposed links to the same existing transaction: both stay open.
- Existing evidence and saved decisions remain unchanged; possible duplicate is never presented as new.
- Velo purchases and explicitly recognized interest may be proposed; cash, card repayment, uncertain BLIK, fees and principal remain open.
- Outdated review, unauthorized account, duplicate row, invalid category, failed commit and retry: no partial writes.
- UI review does not mutate, and a failure never reports a successful confirmation.

### Task 1: Read-only owner-scoped review and one atomic confirmation

- [x] Add synthetic tests for strict link signals, Velo movement classification, collision, and non-inference of a category.
- [x] Implement `settlement_policy.py`, `settlement_schemas.py`, `settlement.py`, DTOs and authenticated `GET/POST /finance/imports/{batch_id}/settlement`. The GET accepts `account_id`; the POST accepts fingerprint, distinct row IDs, optional category IDs and required acknowledgements, not ledger data.
- [x] Factor an internal preparation callback into the existing commit flow. Preserve the financial command key, import evidence, balance invariants, and no partial saves on conflict.
- [x] Add integration tests for snapshot staleness, replay, owner isolation, and a repeated bank reference across two imports.
- [ ] Run PostgreSQL integration tests in separately approved CI; offline collection does not execute them.

### Task 2: Review in the existing statement page

- [x] Add tests for grouping, explicit selection, inline category, no write on preview and repeat-safe confirmation error.
- [x] Add a focused `StatementSettlementReview` component and guarded API hooks. Keep manual decisions available in the existing pane.
- [x] Run lint, typecheck, offline collection, frontend tests and build. Address the independent review's duplicate-target finding and update session docs; no production changes.
