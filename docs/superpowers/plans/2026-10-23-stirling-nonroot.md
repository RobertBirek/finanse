# Stirling Non-root Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a verified staging runtime without weakening document hardening.

**Architecture:** Digest-pinned derived Stirling image preserves vendor startup,
with build-time aliases and immutable Polish tessdata. Scoped uploads ACLs are
evaluated on a copy; production changes remain a separate gate.

**Tech Stack:** Docker/Compose, Python 3.12, pytest/httpx, POSIX ACL, Tesseract.

**Spec:** `docs/superpowers/specs/2026-10-23-stirling-nonroot-design.md`

## Global Constraints

- Exact upstream digest and script SHA-256 from the spec; mismatch fails build.
- Stirling UID/GID 1001:1001; application staging UID/GID 10001:10001.
- No production writes, mounts, migrations, credentials or privileged runtime.
- Retain read-only, cap-drop ALL, no-new-privileges, /tmp noexec/nosuid and limits.
- No OCR against user documents; only synthetic rendered-text fixtures.

## Review Focus

- Upstream script drift: refuse patch rather than deleting unrelated startup code.
- OCR false success: verify extracted content for all three image/document formats.
- ACL privilege widening: retain original owners/modes except named ACL mask;
  refuse symlinks and test inaccessible unrelated users.
- Restore loses ACLs: explicit isolated reapplication before non-root acceptance.
- Shutdown and temp exhaustion: check clean termination and fail closed, not restart loops.

### Task 1: Guarded derived image

**Files:** create `ops/stirling/Dockerfile`, `ops/stirling/patch_init.py`,
`ops/stirling/README.md`, `backend/tests/test_stirling_runtime.py`.
**Interface:** `patch_init(source: bytes) -> bytes` validates the full expected
script hash and replaces exactly the two alias blocks; rejects other inputs.

- [ ] Add tests for wrong hash, exact patch and preserved remainder; observe RED.
- [ ] Implement patch and Dockerfile; create aliases at build time; retain vendor
  entrypoint and USER 1001:1001. Unit tests GREEN.
- [ ] Use model revision, artifact path and SHA-256 fixed in the spec; record
  upstream license/notice and reject missing/mismatched input before build.
- [ ] Build local immutable image; verify script diff, model hashes and languages.
- [ ] Commit after lint/typechecks/tests pass.

### Task 2: Real isolated OCR staging

**Files:** create `ops/stirling/staging.compose.yaml`,
`backend/tests/test_stirling_staging.py`. Leave `ops/document-hardening.compose.yaml`
unchanged; all overrides are staging-only in this follow-up.
**Interface:** explicit `STIRLING_TEST_IMAGE` image ID; tests marked `proxy`,
opt-in for costly OCR; no live service names or production volume defaults.

- [ ] Write staging test reproducing upstream read-only startup failure; observe RED.
- [ ] Launch derived image with isolated internal network and NO published
  ports (host test client uses private bridge IP), empty UID-owned configs/logs and bounded tmpfs. Require health readiness
  within 180 seconds with bounded diagnostics on failure.
- [ ] Exercise synthetic PNG/JPEG -> PDF -> OCR -> text, and scanned PDF -> OCR
  -> text; assert recognizable literal output and identity encoding.
- [ ] Assert no root runtime, intended security controls, graceful stop within
  45 seconds and cleanup of exact test-owned containers/networks/volumes.
- [ ] Run representative resource fixtures; record limits and observed outcomes;
  stop rather than silently relax noexec/read-only/memory limits.
- [ ] Run tests GREEN and commit.

### Task 3: Upload permissions and fresh application runtime

**Files:** create `ops/upload-permissions/README.md`, `ops/upload-permissions/Dockerfile.test`,
`backend/tests/test_upload_permissions.py` (uploads/ is globally ignored).
Update `docs/operations/backup-restore.md` with explicit future ACL procedure.
**Interface:** staging root only, synthetic root-owned 0600 originals and shared
backup lock; no generic recursive production-mutating helper in this task.

- [ ] Reproduce read/write failure for UID 10001 on production-like fixtures.
- [ ] Apply named ACLs only to the isolated fixture, saving prior ACLs; test old
  reads, new atomic writes, duplicate hash checks and backup lock mutual exclusion.
- [ ] Verify symlink/special-file refusal, ownership/content preservation,
  unrelated-user denial, ACL rollback and post-tar-restore reapplication.
  Follow spec manifest validation exactly; reject changed inventories on rollback.
  Assert restored 0600 files fail non-root reads before reapplication, then pass.
  Assert no default ACL inheritance and stable backup lock inode.
- [ ] Build current backend requirements in fresh local runtime and verify
  `pip check`, imports and parser subprocess under UID 10001/read-only.
- [ ] Record exact dependencies/image ID; no production ownership changes.
- [ ] Run tests GREEN and commit documentation/tests.

### Task 4: Final gate and deployment handoff

**Files:** update CHANGELOG/TASKS/JOURNAL and this plan.

- [ ] Independent whole-change review; resolve significant findings.
- [ ] Run project `/test`, `/lint`, `/typecheck`, build, existing proxy tests and
  explicit OCR/permission staging tests; record skips as missing coverage.
- [ ] Inspect rendered staging Compose without exposing secrets; document exact
  new release/image IDs, outstanding sizing limits and backup/rollback steps.
- [ ] Obtain approval of the resulting revision and production ACL/mount changes
  before rollout. Prior f256a10 approval does not cover a different runtime blindly.

## Current status

Final local status: Tasks 1–3 complete; Task 4 review and gate complete (632
backend, 8 proxy/ACL/OCR, 194 frontend PASS; lint/types/build PASS). Production
handoff/approval remains open, not a completed deployment. Historical diagnostic
notes below explain the decisions; final evidence supersedes intermediate failures.

User approved plan and no-default-ACL policy. Task 1 implemented: guarded patch
tests 4 PASS and derived image built offline with verified Polish model. Task 2
active: startup succeeds after reviewed /pipeline tmpfs amendment; correcting
isolated bridge test connectivity before OCR acceptance. Task 3: fresh backend
runtime imports/pip check and 16 parser tests PASS; 2 synthetic ACL tests PASS.
Whole-branch review and final gate remain. No production changes.

BLOCKED after actual connectivity correction: health passes, but vendor init
permission loop changes /pipeline mode 0700 to 0755; same loop contains
world-write fallback. Do not relax the assertion. The alias-only patch needs a
reviewed scope extension: replace runtime permission repair with strict writable
path validation, preserving JVM/OCR/supervision/shutdown. User approved extension;
tests cover main-init and bootstrap permission removal plus strict validator.
New runtime staging in progress. No OCR acceptance claim.

Latest evidence supersedes the historical blockers above: strict runtime staging
PASS for A4 PNG/JPEG/scanned PDF including accented Polish. Pipeline usage 16 KiB;
effective process UID/GID and graceful shutdown verified. ACL helper provenance,
inventory preflight and post-restore writer/lock checks added after independent
review. Final whole-suite gate running. Wide-image fillPage distortion is an
open product issue, not repaired by this runtime change.
