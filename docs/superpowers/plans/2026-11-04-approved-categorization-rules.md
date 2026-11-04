# Approved Categorization Rules Implementation Plan (Stage 3A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans after approval, native inline TDD. Track the steps below and use one independent whole-change review at the end.

**Goal:** Apply an explicitly approved exact-description rule to a newly created, explicitly unclassified manual PLN expense, retaining payment identity and truthful rule provenance.

**Architecture:** Add per-user settings, versioned rules, assignment origin and a durable creation-event outbox. Existing category-only ledger logic becomes a private writer shared by human and approved-rule commands; Stage 2 manual state remains manual-only. The existing worker delivers event IDs, while PostgreSQL stores eligibility, claim/lease and terminal result.

**Tech Stack:** Existing FastAPI/Pydantic, async SQLAlchemy/PostgreSQL/Alembic, Redis/ARQ, React/TypeScript/TanStack Query. No new runtime packages or services.

**Spec:** `docs/superpowers/specs/2026-11-04-hybrid-categorization-design.md`, first independent step of the user-approved hybrid Stage 3 policy. Stage 3B LLM/proposals has a separate later plan.

## Approval and global constraints

The user approved this full plan at5e679b5 with “tak”, after approving the hybrid policy. Implementation is local on the existing isolated worktree; preserve unrelated Velo/Q7 files. “ok, działaj dalej” continues this acceptance, not provider activation, Stage3B, historical processing or a release.

**Execution status:** completed locally after one whole-review; account-history origin omission reproduced RED→GREEN. Final frozen-source gate (`sh_1a5f2a35a001VtfDN4s5439AGc`):1303backend/439frontend/lint/typesPASS, build/111E2E+1expectedskip/2extraoriginbrowserPASS; source/dist/migration hash verified. No production/provider/history action. Acceptance report: `docs/audits/2026-11-04-approved-categorization-rules-local.md`.

- No production migration/deployment, main merge/push, real LLM/OCR, provider activation or historical batch. Stage 3A has no provider adapter or LLM task at all.
- Rule auto-write only for new `source=manual`, booked, positive PLN expense; one account debit, one technical-placeholder credit, rate1 and source_amount==base_amount_pln. No Actual/mappings, pending, loan, FX/refund, document allocations, existing manual state or any assignment origin.
- Technical category is an explicit owned active expense category ID. Never infer from names, nulls, parents, source labels or absence of metadata alone. Target must be different from that ID.
- A rule must have current active approval for its exact normalized description, target path and technical category. No regex/contains/fuzzy, confidence-based writes or rule generation by AI.
- No inline automatic ledger mutation during creation. Only `create_transaction` may register a creation event, atomically with the source; changing rules/startup/description must not enroll old rows.
- `TransactionCategorizationState.source='manual'` and its constraint stay unchanged. Separate assignment origin must not fake human confirmation. Existing manual state protects without a backfill.
- Preserve account Posting ID and every mapped column, payment count, amounts, dates, source, FX and document/loan references. Category postings remain the sole amount source; sum stays zero.
- Receipt, category mutation, origin, audit and terminal event commit atomically. Redis is delivery only; duplicated/late messages and expired leases do not repeat a completed decision.
- Use owner-document mutex before policy/tree/ledger locks, no late account-row locks. Existing `update_account`, category deletion and manual protections must remain covered.
- SessionVersion/per-session QueryClient fences every UI intent/result. No optimistic rewrite or historical receipt installation into a new session.
- Configurable defaults are builder choices: matcher input max500chars; dispatch batch50, lease60seconds, max3attempts, retry delays10/60seconds and UI poll2seconds, in Settings/env—not hardcoded branches. Rules are disabled per user by default.

## Review Focus

1. A creation path can already hold account locks. Registration must not acquire later owner/tree locks or run apply inline; worker mutation occurs in another transaction (Task 2 deadlock/outbox tests).
2. PostgreSQL created_at is transaction-start time. An old row must not become newly eligible after enable/approval, and a rule approved after registration cannot replace the observed grant (Task 2 enrollment tests).
3. Automated provenance must not create manual state; a human correction must protect the transaction even if it returns to the placeholder category (Task 1 origin/race tests).
4. Rule pause/edit, target/category/account changes, manual confirmation or allocation while delivery is delayed must prevent the stale auto-write (Task 1/2 fencing tests).
5. A stale session/replayed receipt must not show old-owner rules or enable the wrong approval UI (Task 3 session/preview tests).

