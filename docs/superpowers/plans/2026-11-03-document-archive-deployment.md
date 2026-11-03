# Document Archive Production Deployment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for sequential execution. Track the checkboxes. Obtain approval of the maintenance/recovery contract below before changing production.

**Goal:** Release approved document archival without losing originals, financial links or archive state.

**Architecture:** Prepare immutable backend/worker/frontend images from approved Git revision `81065329cc4cc8edc511800c436bf0a2f7b94025`. Apply the single additive migration while public application access and processing are quiesced, then start matching services. Recovery preserves the new schema; the old application is allowed only if an admission fence prevents concurrent writes and no archived documents exist.

**Tech Stack:** Existing Docker Compose, PostgreSQL16, Redis, npmplus ingress, Restic/systemd backup and installed isolated restore wrapper. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-document-archive-design.md`; local acceptance `docs/audits/2026-11-03-document-archive-local.md`; release procedure `.opencode/command/deploy.md` and `docs/operations/backup-restore.md`.

## Authorization and outstanding decision

- User said „zatwierdzam” after the handoff naming `8106532` and requiring separate production migration/deployment consent. This authorizes the deployment direction, not destructive recovery.
- Proposed operational contract still needs approval: a short maintenance window for the coordinated migration/release; if archive state exists, fail closed in maintenance and repair forward rather than run an archive-unaware backend.
- No backup, production DDL, container restart, ingress change or active-release update has been performed during plan preparation.

## Global Constraints

- Candidate source is fixed at `81065329cc4cc8edc511800c436bf0a2f7b94025`; no implicit host-main merge or push. Local gate: backend1183/frontend410/lint/types/build/E2E103+1expectedskip; verify source and dist manifests before packaging.
- Current metadata baseline: release69b6f3d, schema92eef8e8086c, active override `/opt/finanse/webapp/releases/69b6f3d/compose.active.yaml`. Revalidate against live service image IDs before any action; metadata alone is not proof.
- Only migration `92eef8e8086c → 2f4b2c2a527c`, adding nullable `documents.archived_at`. No production downgrade, DROP, cleanup, data rewrite or snapshot restore.
- Preserve PostgreSQL/Redis/Stirling container identities, original files, ledger, allocation/source links, usage, policyepoch4 and existing model/prompt/schema configuration. No real AI/OCR, replay, retry, import, duplicate upload or finance mutation by the agent.
- Queues and active DB work must be naturally idle before quiescing services. If work is active, stop and report; never kill active extraction, clear Redis or cancel jobs to satisfy a gate.
- Use full base+production+approved release Compose list and existing environment file. Replace only backend/worker/frontend with `--no-deps --no-build`; do not use bare Compose, `make up` or `make restart`.
- Do not print secrets, private document content or backup data. Retain old release images, encrypted snapshots and unrelated Velo/Q7 working files.

## Review Focus

- Old backend can expose archived records and hard-delete paths: recovery gate must refuse it when any archive state exists, including a concurrent state change.
- An installed restore drill uses host checkout migration files: separately prove the approved candidate migration against an isolated restored schema, not only the old host head.
- Workers/API can admit work during a rolling switch: rehearse a fenced maintenance interval and abort on pending/running work without clearing it.
- Rendered Compose can silently drop secrets/security mounts: compare the entire private rendered baseline, allow only approved images/build changes, and pin actual image IDs/revisions.
- Health200 is insufficient: check migration, source identity, retained rows/originals/ledger and authenticated-query contract without mutating real user documents.

## Task 1: Prepare and certify a recoverable release (no production switch)

**Files:** existing `ops/prepare_release.py`; root-only evidence under `/tmp/opencode/document-archive-deploy-20261103/`; versioned package under `/opt/finanse/webapp/releases/8106532/`. No product code changes planned.

- [ ] Approve the maintenance/recovery contract, then capture exact candidate/source/dist proofs and live baseline service revisions, data IDs, full private Compose rendering and active-release bytes.
- [ ] Obtain a fresh encrypted backup through the established backup service/Make target and installed `finanse-restore-verify.service`; require success and the same snapshot ID, no resetting failure/start limits.
- [ ] On an isolated target whose identity is checked before writes, restore that snapshot and apply exactly candidate migration2f4b2c2a527c. Verify row/file/link/ledger retention, NULL archive defaults and unchanged finance/usage/policy. Keep private contents out of logs.
- [ ] Rehearse recovery: old runtime with new schema and zero archives may serve only behind the write fence; synthetic archived state must make the recovery guard refuse old runtime. Never discard archived_at to make rollback possible.
- [ ] Prepare candidate using `ops/prepare_release.py` with genuine active runtime revision and verified dist, build offline Dockerfiles, pin image IDs and verify all backend/worker source files against approved Git. Inspect full rendered configuration and test routes/models in exact images without provider access.
- [ ] Prepare a one-shot, hash-bound execution/recovery checklist or controller with offline tests covering baseline drift, wrong migration, stale backup, nonidle work, archive-state recovery rejection and repeat-apply refusal. It must not auto-restore production.
- [ ] Independent read-only operations review of the actual package, migration rehearsal and recovery procedure; resolve blocking findings before production apply.

## Task 2: Coordinated migration/release and acceptance

**Interfaces:** consumes Task1 certified package, same verified snapshot, pinned baseline/config/image proofs and approved maintenance contract. Produces verified runtime evidence and atomically finalized active-release metadata.

- [ ] Revalidate backup freshness (<1h), approval, metadata/config/image hashes, unchanged candidate and idle queues/DB work. Drift or user work means stop, not replace the baseline.
- [ ] Fence external application access (including cached-client API writes) during the agreed maintenance window, allow existing requests to finish, recheck idleness, then quiesce old backend/worker. Keep data services and originals running/unchanged.
- [ ] Run approved candidate Alembic upgrade to exactly2f4b2c2a527c with bounded lock/statement waits. If migration fails, inspect actual revision/state before recovery; never blindly downgrade or retry uncertain DDL.
- [ ] Start matching backend/worker/frontend with the complete Compose file list. Verify source revisions, schema, no `/app` host mount, mounts/security settings and data IDs before exposing access.
- [ ] Verify HTTPS/assets/API health/auth rejection, worker readiness, preserved private row/ledger/original/link fingerprints, usage/policy and logs. Do not archive a real user document as a smoke test; use local/in-isolation functional evidence.
- [ ] Remove the maintenance fence only after acceptance checks pass. Browser375/1440 read-only checks and at least five minutes of bounded observation follow. New user actions after opening must not be mistaken for release corruption.
- [ ] On failure, keep/fence maintenance first. Old images may resume only under a stable write fence with proven zero archived rows; keep the added column and schema revision. If any archive state exists, retain it and repair forward; ask separately for any destructive restore.
- [ ] Only after successful verification finalize active-release metadata atomically, marking migration executed and the restricted recovery contract. Preserve old images but do not advertise their generic rollback script as archive-safe.
- [ ] Update CHANGELOG/TASKS/JOURNAL and a deployment audit with exact images/revisions, snapshot, migration outcome and exclusions. Commit only owned documentation; no push or host-main merge implied.

## Self-review / handoff

No new product behavior is proposed. The extra approval concerns availability and safe recovery, not another feature design. Sequential native execution plus one operations reviewer is recommended because migration, ingress fencing and recovery must share one stable baseline. Stop before production if any guard or rollback rehearsal cannot be proved.
