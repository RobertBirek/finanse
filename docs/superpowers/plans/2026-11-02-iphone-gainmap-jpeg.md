# iPhone gain-map JPEG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept the reproduced Apple gain-map JPEG variant without accepting arbitrary MPO documents.
**Architecture:** Extend only the bounded parser's JPEG recognition. Recognise two contiguous JPEG images indexed as MP primary + undefined auxiliary, with explicit Apple HDR gain-map auxiliary type/version; fully decode both under existing resource/pixel limits. Existing normalization consumes frame zero, applies EXIF orientation and writes a metadata-free single JPEG; test that contract and preserve the original byte-for-byte.
**Tech Stack:** Existing Python/Pillow, no dependency, schema or frontend change.
**Spec:** Approved chat description: handle this iPhone variant, preserve original, use primary for derivatives, retain safety limits; do not accept arbitrary multi-image files. Private structural evidence confirms Apple auxiliary type and HDRGainMapVersion65536, primary4032×3024, auxiliary2016×1512.

## Global Constraints
- No private invoice in repo/tests, no OCR/AI/application upload/DB mutation for reproduction.
- No changes to MIME allowlist, size/CPU/memory/time/concurrency limits, AI policy or auth.
- Only two MP entries, primary baseline image plus undefined JPEG auxiliary; valid contiguous in-file ranges and JPEG boundaries, no dependencies/reserved attributes.
- Auxiliary must not exceed primary dimensions or configured pixel limit; both must fully decode. Recognise Apple pixeldatainfo AuxiliaryImageType urn:com:apple:photo:2020:aux:hdrgainmap and HDRGainMapVersion65536 in bounded UTF-8 XMP; reject DTD/entities/malformed XMP.
- Unknown versions/roles, stereo/ordinary MPO, extra frames, corrupt/truncated/oversized images remain rejected.
- No automatic reprocessing of old documents, migrations, arbitrary multi-image support or provider calls.

## Review Focus
- Corrupt MP offsets/sizes, trailing bytes and truncated auxiliary cannot masquerade as a valid single JPEG.
- XMP strings alone do not bypass type/count/range/decode checks; malformed XML and entities fail closed.
- Main-vs-aux selection must survive normalization and orientation; auxiliary must not replace the invoice image.
- Existing PNG/APNG/HEIF/JPEG rules, MIME mismatch and process resource/cancellation semantics remain unchanged.
- Release binds exact gated source and immutable images, retains rollback/config/data/policy and never stores rendered secrets.

### Task 1: Bounded gain-map JPEG support and synthetic regressions
**Files:** Modify backend/app/documents/validation_process.py; add backend/tests/test_documents/test_gainmap_jpeg.py and synthetic fixture in backend/tests/test_documents/fixtures.py. Existing image_process.py changes only if tests demonstrate need.
**Interfaces:** detect_document_mime_type(content: bytes, max_pages: int =100, max_pixels: int =25000000) -> str | None; accepted gain-map content returns image/jpeg. normalize_image API unchanged.
- [x] Write synthetic two-frame Apple fixture, acceptance/isolation/MIME tests and negative role/version/frame/index/XMP/decode/pixel cases; verify derivative frame-zero/orientation/metadata removal and stored-original preservation.
- [x] Observe RED for acceptance with current parser; baseline existing document suite remains green.
- [x] Implement minimal standalone helper in validation_process.py (script runs with -I, no new sibling imports), dispatch only MPO to it; don't relax ordinary JPEG/PNG gates.
- [x] Observe GREEN focused document tests; inspect locally supplied JPEG through candidate's bounded parser/normalizer, emitting only structural proof and discarding derivative pixels.
- [x] Run complete /test /lint /typecheck equivalents on isolated test DB, build/E2E; independent source/security review and fix any blocking findings with RED→GREEN.
- [x] Commit only scoped source/tests/docs hunks, leave pre-existing Velo/Q7 changes unstaged.

### Task 2: Safe release
**Files:** Reuse ops/prepare_release.py and reviewed private release procedure in a new task-owned private directory; document docs/audits/2026-11-02-iphone-gainmap-jpeg.md.
**Interfaces:** Consume exact Task1 SHA plus successful gate/review/structural/build proofs; prepare immutable backend/worker/frontend package with current production9369b5d as rollback.
- [x] Fresh backup/restore, exact image/config/source/dist identity and candidate regression smoke without DB/AI.
- [x] Review procedure; require approval of exact SHA/scope per /deploy before runtime apply.
- [x] Apply only app services, no migration/policy operations; verify HTTPS/assets/auth/browser/data/policy/original invariants and observation, atomically finalize metadata.
- [x] Update CHANGELOG/TASKS/JOURNAL and audit; request one real upload only after completed deployment. Never claim phone success from offline parser tests.

## Execution notes
Already in linked worktree feat/financial-document-workflow; no new worktree needed.
Native inline execution continues existing accepted small-fix workflow; fresh final reviewer required.
Commands are read from installed .opencode/command definitions; no callable slash-command tool is available, so use the same isolated command equivalents as prior approved release (never host/production DB).
