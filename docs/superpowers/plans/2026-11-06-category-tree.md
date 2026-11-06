# Category Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przygotować przetestowane, kontrolowane narzędzie i procedurę zmiany zatwierdzonego drzewa kategorii, a produkcyjne wykonanie pozostawić za osobną bramką zgody.

**Architecture:** Mały operator-only CLI używa istniejących serwisów kategorii, audytu i trwałego `FinanceCommandReceipt`; bez nowych endpointów, modeli, migracji lub interfejsu. Czysty kompilator mapowania, właścicielski preflight READ ONLY i atomowy APPLY są oddzielone; wszystkie dane osobiste pozostają w prywatnym pakiecie, nie w kodzie. PostgreSQL jest źródłem stanu i wyniku operacji, pliki są wyłącznie zatwierdzonym wejściem/dowodem.

**Tech Stack:** Python 3.12+, Pydantic v2, SQLAlchemy async, PostgreSQL 16, istniejące pytest/ruff/mypy, wersjonowany runtime Docker bez zmiany zależności.

**Spec:** `docs/superpowers/specs/2026-11-06-category-tree-design.md` oraz zatwierdzony prywatny `proposal-private.md` i `mapping-private.json` w `/opt/finanse/webapp/category-designs/2026-11-06/`.

## Global Constraints

- „Żadnych scaleń, usunięć, dezaktywacji ani zmian typu”. Zachowane wszystkie oryginalne 65 ID.
- „14 nowych węzłów expense (w tym rodzice, rodzina i kategoria techniczna), łącznie 79 węzłów: 73 expense, 6 income”.
- „Kwoty, waluty, kursy, daty, salda, źródło Actual, IDs i powiązania ledgeru muszą pozostać bez zmian”.
- „Żadnego przepisywania postings lub masowego przypisywania kategorii transakcjom”.
- „Maksymalnie dwa poziomy, nie dodawać spekulatywnych pustych liści”.
- „Nie tworzymy kont, sald otwarcia, projektów, kontaktów ani rozdzielania abonamentów”.
- „Jej utworzenie nie oznacza wyboru jako marker, włączenia reguł, zgody na eksport AI lub uruchomienia historii”.
- Prywatna taksonomia/imiona/UUID/kwoty nie trafiają do Git, stdout lub zdalnych usług; brak modeli/OCR/importu w narzędziu.
- Zgoda na projekt i przygotowanie planu NIE upoważnia do implementacji planu lub produkcyjnego APPLY. Te dwa etapy mają osobne potwierdzenia.
- Import z Actual dla tego właściciela został jawnie zakończony. Importer i `ActualImportMapping` pozostają bez zmian; po reparentingu stary import może bezpiecznie odmówić. Nie osłabiać kontroli hierarchii, nie dodawać automatycznych remapowań/reimportu.
- Zachować host-managed worktree/branch, istniejące prywatne pakiety i zastane niepowiązane dirty. Żadnych push/merge/deploy ani sprzątania innych środowisk.

## Review Focus

1. EDIT odziedziczony po zmianie nazwy rodzica nie może wywoływać sztucznej mutacji dziecka; 38 zmienionych ścieżek oznacza tylko 30 aktualizacji starych wierszy — Task 1/3.
2. Awaria po COMMIT, przed odpowiedzią CLI, nie może utworzyć drugi raz rodziny lub innych nowych węzłów — Task 3.
3. Zmiana kategorii, referencji albo grantu po preflight musi zatrzymać APPLY, nie unieważniać po cichu reguł/propozycji/produktów — Task 2/3.
4. Zmiana wejścia, właściciela lub połączenia DB nie może być potraktowana jako zatwierdzona operacja; również przy ponowieniu — Task 1/2/3.
5. Ponowny import Actual po przeniesieniu grup ma nadal odmówić konfliktu zamiast zresetować drzewo, tworzyć duplikaty lub zmieniać mappings — Task 3/4.

---

## Fakty ustalone podczas planowania

