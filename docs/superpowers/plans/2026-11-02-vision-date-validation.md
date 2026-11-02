# Vision date validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require ISO dates or null from image extraction and terminate invalid model output safely without lease exhaustion or misleading provider-outage wording.
**Architecture:** Tighten the existing nullable string date schema and prompt; perform the existing ReviewFields semantic conversion inside the adapter's safe validation boundary. Keep worker retry/CAS/policy semantics unchanged. Distinguish invalid_model_output in status and review UI without displaying response values.
**Tech Stack:** Existing Python/Pydantic/OpenAI Responses, React/TypeScript, pytest/vitest/Playwright; no dependency changes.
**Spec:** User-approved chat scope: ISO dates or absence, safe handling instead of uncaught exceptions; prepare and deploy after tests/review. No private document AI retry during diagnosis or release.

## Global Constraints
- No private invoice/model-response values in tests, repo, logs or reports. Synthetic inputs only; no actual provider requests or automatic reprocessing of existing failures.
- Date fields issue_date/sale_date/due_date remain required but nullable. Non-null date text must match `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`; ReviewFields still enforces a real canonical calendar date.
- Never infer ambiguous/missing dates; ask the model for null. Don't normalize arbitrary date prose, default a date or relax finance/review validation.
- Conversion failure becomes VisionProviderError(code='invalid_model_output', retryable=False), raised from None; no raw validation exception/input/response log.
- No DB schema, auth, parser limits, AI model/provider/policy/config changes; preserve original and manual financial approval.
- Prompt/schema changes clarify the pre-existing ISO date contract, not a new AI capability. Keep configured version/policy identity and record that provenance-granularity decision.

## Review Focus
- Calendar-impossible ISO-looking dates must be caught after strict model JSON validation, not only by a regex.
- Missing/null dates remain allowed, valid leap dates are preserved, no date is invented or silently coerced.
- Invalid output is terminal after one HTTP call: safe job/revision state, no lease retry or raw traceback leak, originals unchanged.
- Other invalid ReviewFields values remain caught; provider errors retain their existing labels and retry policy.
- Release proofs bind source and UI/dist to one SHA and exact app images; preserve configuration, policy and data, no automatic replay of the failed real document.

### Task 1: Date contract, safe conversion and UI regressions
**Files:** backend/app/documents/vision_schemas.py, vision_client.py; backend/tests/test_documents/test_vision_client.py and test_vision_worker.py; frontend/src/components/documents/documentStatus.ts/.test.ts and DocumentReview.tsx/.test.tsx, frontend/src/pages/UiReliability.test.tsx.
**Interfaces:** extract_image_review(jpeg: bytes, *, config: VisionConfig) -> VisionExtraction unchanged; failures use existing VisionProviderError. review_suggestion_from_payload and ReviewFields remain strict. getDocumentStatus distinguishes invalid_model_output with label `Nieprawidłowy wynik AI` (warning); provider errors stay unavailable.
- [x] Write RED adapter tests for all three invalid date fields, malformed and impossible calendar dates, request schema/prompt, nullable/valid dates and input/exception redaction; write worker regression using real adapter+mock transport that persists terminal invalid_model_output once, not attempts_exhausted.
- [x] Write RED status/review UI regressions: invalid_model_output label and fixed alert `AI zwróciło niepoprawne dane. Możesz uzupełnić pola ręcznie.` with no response details and no automatic retry; existing provider behavior unchanged.
- [x] Implement date schema pattern/descriptions and prompt guidance; put ReviewFields conversion in existing safe validation try. Adjust only known-code UI messages.
- [x] GREEN focused backend/frontend; independent whole-fix review, one RED→GREEN blocking-fix pass if needed; full isolated /test /lint /typecheck equivalents, build/E2E with source/dist manifests.
- [x] Commit scoped code/tests and own documentation hunks only, preserving unrelated Velo/Q7 work.

### Task 2: Exact safe release
**Files:** Task-owned private scripts/evidence under /tmp/opencode/vision-date-fix-20261102; docs/audits/2026-11-02-vision-date-validation.md and CHANGELOG/TASKS/JOURNAL.
**Interfaces:** Consume exact gated Task1 SHA; reuse reviewed immutable release procedure with exact previous app45c8c2d as rollback, same config/runtime/schema/policy.
- [x] Fresh encrypted backup + installed isolated restore; build immutable matching app images, compare complete Compose configuration in memory (persist whole-render HMAC only), verify source/image/UI identities.
- [x] Exact-image network-none synthetic date contract/error/success smoke and legacy400 regression, no provider/DB/private-file use; operation procedure review and explicit exact-SHA approval before apply.
- [x] Apply app services only, verify HTTPS/assets/auth/read-only browser and data/policy/original/service identities; observe and finalize atomically, preserve rollback.
- [x] Update docs/ledger and commit; request one explicit UI `Ponów AI` only after release and user consent, never automate it or reupload/backfill the failed document.
