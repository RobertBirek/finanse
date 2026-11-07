# Credit cards and card installment plans — implementation

Approved in chat: existing VELOBANK - karta, PLN33600 limit, APR14.50%, max57
interest-free days, cycle18–17, nominal repayment day12 with actual statement
dates authoritative. All old Komfort plans closed; new plans each have their own
APR/fees and estimated schedule replaceable by a bank schedule; partial/early
repayment, no duplicate debt/expense. User approved implementation and a dedicated
ephemeral offline PostgreSQL with no published ports, removed after acceptance.

Goal: integrate card metadata/statements/plans with the existing double-entry
ledger, never invent postings from estimates. FastAPI/SQLAlchemy/PostgreSQL,
React/TanStackQuery; same account, not another balance store.

## Tasks / verification

- [x] 1. Pure Decimal calculations and validated contracts (test-first): available
  limit, posted debt/pending reservations/overpayment/overlimit, equal-principal
  monthly estimates (explicit convention, not bank-exact), per-plan APR/fees,
  calendar month clamping; optional explicitly selected daily interest estimate.
  Files credit_card_math.py, credit_card_schemas.py; tests/test_finance/test_credit_card_math.py.
- [x] 2. Additive models/migration + owned services/API: CreditCard profile,
  CardStatement, CardPlan, CardInstallment, CardAllocation, CardCharge. Dedicated
  credit_card_models.py/credit_cards.py/credit_card_router.py; register with finance
  models/router. Model-level amount/date/uniqueness checks. Account lock prevents
  currency/type changes/delete once configured. Audit mutations. All data user-owned.
  RED→GREEN integration tests on dedicated PG, including foreign IDs, duplicate
  retries, plan replacement, payment over-allocation and safe mutations.
- [x] 3. Connect repayments/charges/refunds and immutable linked ledger records.
  Source spending/payout is an existing posted card debit, plans are classification
  of its principal (never another debt). New lending first needs a real transfer.
  Payment allocations link existing posted PLN transfers into the card; per-transfer
  caps independently for statement and plan axes, because those describe the same
  cash flow, never create additional postings. Per-plan principal cannot overpay.
  Booked charges use ordinary double-entry services with scoped trusted reversal
  support for expense corrections with reversed postings (not income), explicit idempotency, optional existing
  entry linking (no second booking). Guard linked tx deletion/date/pending changes
  including explicit transaction date editor. Test ledger sum, reporting net costs,
  unchanged spending when creating plans/schedules/allocations, root ownership.
- [x] 4. React card screen, account link, typed query/mutations: profile setup/edit,
  balances, statement entry/reconciliation and payment link, independent plan APR,
  generated estimated rows and bank schedule replacement, allocations/early payoff,
  charges and corrections + existing transaction linking. Loading/error/empty and
  mutation errors retained, no stale account data; fit existing dark UI. Vitest RED→GREEN.
- [x] 5. Full backend/frontend tests + lint/types/build, migration upgrade/empty
  downgrade/retention guard on populated tables, one fresh-context read-only review,
  fixes via TDD, docs and local commits. No push/merge/deploy/production setup.

## Decisions / constraints

- Money integer minor units, Decimal rates (not float), API safe integer bound.
- Only PLN initially (matches the requested account); reject other currencies.
- Card debt = negative posted ledger balance as of date; pending debits reserve
  additional limit and pending credits don't release it. Available = max(0,limit
  minus debt minus reservations); overpayment shown separately, not guessed bank credit.
- Plans have principal already represented in ledger, not additionally summed into
  debt. Reject a plan unless its principal is covered by an owned posted debit and
  all plans on that debit together fit. Historical Velo statements expose separate
  unmatured capital; don't infer that from header debt or silently import it. User
  confirms no active legacy plans. Bank discrepancies remain explicit, not balanced
  with fabricated postings. UI explains this representation for future plans.
- 57 days is conditional max, not a per-transaction exemption. Without tariff and
  allocation rules do not promise exact revolving interest. Explicit simple daily
  estimate is labelled, never journaled. Statement balance/minimum/due are bank facts.
- Closed plans derive from fully allocated principal, not a status toggle that
  hides debt. Earlier payoff allocates existing transfer principal; no future
  estimated interest is recognized as an actual cost.
- Schedule metadata does not recognize costs; bank schedule replacement preserves
  original principal and cannot overwrite a paid plan. Store schedule kind/version.
- Idempotency keys are stored with exact request payload; identical retry returns
  same record; changed payload conflicts. Transactions remain guarded until links
  removed. No automatic posting/AI/provider or downloading private files to repo.
- No slash-command tool is exposed; use the checked-in workflow commands with this
  worktree/venv instead of hardcoded main. Migration autogenerate only against the
  newly owned test database, never production. No destructive migration of old tables.

Review focus: pending credits incorrectly free limit; original principal counted
twice on conversion; double allocations racing; refunds treated as new income;
historical statement mistaken for current balance. Pin all five in tests.
