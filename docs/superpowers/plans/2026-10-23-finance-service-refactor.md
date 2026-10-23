# Finance service refactor implementation plan

Approved scope: conversation audit and explicit user approval, 2026-10-23.
Goal: separate finance responsibilities without changing ledger/API behavior.
Base: 11a331a. Existing harness-managed linked worktree is retained.

## Constraints and interfaces
- No migrations, dependencies, deploy, production access or behavior fixes.
- PostgreSQL/ownership checks, rounding, posting signs, pending semantics,
  ordering, flushes, SQL predicates and FOR UPDATE locks stay unchanged.
- service.py remains explicit compatibility exports for public finance functions.
- Leaf modules never import service.py: transactions uses queries/validation;
  reporting uses queries; budgets uses entities; cashflow uses budgets/transactions.
- Shared dates.py owns existing date helpers; no clock semantics change.
- Existing test monkeypatches target the new implementation owner, not facade aliases.
  Public API imports remain unchanged; private patch locations are not a public API.

## Tasks
- [x] 1. Baseline finance tests and contract tests: public facade exports/signatures,
  new module entrypoints. Preserve existing integration behavior tests.
- [x] 2. Move transaction/exchange mutations unchanged to transactions.py;
  move date helpers unchanged to dates.py; update exchange test patch targets.
- [x] 3. Move financial/category summaries unchanged to reporting.py.
- [x] 4. Move budget CRUD/status to budgets.py; extract category descendants
  as a pure function with branching/empty/cycle characterization tests.
- [x] 5. Move schedule/settings/forecast/confirmation to cashflow.py; retain locks
  and change only internal import ownership. Update private clock test patch.
- [x] 6. Verify service facade <100 lines, public compatibility, no leaf->facade
  cycles; run full backend/frontend gates, independent review, docs and commit.

## Verification
Use .opencode command definitions /test, /lint, /typecheck with the explicit safe
local finanse_test DSN. Tests run through /opt/finanse/backend/.venv; frontend
already has installed dependencies. No production environment is loaded.
Before each extraction: new entrypoint contract test RED (module absent).
After each extraction: focused finance behavior tests and facade contract GREEN.
Final gate: full pytest, vitest, Ruff/mypy/ESLint/tsc and git diff --check.

## Review focus
Public function signatures and defaults; local date monkeypatch behavior; NBP
provider cleanup/rounding; cashflow confirmation locking/idempotence; no query
predicate/sign changes, extra commits or transaction boundaries.

## Results
Baseline207 PASS; full backend642 PASS (8 proxy deselected), frontend194 PASS;
Ruff/mypy/ESLint/tsc/diff PASS. Independent review: no blocking defects.
Facade63 lines, 27 functions AST-identical; remaining function only extracts traversal.
Private collaborator monkeypatches target implementation owners. Optional followups:
query/entity alias contract assertions and documentation for external private helpers.
No migrations, merge, push or production deployment performed for this refactor.
