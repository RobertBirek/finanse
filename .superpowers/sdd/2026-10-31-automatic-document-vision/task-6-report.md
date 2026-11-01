# Task 6 report — automatic document vision

## Scope
- Added owner-scoped, batched latest-review summaries and common `DocumentResponse` mapping.
- Added safe response fields (`processing_method`, review summary, text-exists flag, local OCR state) without document storage/text fields.
- Added effective DB-policy/config gated upload capability fields; only the configured provider label can be exposed.
- Added an operator CLI with default dry run, explicit apply, controlled test-DB target and expected-epoch refusal.
- Routed a newly committed vision upload to its existing durable job queue entry; legacy uploads retain the legacy queue and Redis failures leave durable recovery intact.

## TDD evidence
- RED: `TEST_DATABASE_URL=...127.0.0.1:55432/finanse_test PY -m pytest tests/test_documents/test_vision_status.py tests/test_documents/test_vision_policy.py -v` → 3 failures: missing mapper/capability fields (one fixture construction failure corrected in test setup).
- GREEN focused: same safe command plus upload-capabilities/vision-upload tests → `6 passed`.

## Gate
- `PY .superpowers/sdd/2026-10-31-automatic-document-vision/gate.py --name task-6-gate`
- First run: backend lint PASS; mypy failed on nullable config provider. Fixed.
- Fresh full run: backend lint/types/tests PASS; frontend lint/types/tests PASS. Logs/results: `.superpowers/sdd/2026-10-31-automatic-document-vision/task-6-gate/`.

## Supplemental mandatory regression matrix
- New upload: `test_new_vision_upload_enqueues_existing_durable_job_after_commit` asserts the exact existing durable job ID is sent to `process_document_job`, and legacy enqueue is not called.
- Duplicate after flag change: `test_duplicate_image_after_flag_change_creates_no_new_vision_intent` asserts no job/revision is created for the historic content.
- Redis recovery: `test_vision_upload_redis_failure_keeps_durable_job_for_dispatch` asserts committed pending job and exact dispatcher entry/id.
- CLI: `test_cli_dry_run_and_epoch_mismatch_do_not_mutate` invokes the real entry function with the controlled 127.0.0.1:55432 `finanse_test` target and checks zero mutation; `test_disable_pauses_old_work_and_enable_never_resumes_it` checks epoch bump, review incompleteness and no old-job resume.
- Status: 50-document owner-scoped mapper tests assert summary state, text existence and no storage/raw data exposure.
- Full post-supplement gate: `PY .../gate.py --name task-6-gate-final3` → backend lint/types/tests PASS; frontend lint/types/tests PASS. Artifacts: `task-6-gate-final3/`.

## Self-review
- Checked no raw OCR/revision data, storage path, provider endpoint, or key reaches the new responses.
- The required direct-queue routing is implemented after commit and preserves the existing durable-job recovery path.
- The full-gate worker loop failure was traced to its test using a stale module session factory; binding it to the fixture engine makes the safe test target explicit.

## Fix 1 — review coverage and CLI operator boundary
- Added a real SQLAlchemy engine `before_cursor_execute` counter around only
  `document_responses(...)` for 50 documents; it asserts the mapper performs at most four
  statements, cleans up the listener in `finally`, and verifies the highest competing
  revision is selected.
- Replaced the direct service-only policy transition coverage with real
  `document_vision_policy.run(..., apply=True)` calls. Tests load the controlled test DB
  environment through `gate.environment()` via `importlib`, then use `Settings()` and
  `get_vision_config()` to verify the runtime fingerprint. Missing configuration returns
  `configuration_missing`/2 with no policy or audit mutation; enable, disable, and a fresh
  re-enable advance epochs and leave old pending/processing leased work paused/incomplete.
- RED evidence: the new CLI test initially failed because `run()` let
  `ValueError("configuration_missing")` escape instead of returning its controlled refusal.
  GREEN: `PY -m pytest tests/test_documents/test_vision_status.py tests/test_documents/test_vision_policy.py -v`
  (with `gate.environment()`) → **5 passed** (one existing Passlib deprecation warning).
- Completion gates `task-6-fix1-completion-gate` and fresh final
  `task-6-fix1-completion-gate-final`: backend lint PASS; backend types PASS;
  backend tests **FAIL** after 1003 passed/8 deselected because unrelated existing test
  `tests/test_finance/test_bill_payments.py::test_candidate_conflict_uses_matched_occurrence_forecast_effects`
  expected recurring conflicts but received none. Frontend steps were not run by the gate
  after that backend failure. No change was made outside Task 6 to mask or repair it.