- `entities.create_category()` i `update_category()` w `backend/app/finance/entities.py` walidują właściciela/typ rodzica/cykle i korzystają z advisory lock `category-tree:{owner}`. Nie wykonują COMMIT.
- `CategoryCreate`: `name`, `parent_id`, `type`; `CategoryUpdate` pozwala na więcej pól, ale ten operator podaje WYŁĄCZNIE rzeczywiście zmienione `name`/`parent_id`.
- Importer `backend/scripts/migrate_actual.py:299–355` bierze najpierw lock `actual-import:{owner}`, potem serwisy kategorii biorą lock drzewa. Zachować tę kolejność; nie modyfikować importera.
- Trwały receipt ma pola `user_id, action, key, request_hash, entity_id, result_ids, version, response_json` i unique `(user_id, action, key)`. Użyć `action="category_tree_reorganize_v1"`, nie tworzyć nowej tabeli.
- `log_event()` ma osobne `user_id` i `performed_by`; ustawić rzeczywistego właściciela i `performed_by="operator-cli"`, bez sesji lub podszywania się pod człowieka w przeglądarce.
- W zatwierdzonym mapowaniu: 16 KEEP, 38 EDIT, 11 HOLD. Rekonstrukcja name/parent_id daje **30 aktualizacji** (19 zmian nazw, 21 zmian rodzica, 10 obu naraz) i 8 zmian ścieżki wyłącznie wskutek zmiany rodzica. Wszystkie 35 pozostałych starych wierszy pozostają nietknięte.
- Wersje wejścia: propozycja SHA256 `c41d1c57b9bc48b7e3fa5f8b7117b1c2ee0f8065cdc4b051bf3280baa5db8c79`; mapowanie `e585810542033f7a24d211989ca4420aae712a99f044a941e34c0f651a36646e`; źródło `e813a3e41211ecbdf9782c9804a46c784db6a23692690ea1b79e1190cb51eda2`.
- Prywatny `design-approval-private.json` dokumentuje zgodę na projekt i zakończenie Actual, ale ma `production_apply_approved=false`. Nie jest plikiem zgody APPLY.

## File structure

| Plik | Jedna odpowiedzialność |
|---|---|
| `backend/scripts/category_tree_manifest.py` | Weryfikacja pakietu, modele i czyste kompilowanie docelowych name/parent_id |
| `backend/scripts/category_tree_guard.py` | Właścicielski snapshot, referencje i preflight/verify bez zapisów |
| `backend/scripts/category_tree_apply.py` | Jedna transakcja, domenowe zmiany, audyt i idempotentny receipt |
| `backend/scripts/category_tree.py` | Operator CLI, dopasowanie DB, jawne zgody i bezpieczne wyjście |
| `backend/tests/fixtures/category_tree_synthetic.json` | Anonimowa struktura65→79; żadne oryginalne etykiety, UUID lub liczniki transakcji |
| `backend/tests/test_finance/test_category_tree_manifest.py` | Pure testy kompilatora i integralności |
| `backend/tests/test_finance/test_category_tree_guard.py` | Integracyjne testy snapshotu/ref/grantów na lokalnym finanse_test |
| `backend/tests/test_finance/test_category_tree_apply.py` | Atomowość, receipt, audit, retry i CLI |
| `docs/operations/category-tree.md` | Runbook przygotowania, próby i późniejszego osobno zatwierdzanego wykonania |

Bez zmian `backend/app/**`, frontend/src, requirements, Alembic, compose lub globalnych ustawień. Jeżeli wykonawca uzna zmianę tego zakresu za konieczną, najpierw przedstawić powód, nie dopisywać jej do tego planu.

### Task 1: Zweryfikowany pakiet i czysty kompilator mapowania

**Files:** Create `backend/scripts/category_tree_manifest.py`; Test `backend/tests/test_finance/test_category_tree_manifest.py`; Fixture `backend/tests/fixtures/category_tree_synthetic.json`.