## File map

- New `backend/app/finance/rule_models.py`: settings/rule/origin ORM, with outbox model in `rule_event_models.py`; both imported for Base metadata and Alembic. No new mapped columns on FinancialTransaction/Posting; optional origin is a batched read projection (`rule_origin_reads.py`).
- New `rule_schemas.py`, `rule_policy.py`, `rule_router.py`: strict owner-scoped configuration/rule CRUD, normalization, preview/approval, receipts and epoch/target checks.
- Modify `categorization.py`, `categorization_context.py`, `categorization_schemas.py`: factor private category writer, add optional origin to opaque snapshot/context, retain manual behavior.
- New `rule_events.py`, `rule_worker.py`: creation registration, DB claim/lease/CAS, rule apply and delivery/recovery.
- Modify `transactions.py`, `worker.py`, `entities.py`, `config.py`, `.env.example` and `finance/router.py`: safe hook, worker registration, reference guards, configurable limits/routes.
- One additive migration after `2268bca97cb8`: four tables and explicit constraints/indexes only. Keep Stage 2 source constraint and all current financial rows unchanged.
- New tests in `backend/tests/test_finance/test_rule_policy.py`, `test_rule_events.py`, `test_rule_races.py`, `test_rule_migration.py`.
- New `frontend/src/api/categorizationRules.ts`, page `FinanceCategorizationSettings.tsx`, focused `components/finance/RuleEditor.tsx` and `RuleEventWatcher.tsx` with tests. Extend FinanceSettings/App routes, existing FinanceTabs with the small watcher, and optional origin in finance DTO/list/detail; no new daily tab until proposal queue3B. Read-only origin loading must be batched/selectin, no N+1 or new mapped transaction columns.
- New `frontend/e2e/categorization-rules.spec.ts`, plus existing finance/date/category regression suites.

## Task 1: Explicit policy, approval and truthful assignment origin

### Interfaces and data

`TransactionCategorizationSettings`: uniqueuser, uncategorized_category_id nullable RESTRICT FK, rules_enabled=false, version>0, Base timestamps. Enabling requires a category. Any settings edit increments version and audits old/new; disabling/clearing does not relabel or scan transactions.

`TransactionCategorizationRule`: owner, display_description, normalized_description_exact, target_category_id RESTRICT, state=draft/active/paused/retired, version, approved_version, approved_for_uncategorized_category_id, approved_target_sha256, approval_receipt_id, approved_at, Base fields. Active exactpattern unique per owner via partial unique index. Edits/pause/retire advance version; edits return draft. Active means stateactive and approved_version==version. Rule approval records a FinanceCommandReceipt snapshot; old receipts retain prior grant semantics after edits.

`TransactionCategorizationOrigin`: unique transaction dependent FK/CASCADE, owner, origin=manual/approved_rule, version, rule_id/version/approval_receipt_id nullable, assignment_sha256, Base fields. Rule origin requires all grant refs; manual clears current grant refs after audit. No amount mirror. Existing Stage 2 state is still an independent human-protection signal.
`Rule.approval_receipt_id` and `origin.approval_receipt_id` are RESTRICT FKs to finance_command_receipts.id. Origin additionally retains approval_snapshot_sha256; the immutable receipt JSON contains the reviewed rule/version, original and normalized pattern, markerID, target fields/path/hash, future-only scope, timestamp and real actor. Never edit a receipt or point a new rule version at the prior grant. Historical UI labels use this snapshot, not mutable rule fields. A persisted rule/origin never references a foreign owner's receipt.

