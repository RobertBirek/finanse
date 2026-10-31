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

## Self-review and known gap
- Checked no raw OCR/revision data, storage path, provider endpoint, or key reaches the new responses.
- The required direct-queue routing is implemented after commit and preserves the existing durable-job recovery path.
- **Concern:** regression coverage for the three requested enqueue cases (exact entry/job id, duplicate no paid intent, Redis failure recovery) and CLI transition cases is not yet present. This task is therefore reported `DONE_WITH_CONCERNS`, not as full Task-6 acceptance.