**Interfaces:**
- Produces frozen typed models `CategoryBefore(id: UUID, parent_id: UUID|None, name: str, type: Literal["expense","income"], source: str, is_active: bool)`, `NewRef(key: str)`, `NewNode(key: str, name: str, parent: UUID|NewRef|None, type: Literal["expense"])`, `CategoryPatch(id: UUID, name: str|None, parent_changed: bool, parent: UUID|NewRef|None)`.
- `load_bundle(directory: Path, *, expected_source_sha: str, expected_mapping_sha: str, expected_proposal_sha: str) -> CategoryTreeBundle` checks the private manifest/files and hashes, never executes any file in that directory.
- `tree_fingerprint(rows: Sequence[CategoryBefore]) -> str`: SHA256 canonical JSON sorted by UUID, only `id,name,parent_id,type,source,is_active`; excludes observation time, usage counts, paths and timestamps.
- `compile_tree(bundle: CategoryTreeBundle) -> PreparedTree`, fields `before_fingerprint: str`, `patches: tuple[CategoryPatch,...]`, `creates: tuple[NewNode,...]`, `expected_paths: dict[UUID|NewRef,str]`, `hold_ids: frozenset[UUID]`, `keep_ids: frozenset[UUID]`, `mapping_sha: str`, `proposal_sha: str`. New keys are opaque input identifiers, not filenames/SQL.
- All failures use typed `CategoryTreeError(code: str)` without raw names/UUID/DB URL in default messages.

- [ ] **Step 1 — Write failing pure tests.** Synthetic fixture retains topology and decision counts65/38/16/11/14, but uses new deterministic test UUIDs and neutral labels. Do not commit a redacted copy containing real IDs or text. Assertions:

  ```python
  plan = compile_tree(load_synthetic_bundle(tmp_path))
  assert len(plan.patches) == 30
  assert len(plan.creates) == 14
  assert sum(p.name is not None for p in plan.patches) == 19
  assert sum(p.parent_changed for p in plan.patches) == 21
  assert len(plan.expected_paths) == 79
  assert len(plan.hold_ids) == 11
  assert len(plan.keep_ids) == 16
  assert not (set(p.id for p in plan.patches) & (plan.hold_ids | plan.keep_ids))
  ```

  Add named tests: `test_ancestor_rename_does_not_patch_eight_unchanged_children`, `test_hold_keeps_name_parent_and_path`, `test_rejects_missing_extra_duplicate_source`, `test_rejects_cross_type_parent_cycle_and_orphan`, `test_rejects_new_node_collision_and_third_level`, `test_fingerprint_ignores_observation_not_names_source_or_active`, `test_modified_json_or_markdown_hash_is_rejected`, `test_bundle_does_not_execute_private_python_or_follow_symlink`. Missing fields/unknown actions/delete/type-change directives fail closed; names remain data.
- [ ] **Step 2 — Run RED.** From `backend/`: `.venv/bin/pytest tests/test_finance/test_category_tree_manifest.py -v`. Expected: failure for missing operator module/API, not a DB skip.
- [ ] **Step 3 — Implement the exact interfaces.** Resolve proposed parents against unique typed target paths, compare own name/parent identity rather than derived path text, topologically order new nodes. No DB import, side-effectful scripts, guessed interpretation of HOLD or source IDs replaced by new IDs. Parse only the known JSON/Markdown files; the private generator is not a plug-in.
- [ ] **Step 4 — Run GREEN**, same command. Expected: all named tests pass, no private artifact dependency or network.
- [ ] **Step 5 — Commit**, only module/tests/anonymous fixture: `feat: walidacja i kompilator planu drzewa kategorii`.

### Task 2: Read-only preflight i kontrola zależności

**Files:** Create `backend/scripts/category_tree_guard.py`; Test `backend/tests/test_finance/test_category_tree_guard.py`.

