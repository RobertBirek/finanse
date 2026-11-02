# Complete image stream and explicit retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return the complete bounded JPEG from the asynchronous normalizer and offer explicit retry for an unreadable image review without deleting or uploading again.
**Architecture:** Keep image conversion in the existing bounded child process. Write input concurrently with reading stdout until EOF, stopping at limit+1, checking exit/JPEG boundaries, killing/reaping and draining on every failure/cancellation. UI extends the known incomplete-warning branch only; backend intent/policy/quota remain authoritative.
**Tech Stack:** Existing Python asyncio/Pillow, pytest, React/TypeScript/vitest/Playwright; no new dependency.
**Spec:** User approved correcting the reproduced64KiB-prefix bug plus availability of PonówAI. Keep2048px/quality90. No deletion, auto-retry/provider call/private pixels in model context.

## Global Constraints
- Source byte-preserving, private image derivatives only in memory, no OCR or provider calls in verification.
- Existing byte/pixel/CPU/memory/concurrency/time settings unchanged; normalized output must terminate with EOI and fit existing output bound. Do not loosen JPEG/HEIF admission or enable truncated decoding.
- Read incremental chunks until EOF, never assume read(n) fills n. Limit memory to configured output + bounded pipe/chunk buffers; reject on the first byte beyond output limit, never wait for EOF from an oversized producer.
- Input writing and stdout reading overlap to prevent pipe deadlock; on cancellation/timeouts/bad output kill+drain+reap child, cancel writer, release semaphore.
- UI makes incomplete/image warning unreadable or missing_required_fields actionable, with fixed message explaining missing/readability, no unknown warning interpolation. Explicit click creates a new intent; mount/poll never callsAI, active/error/readiness/unsupported rules remain safe.
- No database schema/config/policy changes, financial changes, deletion/history purge, migration, provider/model change or reprocessing of old jobs.

## Review Focus
- Large real synthetic JPEG output >64KiB must fully decode and equal complete child output byte-for-byte.
- Forced multi-chunk stdout and child simultaneous stdout/stdin must not truncate or deadlock; exact byte limit accepted, limit+1 rejected.
- Timeout, cancellation, abnormal exit, invalid/truncated JPEG, busy slot fail safely with no live child/task leak or exposed input.
- Supported incomplete/image review offers one explicit retry and preserves manual fields; active/pending/ready and unsupported output do not gain automatic AI work.
- Exact-image smoke must invoke app.documents.images.normalize_image, not only the child script; verify resulting JPEG decodes, no external requests, bind source/UI/images before any release.

### Task 1: Normalizer stream and retry UI
**Files:** backend/app/documents/images.py; backend/tests/test_documents/test_image_stream.py; frontend/src/components/documents/DocumentReview.tsx/.test.tsx. Other files only if a regression proves necessity.
**Interfaces:** async normalize_image(content: bytes,mime: str,*,thumbnail: bool=False,max_edge: int|None=None,max_output_bytes: int|None=None)->bytes unchanged, ImageNormalizationError unchanged; existing usePrepareDocumentVision mutates only on explicit click.
- [x] Write real-process RED for large seeded syntheticJPEG and delayed chunkedstdout returning completeJPEG; exactoutput/limit+1/truncation/nonzero exit; timeout/cancellation PID reaped+slot reusable; concurrent input/output case.
- [x] Write UI RED for supported incomplete/image warning unreadable/missing_required_fields with noerror; fixed warning and explicitAI button, noautomaticrequest/changes to manually entered fields; absent whenpending/processing/ready or non-image.
- [x] Implement minimal incremental reader and concurrent writer under existing timeout; errorcleanup drains and reaps child, returns only complete framedJPEG. Extend only UI incomplete branch with fixed explanatory text.
- [x] GREEN focused backend/frontend, actualasync privateJPEG reproduction offline on exactruntime with candidate source mounted read-only. Compare full childbytes in memory, noAI/DB, do not equate decode with provider success.
- [x] Fresh independent source/security review and RED→GREEN any blockers, then freeze code, full isolated /test /lint /typecheck and build/E2E manifests, scoped sourcecommit.

### Task 2: Safe versioned release (only after exact-SHA approval)
**Files:** Private task-owned evidence /tmp/opencode/image-stream-fix-20261102; docs/audits/2026-11-02-complete-image-stream.md and CHANGELOG/TASKS/JOURNAL.
**Interfaces:** Consume exact gated Task1 SHA. Existing immutable package mechanism, active5d5b82f rollback; config and policy unchanged.
- [x] Fresh backup/installed isolated restore; immutable candidate images and exactappsource/UI/dist binding; whole-renderHMAC only, preserve original/data/service identity.
- [x] Exactimage trueasync seededlargeJPEG normalization+bounded chunk/timeout smoke and inherited synthetic safe400/datecontract regressions, networknone/noDB/noAI. Procedure review and explicit exactSHA approval beforeapply.
- [x] Approved appservices-only deployment and readonlyHTTPS/assets/auth/browser/observation, atomicmetadata; no migrations/privateAIretry/deletion/backfill.
- [x] Close docs/ledger and scoped commits, askoneuserexplicitretry after release; deletion remains separate pending safe lifecycle decision.
