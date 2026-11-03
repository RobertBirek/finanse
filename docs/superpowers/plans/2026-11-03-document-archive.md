# Safe Document Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement task-by-task. Track checkboxes; this draft is NOT implementation/deployment approval.

**Goal:** Replace failing document hard-deletion with reversible, finance-safe archival and clear status/error feedback.

**Architecture:** Add nullable `documents.archived_at` as lifecycle state, preserving all originals/history/FKs. Owner-scoped archive/restore services serialize with processing admission on the Document row; UI lists active versus archived documents while finance retains private source access.

**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/Alembic/PostgreSQL and React/TypeScript/TanStackQuery/Zustand/Tailwind; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-document-archive-design.md` (assistant's proposed safe default, awaiting approval). Diagnosis: `docs/audits/2026-11-03-document-delete-diagnosis.md`.

## Global Constraints

- No harddelete, CASCADE, original-file removal, finance/ledger/source-link mutation or usage refund/reset.
- Archived originals/history remain available through existing private owner-scoped reads, including from finance.
- Active work blocks archive with409; archive/restore/upload duplication never enqueue AI/OCR.
- Serialize archive and every processing admission/claim using the existing Document row lock; preserve current lock order Document→revision/job.
- Repeated archive/restore is a no-op (same timestamp, no repeated audit); foreign/missing IDs return404.
- One additive nullable archived_at migration; never apply it to production or deploy as part of local implementation without separate permission.
- Keep unrelated Velo/Q7 dirty files; use the existing linked worktree. No package/runtime/config changes or main merge/push.
- Exact UI strings and safe-default semantics come from the spec; no misleading „Usuń” or „Spróbuj ponownie” for permanent domain blocks.

## Review Focus

- Archive versus new/replayed/claimed processing race: no work can start on archived documents, no deadlock; row-lock tests belong to Task1.
- Approved financial source remains readable and its ledger/allocations unchanged after archive/restore; Task1 integration and Task2 E2E.
- Archived duplicate upload must not resurrect visibility or consume additional usage; Task1 admission and Task2 upload tests.
- Old pending revisions with terminal jobs versus genuinely running legacy/text OCR: no permanent phantom block and no unsafe archive; Task1 state matrix.
- Logout/relogin and stale query completion after archive: no phantom activity/toasts or cross-session cache changes; Task2 mounted tests.

## File Map

- `backend/app/documents/models.py`, `schemas.py`: archived_at field and DTO; no new status enum value (processing status remains separate).
- New `backend/app/documents/lifecycle.py`: lifecycle errors/locked transitions/active-work checks; service.py delegates compatibility delete, list filters and duplicate read.
- `backend/app/documents/router.py`: explicit archive/restore and legacy DELETE adapter; clear domain-code mapping.
- `backend/app/documents/review_service.py`, `job_service.py`, `backend/app/worker.py`: archived guards in admission/claims/dispatch, with existing lock order.
- New Alembic revision under `backend/migrations/versions/` via `/migration "document archive lifecycle"`; single head, nullable DateTime(timezone=True), no data-destructive downgrade or FK changes.
- Backend tests: new `test_documents/test_lifecycle.py`, `test_lifecycle_api.py`, `test_lifecycle_races.py`; update `test_finance/test_bill_sources.py` to assert retained source rather than forbid harmless archival.
- `frontend/src/api/documents.ts`: archive/restore hooks and archived list argument/DTO; session-fenced mutation success.
- `frontend/src/components/DocumentList.tsx`, `DocumentUpload.tsx`, `documents/DocumentReview.tsx`: archive filter/actions, duplicate-in-archive feedback, disable fresh processing until restore.
- `frontend/src/stores/documentProcessingStore.ts`, monitor/inline components: forget document feedback only for matching actor, avoid watches on archived DTOs.
- Tests in matching frontend component/API/store test files; new `frontend/e2e/document-archive.spec.ts` and fixture support.

### Task1: Transactional archival, API and processing admission safety

**Interfaces:**
- Add `Document.archived_at: datetime|None` and `DocumentResponse.archived_at: datetime|None` (defaultNone).
- `set_document_archived(db: AsyncSession, user_id: UUID, document_id: UUID, *, archived: bool) -> Document` in lifecycle.py. Missing→LookupError; active archive→`DocumentLifecycleError(code="document_processing_active")`; archive guard for processing→`DocumentLifecycleError(code="document_archived")`.
- `require_document_unarchived(document: Document) -> None` for admission/claim after the Document row is locked; existing exact-intent read-only replay stays idempotent with no new work.
- `get_documents(..., status: str|None=None, *, archived: bool=False) -> list[Document]`; retain existing limits/offsets and owner scope. `get_document` continues to read both lifecycles by owner+UUID.
- POST `/documents/{id}/archive` and `/restore` return DocumentResponse/200. Legacy DELETE delegates archive and returns200 `{"message":"Document archived"}`. Error JSON:404 `code=document_not_found`;409 `code=document_processing_active` or `document_archived`, plus safe detail.
- `delete_document(...) -> bool` becomes compatibility archival adapter (False on missing), not db.delete; no parallel public harddelete path.

- [ ] **1. Write RED integration tests**: terminal review/job cases that currently produce500 now archive200 and retain every dependent row/original; linked approved finance archives200 with unchanged finance/ledger/source/allocations; repeated archive timestamp/audit stable; restore leaves jobs/usage untouched; owner isolation404; archived_at returned without extra mapper queries.
- [ ] **2. Run focused `/test`** for the new lifecycle cases in the guarded isolated DB; Expected: FAIL on missing archived_at/routes or current FK500. Never use production.
- [ ] **3. Add nullable field/migration and lifecycle service**: select owner document FOR UPDATE, check work before first archive, set timestamp/None, log `entity_type=document`, action `archived`/`restored` via existing audit.log_event in the same transaction. No audit on no-op. GET list defaults active; active discovery excludes archives; private content/history reads still work.
- [ ] **4. Map API and legacy delete to lifecycle**, preserving auth/CSRF. Add closed error mapping rather than catch-all ValueError; don't treat IntegrityError as successful deletion. Update finance-source regression to check preserved references.
- [ ] **5. Write RED admission/worker/duplicate/race tests**: pending/processing durablejob, legacy document, text review block409; paused/failed/superseded terminal jobs allowarchive; old pending vision with terminaljob doesn't block; fresh prepare/vision/OCR on archive409, exact replay no writes; duplicate archive upload remains sameUUID/is_duplicate/archive state/no enqueue; quota not refunded; two real sessions prove either archive wins or admitted work blocks archive without deadlock.
- [ ] **6. Run focused `/test`** for the admission/race tests. Expected: FAIL on current unconditional admissions/claims and archived filtering gaps.
- [ ] **7. Guard existing admission/claims/dispatch paths**: use common archived check after existing Document locks, refuse new work, skip archived dispatch candidates; preserve exact receipt replay without new jobs/calls. Check every non-terminal text review that could still run, not only the latest label. Duplicate upload remains read-only visibility-wise.
- [ ] **8. Verify GREEN** focused lifecycle/admission/finance tests plus `/lint` and `/typecheck`; isolated migration head upgrade preserves row counts, defaults and FK restrictions. No automatic downgrade dropping archived_at on populated data; preserve archive state for operational rollback planning.
- [ ] **9. Commit** own backend/migration/tests only: `feat: dodaj bezpieczną archiwizację dokumentów`.

### Task2: Archive UI, session-safe feedback and whole-change verification

**Interfaces:** consumes Task1 DTO/routes/list filter/errors. Produces `useArchiveDocument()` / `useRestoreDocument()` mutations taking `{documentId:string}`, existing auth-generation capture, and archived boolean in document query key. A store method `clearDocumentFeedback(actor: ProcessingActor, documentId:string):void` removes that document's watches/toasts only for current actor; no persistent user data.

- [ ] **1. Write RED frontend tests**: active/„Archiwum” lists have separate keys and filters; archive confirm uses exact spec text; linked finance source action archives (not deletes/unlinks finances); restore shows document without AI calls;409 displays processing reason,404/transport failures remain distinct; archived duplicates offer explicitrestore, never automaticwork.
- [ ] **2. Run focused `/test` frontend**. Expected: FAIL on missing archive hooks/filter/actions and generic delete errors.
- [ ] **3. Implement hooks/UI** in mapped files. Replace destructive-looking action with „Archiwizuj”; archive list offers „Przywróć”. Show clear success/error copy. Invalidate document-family queries, close archived viewer/review and remove linked review URL if needed; preserve owner-private finance access. Disable new prepare/retry on archived review until explicit restore.
- [ ] **4. Write RED mounted session tests**: accepted archive clears matching watches/toasts; stale active snapshot must not resurrect archived watch; delayed archive reply after logout or another user's login doesn't clear their watches/cache. Navigation or StrictMode must not duplicate lifecycle feedback.
- [ ] **5. Run tests to confirm RED**, then implement actor-fenced success and archived DTO suppression. Preserve existing operation completion dedup and feedback for other documents.
- [ ] **6. Verify GREEN** focused hooks/component/store/monitor tests and `/lint`/`/typecheck`.
- [ ] **7. Add mocked Chromium E2E375/1440**: document→archive→archive list→restore; attached approved source remains readable from finance; active work has409/reason without data mutation; archive duplicate upload no new job; keyboard/dialog/a11y and no overflow. Run production build/E2E; Expected: PASS with no backend/provider traffic.
- [ ] **8. One independent whole-change review**, using Review Focus above, before final source freeze. Resolve Important/Critical with RED→GREEN; report any deferred Minor. Expected: no unresolved blocking issue.
- [ ] **9. Final full `/test`, `/lint`, `/typecheck`, build/E2E** on pinned source manifest; run PostgreSQL suites serially. Validate additive migration and no data loss in isolated restore. Expected: allPASS, zero real AI/OCR and no production writes.
- [ ] **10. Update CHANGELOG/TASKS/JOURNAL and commit** only own UI/tests/docs: `feat: pokaż archiwum i przywracanie dokumentów`. Handoff states migration required, scope not deployed. Production backup/migration/rollback/deploy is a separate approval, not a hidden step.

## Plan Self-Review / Handoff

Spec mapped to Task1 lifecycle/admission/retention and Task2 UI/session feedback; all five review-focus inputs have explicit tests. API/type names consistent between tasks. Existing stack and finance invariants retained; no planned deletion of originals/dependencies or provider calls.

Recommendation: **Native / executing-plans**, sequential backend→UI, with one independent whole-change reviewer. This is a draft safe default, not user approval of archival semantics or implementation. Ask approval of this full scope first; deployment/migration approval remains separate.

Release caveat: the previous backend69b6f3d does not understand archived_at and still exposes harddelete. Do not call its rollback archive-compatible without an isolated compatibility rehearsal and a separately approved rollout/rollback plan. Never downgrade the production schema to erase archive state. This plan authorizes no production rollout.