**Interfaces:**
- Consumes `PreparedTree`, `CategoryBefore`, `tree_fingerprint()` and `CategoryTreeError` from Task 1.
- Produces `GuardReport(owner_id: UUID, before_fingerprint: str, reference_fingerprints: dict[str,str], reference_counts: dict[str,int], blockers: tuple[str,...], actual_migration_closed: bool)`.
- `preflight(db: AsyncSession, owner: UUID, plan: PreparedTree, *, actual_migration_closed: bool) -> GuardReport`: SELECT only, no flush/commit/create-on-read; caller starts `REPEATABLE READ READ ONLY` with configurable statement timeout and always rolls back.
- `verify_before(db: AsyncSession, owner: UUID, plan: PreparedTree, expected: GuardReport) -> None`: same checks inside locked APPLY, no writes. `verify_after(db: AsyncSession, owner: UUID, plan: PreparedTree, *, resolved_ids: Mapping[str,UUID], before: GuardReport) -> None`: SELECT, all actual paths/counts/types/IDs and immutable reference fingerprints match expected.

- [ ] **Step 1 — Write failing integration tests** using `@pytest.mark.integration` and the existing guarded local `finanse_test` fixture. Names/assertions:
  - `test_preflight_is_owner_scoped_read_only_and_creates_nothing`: foreign owner's rows untouched; no implicit settings, consent, audit or receipts.
  - `test_stale_tree_name_parent_source_active_or_extra_category_blocks`: same IDs do not authorize a changed tree.
  - `test_foreign_owner_reference_to_category_is_blocker`: także dziecko kategorii lub FK z cudzym ownerem jest błędem integralności; ujawnić wyłącznie licznik/bloker, nie cudze dane.
  - `test_existing_budget_schedule_bill_posting_and_import_refs_are_counted_and_retained`: stable-ID references are reported and hashed, not rejected merely because a category is used.
  - `test_rule_grant_proposal_origin_or_receipt_item_evidence_blocks`: owner-scoped existing rule/origin/proposal/receipt evidence is a blocker in this initial conservative operator; do not mutate/invalidate it.
  - `test_marker_or_suggestion_consent_and_active_read_work_blocks`: marker/rules enabled, any owner suggestion-consent row or active document/receipt/suggestion jobs is a blocker; no change to policies or grants to clear it.
  - `test_unknown_category_reference_requires_review`: discover FK references from registered complete app metadata; unknown/new reference table blocks, never silently omit it. Handle Actual mapping separately because it is not an FK.
  - `test_closed_actual_migration_is_required_without_touching_import_mapping`.
  - `test_after_verification_detects_modified_posting_import_budget_or_foreign_owner`: hashes use exact types/minor units, not float sums.
- [ ] **Step 2 — Run RED:** `.venv/bin/pytest tests/test_finance/test_category_tree_guard.py -v`. Expected: missing guard module/functions; do not accept unavailable-DB skip as test proof.
- [ ] **Step 3 — Implement interfaces.** Register static owner-scoped finance reference queries (postings via transaction owner), plus complete FK discovery to detect unregistered dependencies. Include account/transaction/posting/date data, import mappings, budgets/schedules, bills/allocations and rule/suggestion/receipt/command evidence. Never query credentials/session tokens. Reference fingerprints exclude categories and new operator control records, but require all preexisting ledger/references/control rows unchanged. Baseline whole-tree snapshot includes all owner categories, including inactive ones.

  Preflight records all reference counts privately. It allows existing ordinary ledger/budget/document FKs because IDs are preserved, but refuses the explicitly listed immutable/grant/evidence cases. Their reconciliation is out of scope. If initial live preflight reports a blocker, stop and show its effect to the user; do not extend permissions or infer a repair.
- [ ] **Step 4 — Run GREEN**, same command; then Task 1 suite. Expected: passes on the allowed local DB, read-only transaction verified. Do not use production for these tests.
- [ ] **Step 5 — Commit:** `feat: preflight tylko do odczytu dla drzewa kategorii`.

### Task 3: Atomowy APPLY, idempotentny receipt i jawny operator CLI

**Files:** Create `backend/scripts/category_tree_apply.py`, `backend/scripts/category_tree.py`; Test `backend/tests/test_finance/test_category_tree_apply.py`.

