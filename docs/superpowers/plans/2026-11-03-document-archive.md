# Safe Document Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement task-by-task. User approved local implementation; production migration/deployment is NOT approved.

**Goal:** Replace failing document hard-deletion with reversible, finance-safe archival and clear status/error feedback.

**Architecture:** Add nullable `documents.archived_at` as lifecycle state, preserving all originals/history/FKs. Owner-scoped archive/restore services serialize with processing admission on the Document row; UI lists active versus archived documents while finance retains private source access.

**Tech Stack:** Existing Python/FastAPI/SQLAlchemy/Alembic/PostgreSQL and React/TypeScript/TanStackQuery/Zustand/Tailwind; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-document-archive-design.md` (safe default approved for local implementation). Diagnosis: `docs/audits/2026-11-03-document-delete-diagnosis.md`.

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

### Task 1: Transactional archival, API and processing admission safety

**Interfaces:**
- Add `Document.archived_at: datetime|None` and `DocumentResponse.archived_at: datetime|None` (defaultNone).
- `set_document_archived(db: AsyncSession, user_id: UUID, document_id: UUID, *, archived: bool) -> Document` in lifecycle.py. Missing→LookupError; active archive→`DocumentLifecycleError(code="document_processing_active")`; archive guard for processing→`DocumentLifecycleError(code="document_archived")`.
- `require_document_unarchived(document: Document) -> None` for admission/claim after the Document row is locked; existing exact-intent read-only replay stays idempotent with no new work.
- `get_documents(..., status: str|None=None, *, archived: bool=False) -> list[Document]`; retain existing limits/offsets and owner scope. `get_document` continues to read both lifecycles by owner+UUID.
- POST `/documents/{id}/archive` and `/restore` return DocumentResponse/200. Legacy DELETE delegates archive and returns200 `{"message":"Document archived"}`. Error JSON:404 `code=document_not_found`;409 `code=document_processing_active` or `document_archived`, plus safe detail.
- `delete_document(...) -> bool` becomes compatibility archival adapter (False on missing), not db.delete; no parallel public harddelete path.

- [x] **1. Write RED integration tests**: terminal review/job retention, approved finance/ledger/source retention, audit idempotence, restore and owner isolation.
- [x] **2. Run focused `/test`**: new lifecycle cases verified RED in isolated DB; no production writes.
- [x] **3. Add nullable field/migration and lifecycle service**: locked owner transitions, audit/no-op semantics, active lists and retained private reads.
- [x] **4. Map API and legacy delete to lifecycle**: explicit errors and finance-source regression.
- [x] **5. Write RED admission/worker/duplicate/race tests**: state matrix, archived guards, quota and two-session serialization. Review added running legacy/text-worker regressions.
- [x] **6. Run focused `/test`**: admission/race cases verified RED before guards.
- [x] **7. Guard admission/claims/dispatch**: archived work rejected, exact receipts retained, no new provider processing. Exception deferred: old pending vision duplicate may deliver an existing terminal job; claim rejects it, no AI/usage (see final report).
- [x] **8. Verify GREEN**: focused417PASS/lint/types, isolated migration upgrade and safe downgrade guard; final full backend1183PASS. Busy row archive now conservatively returns409 via SKIP LOCKED rather than waiting behind a worker.
- [x] **9. Commit** backend/migration/tests: `8c96be6`; review fixes committed separately at closeout.

### Task 2: Archive UI, session-safe feedback and whole-change verification

**Interfaces:** consumes Task1 DTO/routes/list filter/errors. Produces `useArchiveDocument()` / `useRestoreDocument()` mutations taking `{documentId:string}`, existing auth-generation capture, and archived boolean in document query key. A store method `clearDocumentFeedback(actor: ProcessingActor, documentId:string):void` removes that document's watches/toasts only for current actor; no persistent user data.

- [x] **1. Write RED frontend tests**: active/archive filters, retained sources, explicit restore/duplicate handling and error reasons.
- [x] **2. Run focused frontend tests**: verified RED before UI changes.
- [x] **3. Implement hooks/UI**: Archiwizuj/Przywróć, retained private access, archived processing restrictions.
- [x] **4. Write RED mounted session tests**: archive feedback, stale snapshots, logout/owner changes and StrictMode; review added private query isolation tests.
- [x] **5. Confirm RED and implement fencing**: actor/sequence barriers and scoped query keys with generation, without losing other-document feedback.
- [x] **6. Verify GREEN**: focused tests/lint/types and final full410frontendPASS.
- [x] **7. Mocked Chromium E2E375/1440**: six archive scenarios, a11y and no overflow PASS; full fresh build/E2E103PASS+1expectedskip, no provider calls.
- [x] **8. Independent whole-change review**: ses_e5ed13a1bffePe7BMgp2QvMgHh; Critical0/Important2 fixed RED→GREEN, one reviewMinor and one visualMinor deferred in TASKS/report.
- [x] **9. Final gates**: backend1183/frontend410/lint/types/build/E2E103+1skip PASS, exact source/dist manifest verified. First stale-head test failure retained in evidence; corrected lineage assertion and full rerun PASS. Migration tests isolated; no production writes/real AI/OCR.
- [x] **10. Update CHANGELOG/TASKS/JOURNAL and commit** own UI/tests/docs: `feat: pokaż archiwum i przywracanie dokumentów`. Backend review fixes: `7e1d3d0`. Handoff states migration required, scope not deployed. Production backup/migration/rollback/deploy requires separate approval.

## Plan Self-Review / Handoff

Spec mapped to Task1 lifecycle/admission/retention and Task2 UI/session feedback; all five review-focus inputs have explicit tests. API/type names consistent between tasks. Existing stack and finance invariants retained; no planned deletion of originals/dependencies or provider calls.

Executed: **Native / executing-plans**, sequential backend→UI, with one independent whole-change reviewer after user approval of local implementation. Deployment/production migration approval remains separate. Final report: `docs/audits/2026-11-03-document-archive-local.md`.

Release caveat: the previous backend69b6f3d does not understand archived_at and still exposes harddelete. Do not call its rollback archive-compatible without an isolated compatibility rehearsal and a separately approved rollout/rollback plan. Never downgrade the production schema to erase archive state. This plan authorizes no production rollout.