- `GET/PATCH /api/finance/categorization/settings`; PATCH uses expected_version, uncategorized_category_id/rules_enabled, explicit `confirm_future_only=true` and Idempotency-Key. Context includes max description length and version, not a guess about which category to choose.
- `GET/POST /api/finance/categorization/rules`; create makes draft only. `PATCH /rules/{id}` edits to draft. `POST /rules/{id}/preview` is nonmutating and binds ruleversion, normalized pattern, markerID and complete target/ancestor fields.
- `POST /rules/{id}/approve` requires expected_version, preview_snapshot, `confirm_future_only=true`, Idempotency-Key. `POST /rules/{id}/pause|retire` requires version/key. No harddelete.
- Owner404, stale/conflicting approval409, invalid/missing/foreign/inactive category or wrong input422. Client cannot supply approved_by/source/origin/version increments.
- `normalize_rule_description(value: str) -> str`: NFKC/casefold/strip/whitespace collapse, nonempty/maxconfigured length. No truncation or free regex.
- `preview_rule(db, user_id, rule_id, expected_version) -> RulePreview` and `approve_rule(db, user_id, rule_id, request, *, idempotency_key) -> RuleResponse` operate under owner-document→category-tree→policy/rule→category locks. Settings changes use same protocol; no ledger locks for policy-only work.
- Private category writer returns the refreshed ledger without creating manual state/audit/receipt by itself. Existing human wrapper still writes Stage 2 manualstate and also manual origin. Rule wrapper later writes approved_rule origin, never Stage 2 manualstate or `confirmed=true` on a fabricated human request.
- `CategorizationContext` retains legacy source/version meaning and adds optional `assignment_origin` data; do not widen the manual-only source to pretend a rule is manual. Bump canonical opaque snapshot namespace to v2 and include origin; existing clients refresh on409. No fingerprintActual change.

### TDD steps

- [x] Write `test_marker_is_explicit_and_never_name_inferred`: unset/off→no eligibility, exact ID only, active own expense validation, root descendants not inferred. Write strict/spoofed-fields/owner/real-session-CSRF tests for each mutation family.
- [x] Write `test_rule_approval_binds_normalized_exact_pattern_and_target`: draft cannot auto-apply; preview no writes; approved then edit/pause/target rename/archive is no longer the old grant; duplicate active pattern rejects, no substring/fuzzy match. Include Unicode/case/whitespace and overlong input (reject, do not truncate).
- [x] Write `test_manual_origin_overrides_rule_without_faking_approval`: Stage2 behavior unchanged, legacy manualstate protects without origin, rule-origin→human same-category confirmation creates manualstate, existing human splits preserve account/date/allocations and origin history. Test wrong-owner grant refs.
- [x] Run guarded focused tests, observe RED at real behavior (not merely import error).
- [x] Implement data/DTO/policy/private writer and reference guards. `delete_category` must reject settings/rule/origin references under the existing tree lock; do not add owner-document lock after tree. Refresh policy/category state under locks and preserve established account-edit serialization.
- [x] Run focused policy/categorization/date/Actual/bill/account tests, ruff/mypy; expect PASS. Commit verified focused work only after lint/types/tests for both affected layers as appropriate, or keep uncommitted until whole-step gate if interfaces are still moving.

## Task 2: Creation-only outbox and approved-rule worker

### Interfaces and data

`TransactionRuleEvent`: unique transaction FK/CASCADE, owner, observed settingsversion, observed ruleID/version (nullable for no-match), source contextsha, registered_at from statement clock, status=ready/processing/applied/skipped/failed, reasoncode, attempts, lease token/deadline, next_attempt_at, resultreceipt ID, Base fields. A no-match/ambiguous event is terminalskipped, never re-enrolled by a later rule. Creating while off creates no ready event. Event uniqueness prevents duplicate hook calls from creating additional opportunities.
The observed ruleID/version are opaque snapshot values, NOT rule/receipt FKs. Enrollment must not implicitly acquire a late rule row lock through a FK while already holding source account/category locks. Only the event→new transaction FK is required there. The worker treats these values as untrusted references and proves current owned grant + immutable approval receipt before writing; a missing rule gives skipped/rule_changed, not authority to reconstruct one.

