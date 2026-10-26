# Finance UI Implementation Plan

> **For agentic workers:** Use executing-plans with independent backend/frontend units
> and one fresh whole-branch review. Track evidence below; no production publication.

**Goal:** Replace finance UX with approved mockup while preserving owned ledger/history.
**Architecture:** Existing modular monolith and API, additive schema migration, React pages
and shared semantic theme components. Backend owns all monetary aggregates.
**Tech Stack:** Existing Python/FastAPI/PostgreSQL + React/TS/TanStack Query/Tailwind.
**Spec:** `docs/superpowers/specs/2026-10-26-finance-ui-design.md`.

## Global Constraints

- Spec's constraints and API contract apply to each task. No production DB or deploy.
- Root checkout's uncommitted mockup/docs copied into this worktree without modifying root.
- Existing operations remain usable, without replacing ledger history or reimporting Actual.

## Review Focus

- Parent + child budgets: summary excludes double counting, sibling branches remain included.
- Deep/archived category branches: no missing amounts/children/cycles or ownership leakage.
- FX and transfers: source vs PLN clearly labelled; zero-sum ledger is not displayed as amount.
- Optional bank fields: omitted vs null PATCH; valid normalization, access and PII boundaries.
- Existing routes, mobile forms, history/detail restoration: no trapped dialog or lost navigation.

## Tasks

- [x] Task 1 — Baseline + execution record: isolated workspace, tests, spec, contracts.
- [x] Task 2 — Backend accounts: schema validators + nullable migration + source balances.
  Tests first: metadata create/PATCH/null/IBAN/BIC/ownership, source amounts for FX,
  migration preserving metadata-free accounts, no sensitive advisor context.
- [x] Task 3 — Backend hierarchy/reporting: deep rollup and subtree search with compatibility.
  Tests first: parent direct + grandchild amounts exactly once, archived parents,
  default exact search and include_descendants, transfer exclusion, owned scope.
- [x] Task 4 — Budget aggregate: highest budget ancestors only, cashflow uses same totals.
  Tests first: parent/child and sibling cases, independent child-only budget, unchanged items.
- [x] Task 5 — React shell/theme/settings: approved visual pattern, accessible responsive
  navigation, route redirects, metadata form with optional patch semantics.
  Tests first: routing/config placement/theme persistence/validation/no create UI in daily views.
- [x] Task 6 — Category editor/pickers: shared tree paths, expand/collapse, create/reparent,
  inactive ancestors visible. Tests first for 3+ levels, cycles, inactive descendants.
- [x] Task 7 — Finance pages: real overview/forecast/budget/transactions/reports, no mock values.
  Tests first for source/PLN display, URL filters, detail restore, budget drilldown, error/retry.
- [x] Task 8 — Integration: full tests/lint/types/build, local browser fixtures + isolated API
  checks, screenshots responsive 320/375/768/1440 and fresh review, fix blockers, docs.

## Evidence / rulings

- Task 1: frontend baseline 194 PASS. Backend initial command exceeded 120s, rerunning
  full baseline with longer limit; timeout is not a test failure.
- Ruling: independent units can run concurrently on non-overlapping `backend/` and
  `frontend/` paths using the explicit spec API contract; coordinator owns docs and verification.
- Ruling: use existing installed dependencies via ignored symlinks, no lockfile changes.
- Ruling: maintain exact-match category search by default; UI opts into descendant search.
- Ruling: no cashflow semantic changes beyond approved overlapping-budget aggregate;
  current payday/horizon/pending/PLN confirmation validations stay unchanged.
- Baseline follow-up: backend 777 PASS + 1 environmental failure (missing TEST_DATABASE_URL
  in the legacy session migration test). That unchanged test rerun with the explicit safe
  test DSN passed; no production code change was needed.
- Ruling: added backend `FinancialSummary.balance_all_pln` and `balance_budget_pln` so
  the new balance-scope selector does not sum money in the browser. The balances are
  current book values, independent of the report period; old fields retained.
- Ruling: budget page's old "unbudgeted" frontend filter did not account for deep branches.
  Show full server-supplied category spending under an accurate heading instead of
  deriving a new financial rollup in React. A separate unbudgeted-only backend report
  can be introduced later if needed; all financial data remains available.
- Fixes in coordinator's review: sidebar still needed every module after rail removal;
  migration initially branched from an obsolete revision; corrected predecessor to c7
  with RED→GREEN single-head test and synthetic migration preservation test.
- Interim gate: backend full 786 PASS / 8 proxy deselected / 2 known dependency warnings.
  New migration and protocol tests have separate RED→GREEN evidence; full final rerun pending.
- Subagent usage limits interrupted work. Coordinator resumed integration and verification;
  no partial agent report was treated as proof of completion. Fresh reviewer requested.
- Final fresh-context review returned no findings. Subsequent own/browser checks fixed
  active-settings/archival-controls contrast, retained bank + account name in chips,
  hid bank fields for cash, and kept report drilldown on budget accounts (new additive
  budget_accounts_only flag, exact same-leg/owned scope). Each behavior has regression coverage.
- Ruling: budget-account-only report drilldown is an optional filter rather than a change
  to ordinary search: normal history must continue to include off-budget accounts.
  Wrong choice here would hide valid history or make report details disagree with totals.
- Final gate: backend790 PASS (8 proxy deselected,2 known dependency warnings),
  frontend220 PASS, E2E31 PASS+1 intentional desktop skip; Ruff/mypy/ESLint/tsc/build
  and single Alembic head PASS. Responsive browser checks include 320/375/768/1440;
  fixtures only, no production calls. Worktree retained for user evaluation, no push/merge/deploy.