**Interfaces:**
- Consumes Task 1/2 public interfaces; existing `entities.create_category`, `entities.update_category`, `CategoryCreate`, `CategoryUpdate`, `log_event`, `FinanceCommandReceipt`.
- `apply_tree(db: AsyncSession, owner: UUID, plan: PreparedTree, *, operation_id: UUID, expected: GuardReport, request_hash: str) -> ApplyResult`: no internal COMMIT; transaction controlled by CLI. `ApplyResult(operation_id: UUID, before_fingerprint: str, after_fingerprint: str, created_ids: dict[str,UUID], updated_ids: tuple[UUID,...], replayed: bool)`.
- `inspect_operation(db: AsyncSession, owner: UUID, plan: PreparedTree, *, operation_id: UUID, request_hash: str) -> OperationStatusReport`, with `status: Literal["not_applied","applied","applied_state_changed","busy_or_conflict","receipt_conflict"]` and optional `result: ApplyResult`. It never writes rows.
- Stable request hash binds version1, owner, operation_id, approved proposal/mapping hashes and before fingerprint. It does not depend on a changing clock or generated IDs.
- CLI `run(args: Sequence[str]) -> int`, modes `--preflight`, `--verify`, `--apply`; default is preflight, mutually exclusive. Common `--bundle-dir`, `--owner`, `--operation-id`, `--report-file`, explicit timeout options; all paths/data remain private. `CATEGORY_TREE_DATABASE_URL` must exactly match configured `DATABASE_URL`; neither value appears in stdout/errors. `--apply` additionally requires `--approval-file` and exact approved operator-bundle digest.
- Production approval format version1 binds `scope=category_tree_apply_v1`, `production_apply_approved=true`, owner, operation_id, input digests, source tree fingerprint, tested operator bundle SHA, current runtime revision/image ID, schema, successful fresh backup/restore proof SHA/snapshot, rehearsal proof SHA and fenced proof SHA. The existing design-approval file can NEVER satisfy it.
- Evidence freshness/timeouts come from explicit private operator configuration; validate positive values and inject a clock in tests. No unbounded stale fence proof or hidden fixed cost/rate/timeout assumption.

- [ ] **Step 1 — Write failing integration/CLI tests.** Assertions for anonymous65-category fixture and ordinary references:

  ```python
  result = await apply_in_committed_test_transaction(plan, owner, operation_id)
  assert len(result.created_ids) == 14
  assert len(result.updated_ids) == 30
  assert await owner_category_count(owner) == 79
  assert await original_ids_present() == 65
  assert await unchanged_original_rows_count() == 35
  assert await owner_type_counts(owner) == {"expense": 73, "income": 6}
  assert await preexisting_ledger_and_refs_identical()
  assert await operator_audit_counts(owner, operation_id) == {"created": 14, "updated": 30, "batch": 1}
  assert await operation_receipt_count(owner, operation_id) == 1
  ```

  Add tests `test_domain_create_update_are_used_without_type_source_active_changes`, `test_parent_changed_false_does_not_clear_parent`, `test_fault_after_first_create_mid_updates_and_before_receipt_rolls_back_everything`, `test_response_loss_after_commit_replays_without_second_writes`, `test_verify_during_uncommitted_apply_reports_busy_not_not_applied`, `test_verify_reads_fresh_receipt_after_lock_acquisition`, `test_same_key_different_request_is_conflict`, `test_receipt_replay_with_changed_post_tree_reports_drift_not_success`, `test_second_operation_id_cannot_reapply_to_post_tree`, `test_reference_or_grant_change_since_preflight_aborts_before_first_write`, `test_owner_db_or_hash_mismatch_opens_no_write_transaction`, `test_design_approval_cannot_authorize_production_apply`, `test_missing_stale_or_mismatched_runtime_backup_rehearsal_fence_proof_refuses_apply`, `test_errors_do_not_print_url_private_labels_or_uuid`, `test_actual_importer_still_refuses_original_group_after_reparent`. The last test uses a synthetic parser in the isolated DB, never an Actual server or private source.
