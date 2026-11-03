# Document Processing Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this approved vertical change. Track checkboxes and a task-owned ledger.

**Goal:** Show actual AI/OCR work and one global completion toast per observed operation, including after route navigation.

**Architecture:** Keep PostgreSQL job/revision/document states authoritative. Repair OCR summary mapping and add an owner-scoped paginated active-document read. A session-scoped Zustand tracker registers accepted actions and observed active work; one Layout monitor polls tracked document IDs, so completion survives navigation and the default 50-document list boundary. Toasts distinguish review-ready/incomplete/failure/pause, never mutate or retry work.

**Tech Stack:** Existing FastAPI/SQLAlchemy/Pydantic, React18/TanStackQuery/Zustand/Tailwind; no dependency or database-schema changes.

**Spec:** User approved the chat description: AI/OCR indicators at the document and globally; global toast with open-document action after navigation; separate completion/missing-data/error copy without duplicates; fix real OCR state; local implementation only, no new AI calls or deployment. IBAN/sale-date extraction remains separate.

## Global Constraints

- No production writes, deploy, AI/OCR calls, historical job replay, migrations, extraction-prompt changes or field guessing.
- All status reads owner-scoped, no extracted document content; GETs never enqueue work.
- Preserve unrelated Velo/Q7 changes and the existing linked worktree (BASE b1e3f03).
- Session-memory-only tracking/toasts; reset on logout/user switch and fence delayed mutation/query responses using owner/session generation.
- Initial already-completed history produces no toast; accepted fast completion does; StrictMode/refetch/retries do not duplicate notifications.
- Paused work is not processing/success; superseded work is not success. Network error is unknown status, not completion.

## Review Focus

- OCR can run while an old review is ready: actual active OCR must win the badge; latest jobs only, no cross-owner joins.
- A document older than the first50 list entries remains discoverable/trackable; tracked GETs are independent of active-list disappearance.
- A job can finish before the first poll: register accepted mutation results, skip duplicate upload, preserve operation identity across retries.
- Logout/relogin (even same user) fences late results and clears toasts; no document names or values survive another session.
- Partial/unsupported/failed/paused/superseded outcomes and null fields must never become an unqualified successful extraction notification.

## File map and interfaces

- Backend `processing_queries.py`, `schemas.py`, `service.py`, `router.py`: add `ReviewSummary.job_id: UUID|None`, `DocumentResponse.local_ocr_job_id/local_ocr_error_code: UUID|None/str|None`; populate existing `local_ocr_state` from the latest owner-scoped job. `GET /documents/active?limit=100&offset=0` returns `list[DocumentResponse]` with only currently active latest work (legacy OCR, latest review, latest durable jobs), before the UUID route. Batch enrichment remains <=4 queries/page.
- Frontend `api/documents.ts`: matching optional fields, active-document discovery read, session-fenced registrations for upload/prepare-review/prepare-vision/retry-OCR. Existing cache invalidation remains; no extra mutating request.
- New `components/documents/documentProcessing.ts`: pure operation extraction/classification. Identity: vision/text review revision UUID; local OCR job UUID; legacy OCR document UUID plus client intent generation for explicit reruns. Terminal state has precedence over stale pending review status.
- New `stores/documentProcessingStore.ts`: owner/generation-scoped watches, completion dedup, small dismissible toast queue; no persistence. Accepted mutation context is captured before await and cannot rebind an old response to a new session.
- New `components/documents/DocumentProcessingMonitor.tsx`: singleton in Layout; paginated active discovery + owner-scoped watched GETs, 3s polling only while work remains, abortable requests. Superseded/404 watches removed without false success; request failures show unknown/update state, retain watchers.
- New `components/documents/ProcessingFeedback.tsx`: reusable inline spinner/label, global compact header indicator, accessible toast host (`role=status`/polite; errors alert), dismiss and open-document action, no auto-dismiss while focus/hover (initial version remains until dismissed). Preserve existing theme/fonts, respect reduced motion and 375px layout.
- Update `Layout.tsx`, `DocumentList.tsx`, `DocumentReview.tsx` as needed: mount singleton feedback globally, active badges, toast link opens review using `?review=<id>` even outside first50 items.
- Tests: backend `test_documents/test_processing_feedback.py`; frontend corresponding store/helper/monitor/feedback tests, existing status tests and a mocked Playwright navigation/toast scenario.

## Task 1: Real status → session tracker → global feedback (one vertical deliverable)

- [x] Baseline existing status/mapper and frontend status tests pass using the established isolated test venv/database.
- [x] Backend RED: latest local OCR mapping/identity/error, latest owner-scoped review job ID, no stale/superseded or other-user work, active legacy/review/job discovery beyond50 with pagination, GET read-only and existing <=4-query mapper contract.
- [x] Backend GREEN: batched latest status summaries and active route; keep source data, jobs, quotas and extraction unchanged.
- [x] Frontend RED: helpers/store tests for active precedence, one toast per operation, fast completion, paused/superseded/partial outcomes, user/session fencing and stale replies. Implement pure helpers and tracker minimally.
- [x] Frontend RED: mounted monitor/feedback/navigation tests; assert global work indicator, notification after unmounting document page, dismiss/open behavior, polling/error/404 cleanup, no history toast or repeated notification. Implement monitor/UI and mutation registration; no source-content logging.
- [x] Focused suites + lint/types, then one independent whole-change review before freezing final source. Resolve Important findings via RED/GREEN; record minors/decisions.
- [x] Final full project `/test`, `/lint`, `/typecheck`, build and mocked E2E with exact source manifest. Do not run parallel PostgreSQL suites.
- [x] Update CHANGELOG/TASKS/JOURNAL, commit only this local feature/own docs after verification. Preserve other dirty files; no push/main merge/deploy/AI.

## Execution notes

This records the already-approved small feature, not a request to expand extraction accuracy work. Existing isolated venv and identity-checked `finanse_test` helper avoid the obsolete repository SDK and occupied test Compose port; never use a production DB as a test target.

Final evidence: `/tmp/opencode/document-processing-notifications-20261103/final-source-proof.json`.
Backend1151/frontend388/lint/types/build PASS, full mocked E2E97PASS+1expectedskip.
Independent review: one Important viewer-label regression fixed4RED→GREEN; no deferred minors.
Only E2E fake API changed after full gate; fresh frontend gates/full E2E PASS, backend/app hashes unchanged.
Local feature only: no AI/OCR, deployment, schema/prompt/extraction changes, push or main merge.