- `record_new_expense_event(db: AsyncSession, user_id: UUID, transaction: FinancialTransaction) -> UUID | None` is called only from a newly created eligible manual expense after the final explicit selectinload of validated persisted postings, just before create_transaction returns. No async lazy relationship reads or incidental autoflush during canonicalization. It writes an event in the caller transaction, never commits, takes no owner/tree/account locks, and performs no broker/network/ledger mutation.
- Enrollment reads settings plus currently approved exact rule in one SQL statement snapshot, storing exactly the observed references and version. Newness is the creation-path event, not booking/purchase date, background discovery or naive created_at comparison. No public endpoint can register an arbitrary existing transaction by ID.
- `claim_rule_event(db, event_id) -> RuleLease | None` claims with short rowlock/CAS and commits before any ledger operation. `process_rule_event(ctx, event_id) -> RuleEventResult` rechecks current lease/grant/input and writes rule decision using stable FinanceCommandReceipt action/key derived from eventID.
- Processing order: receipt→owner-document→category-tree→eventrow→parent/postings→manualstate/origin→settings/rule→categories. Settings/rule edits share owner mutex; claim only eventrow and commits before waiting for owner/tree/ledger locks. Existing category-only mutations keep category-tree before category rows and never add owner-document after tree. No account-row locks.
- Recheck current settings version/enabled/category, exact same active approvedrule/version and markerID/targetsha, source inputsha, absence of manualstate/origin, ledger ownership/shape/PLN/noActual/loan/allocations. Stale/missing source or policy gives terminalskip, no substitute rule or ledger/audit apply.
  Explicitly recheck the current marker category under tree/category locks: same owner, is_active, typeexpense, and its ID equals the sole placeholder Posting. Archive/type/ownership changes can invalidate the marker without changing settingsversion; yield skipped/marker_invalid.
- A successful auto decision writes a single existing target with the full unchanged amount, approved_rule origin, audit, receipt and applied event atomically. Repeated delivery returns terminal outcome; stale lease token cannot write. Rule origin includes the immutable approval receipt, not only a mutable rule name.
- Dispatcher/recovery queries only event rows. Redis delivery may duplicate/fail; enqueue failure never increments attempts. Only a successful lease claim increments attempts. Recovery considers ready or expired nonterminal processing rows; applied/skipped/failed never re-enter dispatch. At the configured attempt ceiling, persist terminalfailed/attempts_exhausted with no ledger write.
- Successful apply commits ledger/origin/audit/receipt/eventapplied together. Writer/audit failure rolls all of those back; `record_rule_event_failure(db, event_id, expected_lease_token, safe_code)` then runs in a SEPARATE short transaction, CAS on still-owned nonterminal lease, to persist ready+next_attempt_at or failed. If the DB is unavailable, lease expiry permits later recovery. A rollback alone cannot persist failed. If lease was lost or event became terminal, failure handling is a no-op and cannot overwrite another result.
- Persisted safe skip/failure codes: no_match, ambiguous, settings_changed, rule_changed, target_changed, marker_invalid, input_changed, manual_protected, ledger_protected, source_missing, write_failed, attempts_exhausted. `lease_lost` is a handler result, not permission to terminalize a row now owned by another worker. No raw SQL/exception/description in public reason fields.

### TDD steps

- [x] Write `test_only_creation_enrolls_observed_approval`: pre-enable/old transactions untouched; rule approved later cannot apply to no-match event; source dates may be old without being historical discovery; concurrent approval is bound to the observed committed grant, not transaction-start timestamp.
- [x] Write `test_record_event_never_takes_late_finance_locks`: creation paths retain lock order, including implicit FK locks; overlap a source creation holding category/account refs with a worker holding the approved rule row and prove enrollment commits without a rule FK wait. Explicit-loaded input cannot trigger MissingGreenlet. Broker offline/rollback/duplicate hook or delivery never loses or duplicates payment; include document_payment/scheduled/Actual exclusions.
- [x] Write `test_rule_job_writes_origin_without_manualstate`: exact new unclassified expense10000 changes one category, account Posting mapped columns/date/source unchanged, signed sumzero, no fabricated human approval, correct receipt/audit/grant lineage. New manual actual-category selection or split never enters job.
- [x] Write deterministic concurrent tests: pause/edit/settings disable/target or account change/manual confirm/allocation admitted before job→skip; job admitted first→later edit waits. Expired/stolen lease and repeated delivery cannot apply twice. Inject audit failure and broker failure, verify rollback/recovery.
  Add marker archive without settingsversion change, old receipt retained after rule edit, and failure CAS versus stolen lease. Prove claim-only attempt accounting, enqueue-no-attempt, audit rollback then separate failure transaction, and terminal states never re-dispatch.