- [ ] **Step 2 — Run RED:** `.venv/bin/pytest tests/test_finance/test_category_tree_apply.py -v`. Expected: missing apply/CLI API, not successful production work.
- [ ] **Step 3 — Implement transaction and CLI.** Before creating a DB engine, validate CLI mode and required approval; default paths cannot imply APPLY. Load full metadata without starting FastAPI lifespan or worker. Preflight/verify use read-only sessions; APPLY uses SERIALIZABLE, configurable timeouts, advisory locks in order **actual-import:{owner} → category-tree:{owner}**, then owner category row locks. Validate request/receipt and rerun preflight against the frozen expected report under these locks.

  If matching receipt exists, return replay only after current post-tree and references still match its stored after proof. A changed request is conflict; post-commit drift is an explicit stop. A new operation ID on an already changed tree fails the expected-before check, not another 14 creations.

  `--verify` uses READ COMMITTED READ ONLY and nonblocking transaction advisory locks in the same order. If another operation/import holds a lock, return `busy_or_conflict`, never `not_applied`. Only after both locks are acquired does a NEW SELECT snapshot read receipt/tree: absent receipt + exact original tree means `not_applied`; matching receipt + exact after proof means `applied`; matching receipt + later changes means `applied_state_changed`; divergent request means `receipt_conflict`; otherwise `busy_or_conflict`. This avoids a stale REPEATABLE READ snapshot falsely reporting no commit. Release locks by rollback. CLI exit codes: applied0, not_applied3, busy_or_conflict4, applied_state_changed5, invalid input/receipt_conflict2. No verify status automatically authorizes another APPLY.

  Create 8 new roots, then 6 family leaves through `create_category`; generated IDs are captured in this transaction. Resolve parent references and perform exactly 30 minimal `CategoryUpdate` calls, no updates for the 8 inherited-only paths. Re-read each result and verify owner/type/source/is_active; no direct SQL UPDATE/DELETE on category/ledger/import mappings. Append 14 create audits, 30 update audits and one batch audit with `performed_by="operator-cli"`, preserving previous audit rows.

  Run `verify_after` before COMMIT. Insert one `FinanceCommandReceipt` with the specified action/key, resolved IDs and before/after proof. CLI commits once, only after all assertions; every exception rolls back. A lost response is resolved by `--verify` and the DB receipt, never by deleting markers or guessing from JSON logs. Technical audit/receipt rows are the only additional writes besides the specified category rows.
- [ ] **Step 4 — Run GREEN:** three operator suites together; verify all original importer/entity tests still pass. Expected: no new schema, policy or frontend dependency and no weakened Actual group guard.
- [ ] **Step 5 — Run project gates `/lint`, `/typecheck`, `/test` according to their command definitions against this worktree and isolated test DB.** Expected: all applicable tests/lint/types pass; no unexplained DB skips or private fixture requirements. Do not run `/migrate` or `/deploy`; unchanged frontend does not require a new image. Record output in task-owned private evidence.
- [ ] **Step 6 — Commit:** `feat: kontrolowana atomowa reorganizacja kategorii przez operatora`.

### Task 4: Próba na odtworzonej kopii i runbook z osobną bramką produkcyjną

**Files:** Create `docs/operations/category-tree.md`; update `docs/CHANGELOG.md`, `docs/TASKS.md`, `docs/JOURNAL.md`. Private rehearsal artifacts outside Git. No production APPLY as part of this task.

**Interfaces:** Consumes tested CLI, `GuardReport`, `ApplyResult`, exact approved inputs and current `active-release.json`. Produces private operator bundle SHA, preflight report and rehearsal proof; later production approval must bind them.

- [ ] **Step 1 — Write runbook's preparation and refusal checklist.** Match current runtime/schema/image IDs instead of assuming the old release helper's baseline. Private bundle contains ONLY the four tested modules under `scripts/`, no private data/code executed from the data bundle. Run in the matching immutable backend runtime with a read-only `/release-ops` mount and `PYTHONPATH=/release-ops:/app`, not a host `/app` mount. Do not add scripts/__init__.py that shadows existing namespace modules, requirements, ports, image builds or app deployment.

  CLI forms (placeholders are privately resolved, never guesses):
  ```text
  python -m scripts.category_tree --preflight --bundle-dir <private-design-dir> --owner <confirmed-owner-uuid> --operation-id <stable-operation-uuid> --report-file <private-preflight.json> --statement-timeout-ms <configured-value>
  python -m scripts.category_tree --verify --bundle-dir <private-design-dir> --owner <same-owner> --operation-id <same-operation> --report-file <private-verify.json> --statement-timeout-ms <configured-value>
  python -m scripts.category_tree --apply --bundle-dir <private-design-dir> --owner <same-owner> --operation-id <same-operation> --approval-file <separate-scope-specific-approval.json> --report-file <private-result.json> --statement-timeout-ms <configured-value> --lock-timeout-ms <configured-value>
  ```
  Expected without a matching private target URL or APPLY approval: nonzero safe refusal, no database mutation.
- [ ] **Step 2 — Prepare isolated rehearsal.** Follow `docs/operations/backup-restore.md` to verify a fresh encrypted snapshot on a disposable local restore target, not production. Preserve private data in root-only directories; no upload to external services. New snapshot/restore SQL or DROP is allowed only for explicitly identified disposable test DB/schema under the established procedure, never production. No global conftest/drop operation against an unapproved or shared DB.
- [ ] **Step 3 — Run the tested CLI against the restored copy.** First read-only preflight, then a TEST-ONLY approval binding that isolated DB and the bundle, then APPLY, verify, and same-key replay. Expected:65original IDs/14new/30updates/79total; exact private target paths and max2levels; all HOLD/KEEP unchanged; ordinary references, amounts/currencies/dates/FX/source and account balances unchanged; receipts/audits exactly as Task3. Rehearsal any blockers STOP, not a repair to real or cloned data outside the approved scope.
- [ ] **Step 4 — Record rehearsal proof and run operator/full gates.** Rehearsal proof binds source snapshot, real approved mapping/proposal digests, operator bundle digest, runtime image/source compatibility and schema, counts/retention/replay result. Run tests after any operator change. Dispatch ONE independent whole-change reviewer on the operator/test/runbook diff, with Spec, this plan, and Review Focus verbatim; no production writes by reviewer. Important/Critical findings receive one TDD fix pass + complete gates, not a second review loop.
- [ ] **Step 5 — Prepare a fresh READ ONLY production preflight if the user has approved executing this plan.** No policy reconciliations or create-on-read; report aggregate drift/ref/blocker status privately. A fingerprint/reference/grant mismatch since design/rehearsal prevents production approval; show the blocker, do not silently expand the plan. This is not APPLY.
- [ ] **Step 6 — Document the separately gated production procedure, DO NOT RUN IT under plan-execution approval:**
  1. Present exact operation UUID, source/mapping/proposal/operator/runtime/schema hashes,30minimalupdates+14creates, expected report-group changes, Actual migration closed, HOLD list unchanged, and maintenance/recovery scope. Obtain explicit approval of this exact production operation; do not infer it from acceptance of this plan or a generic “tests passed”.
  2. Read active release/rollback metadata privately; preserve current frontend config, app/data container IDs and image IDs. Fence public ingress with a tested503 response, verify no direct backend published path. Wait for admitted requests to finish and require zero active document/receipt/suggestion/rule work before any stop; no model calls to empty a queue.
  3. Gracefully stop existing backend/worker via the FULL active base+prod+versioned Compose list, never base alone. Recheck Redis/durable state after producers stop. ARQ finished-cron dedup markers without payload/queue membership are not active jobs; retained real work is a STOP. Do not delete queue keys, reset jobs or blindly run historical release helpers. If safe draining of dispatcher-only work is needed, explicitly document the same-runtime, no-new-cron bounded drain before continuing.
  4. Under the fence, capture final owner reference/tree fingerprints and fresh encrypted backup; verify isolated restore/checksums/migrations/ledger by the installed procedure. Retain snapshot/images and bind this final evidence, current no-write fence, runtime and unchanged source fingerprint to the separate production approval file.
  5. Run exactly one category-tree APPLY in a one-off compatible immutable container, while public503 and app producers stopped. Pre-COMMIT failure leaves original data unchanged. Timeout/unknown after dispatch is investigated with READ ONLY `--verify` and DB receipt before any next command; no blind retry or second operation UUID.
  6. Before reopening: verify all79paths/types, old65IDretention, HOLD/KEEP unchanged, ledger/references/mappings immutable, owner scope and45audits+1receipt. Restart original backend/worker (same images/config; no frontend recreation), check internal health/logs/nojobdispatch caused by operation. Restore saved nginx config with `nginx -t`/reload, then publicHTTPS200/anonymous401 and worker health/zero unexpected errors. DBproof is primary; authenticated UI check requires a legitimate user session/manual user inspection, never forged sessions or auth overrides.
  7. If verification fails after COMMIT, keep maintenance, preserve new nodes/receipt/evidence and escalate for explicit repair-forward. No automatic deletion of14nodes, category rollback, importer bypass, downgrade or production backup restore. Backup is for separately authorized recovery, not an implicit destructive retry.
  8. Save operation outcome privately, docs-only handoff and final before/after manifest. Active application revision/Compose metadata is unchanged because this is a data operation, not a release. Do not label all future Actual imports as supported; the importer guard remains in force.