- [x] Run guarded tests RED, implement events/worker/hook and existing ARQ handler/dispatcher integration, then focused GREEN including Stage2 races/Actual/date/bill/account suites.
- [x] Generate `/migration "approved categorization rules"` equivalent only in newly owned finanse_test schema upgraded to2268. Inspect four-table additive DDL; keep prior manual check, transaction/posting columns and all old rows/indexes unchanged, no backfill/events for old ledger.
- [x] Test actual isolated upgrade/retention, empty rollback/re-upgrade and populated downgrade refusal under all new-table DDL locks. No table with policy/origin/events is dropped to ease rollback. No production migrate.

## Task 3: Settings and rule review UI

**Interfaces:** use canonical `/settings/finances/categorization` (execution ruling: retain existing settings layout, not the originally transposed path), with session-scoped `useCategorizationSettings`, `useCategorizationRules`, receipt-keyed mutations and preview. Server supplies limit/version/eligibility messages; frontend does not infer eligibility from names or confidence. Origin display reads optional assignment_origin from Task1.
`GET /api/finance/categorization/events?status=active` returns bounded owner-scoped public ID/transactionID/status/safe reason and poll_after_ms. It reads only the event table and never claims/runs jobs or discovers ledger history. FinanceTabs watcher polls only while active events exist; a successful event-list read/terminal transition invalidates ledger reads, never its own query key, so there is no empty polling loop. New-transaction mutation also invalidates this watcher. Optional assignment_origin in TransactionResponse is read-only, bulk/selectin loaded and uses the immutable approval label. CategorizationContext may expose last_event status/reason for diagnosis without including mutable job state in the ledger token.

- [x] Write failing UI tests: explicit marker selection, rules initially off, future-only confirmation, no historical-run button, draft→preview→approve, exact original/normalized description and full target path, edit/pause invalidates old preview,409 retains fields but requires refresh.
- [x] Write failing session/receipt tests: delayed old-owner result does not invalidate/install new-session rules; same-session auth refresh retains editor; uncertain retry preserves key; changed intent generates new key/preview.
  Test pending→terminal invalidates finance even if apply finished before the first watcher read, while empty state does not keep polling; no per-row query or new mapped financial column. A paused/edited rule name cannot rewrite a historical origin label.
- [x] Implement focused settings page/editor using existing CategoryPicker/Dialog/style, add route/settingsnav, explain source limitations and why a rule needs reapproval. Separate manual/rule origin labels; preserve existing category split editing.
- [x] Add mockedE2E375/1440 for settings/rule approval and source origin/manual override, a11y/keyboard/nooverflow. Mock server and block provider/backend traffic; real ledger invariants remain covered by backend tests.
- [x] Run fullfrontend/lint/tsc/build and focusedE2E; expect PASS. No AI generation button or provider activation in3A.

## Task 4: Whole-step acceptance and local handoff

- [x] One fresh-context whole-change review against spec/ReviewFocus; verify/fix Critical/Important RED→GREEN in one pass, record remaining minors. No per-task reviewer loop or live provider/production test.
- [x] Freeze source; full guarded `/test`, `/lint`, `/typecheck`, fresh build/fullE2E and migration retention with exactsource/dist/revision proof. Run public PostgreSQL suites serially.
- [x] Update CHANGELOG/TASKS/JOURNAL and audit, commit only own verified files. Stage3A done locally is not fullStage3 or deployment; 3B proposals/LLM remains pending. Preserve branch/worktree/Velo/Q7.

## Builder decisions and self-review

Read-only buildercheck `ses_e5aa56365ffeFvTF8OHW4I6XXL` found no user-only blocker and validated the written spec/plan after recon. Its five required clarifications are incorporated: separate failure transaction, explicit-loaded enrollment, current marker recheck, immutable receipt FK/hash evidence and exact retry accounting. The source insert also avoids implicit rule FK locks. Exact matcher, noActual auto-write, per-user explicitmarker and separate origin are builder defaults; user approved the hybrid policy. Creation outbox replaces unsafe inline mutation/naive timestamp newness. Optional origin fields preserve manual DTO/source semantics instead of widening the manual-state constraint.

Tasks1→2 share grant/normalization/privatewriter and origin; Tasks1/2→3 share settings/rule/context DTOs and opaque preview tokens. Version and lock order are specified together to avoid hidden authorization bypass. FullStage3 LLM batches/provider quota/new-category proposals are in the design but explicitly outside this plan, not marked implemented or silently omitted.