- [ ] **Step 7 — Commit runbook and docs:** `docs: procedura próby i zatwierdzania reorganizacji kategorii`. Hand over rehearsal/preflight results and ask for the exact production operation approval only when all gates pass. If any blocker exists, report it rather than request an executable approval.

## Self-review planu

| Kontrola | Wynik |
|---|---|
| Spec coverage | Task1:65/65, 14new, 30real edits, HOLD/KEEP/type/ID. Task2:owner/ref/grants/import provenance. Task3:atomic services/audit/receipt/auth. Task4:privacy/rehearsal/backup/maintenance/explicit APPLY/recovery. |
| Step scan | Każdy moduł ma dokładne API i testy RED→GREEN; procedura ma warunki PASS/STOP. Brak sekcji wymagającej od wykonawcy odgadnięcia prywatnych nazw lub interpretacji HOLD. |
| Interfaces | Ten sam `PreparedTree`, `GuardReport`, `ApplyResult`, `NewRef` i fields istniejącego receipt we wszystkich zadaniach; request hash stabilny, after-IDmapping z receipt. |
| Review Focus | Wszystkie5warunków mają nazwane testy w Task1/2/3, powtórzenie receipt i realny układ65→79 w Task4. |
| Proportion | Cztery małe moduły operatorskie i runbook; zero dodatkowych endpointów/UI/migracji, wersjonowania całej aplikacji lub silnika mapowania Actual. |
| Decyzja o Actual | Ważna zależność z kodu wyjaśniona z użytkownikiem; import zakończony. Zachować guard i mappings, nie rozszerzać tego planu o nowy importer. |
| Scope of consent | Projekt zatwierdzony; plan do zatwierdzenia. Implementacja/testy narzędzia i osobne produkcyjne APPLY nie zostały jeszcze zatwierdzone. |

## Handoff

Rekomendacja: **Native** — cztery zadania mają współdzielone silne interfejsy i jeden stan operacyjny; ciągła implementacja z TDD oraz jednym końcowym świeżym review ogranicza koszt/przełączanie kontekstu. Alternatywa: Subagent-driven, osobny wykonawca/reviewer per zadanie. Najpierw zatwierdzenie tego planu i wybór metody, potem narzędzie/próba. Produkcyjne APPLY zawsze osobno.
