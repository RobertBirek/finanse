# Document Archive Production Deployment Plan

> **For agentic workers:** Completed with superpowers:executing-plans after explicit maintenance/recovery approval. Do not replay this release. Evidence and exclusions are in the deployment audit.

**Goal:** Release approved document archival without losing originals, financial links or archive state.

**Architecture:** Prepare immutable backend/worker/frontend images from approved Git revision `81065329cc4cc8edc511800c436bf0a2f7b94025`. Apply the single additive migration while public application access and processing are quiesced, then start matching services. Recovery preserves the new schema; the old application is allowed only if an admission fence prevents concurrent writes and no archived documents exist.

**Tech Stack:** Existing Docker Compose, PostgreSQL16, Redis, npmplus ingress, Restic/systemd backup and installed isolated restore wrapper. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-11-03-document-archive-design.md`; local acceptance `docs/audits/2026-11-03-document-archive-local.md`; release procedure `.opencode/command/deploy.md` and `docs/operations/backup-restore.md`.

## Authorization and outstanding decision

- User said „zatwierdzam” after the handoff naming `8106532` and requiring separate production migration/deployment consent. This authorizes the deployment direction, not destructive recovery.
- Operational contract approved by user „akceptuję”: a short maintenance window for the coordinated migration/release; if archive state exists, fail closed in maintenance and repair forward rather than run an archive-unaware backend.
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

- [x] Maintenance/recovery approved; exact source/dist, live69b6f3d/schema92, service IDs/rows/originals/config and metadata captured.
- [x] Fresh backup4e7b441f and installed isolated restore of the same snapshot PASS; no reset/retry of failure limits.
- [x] Same snapshot restored into disposable internal-only PostgreSQL; candidate92→2f PASS, rows/ledger/links/usage/policy retained, nullableNULL archive defaults and backup checksums verified. Disposable DB/network removed.
- [x] Isolated old ORM/new schema/zeroarchive PASS; real synthetic archive state makes guard refuse legacy recovery. Generic rollback script always refuses; no downgrade.
- [x] Exact candidate package prepared via ops/prepare_release.py; full Compose comparison, pinned imageIDs,210sourcefiles/backend image and offline routes/models/guard PASS.
- [x] One-shot hash-bound controller12offline tests PASS; drift/schema/backup/idle/transaction/fence/archive/repeat guards. No automatic production restore or legacy rollback.
- [x] Operations review ses_e5e5a8f3dffeSRkQPmcwfI1T2e Approved, Critical0/Important0; manual-downgrade TOCTOU minor deferred because downgrade prohibited. Review bound to265artifacts.

## Task 2: Coordinated migration/release and acceptance

**Interfaces:** consumes Task1 certified package, same verified snapshot, pinned baseline/config/image proofs and approved maintenance contract. Produces verified runtime evidence and atomically finalized active-release metadata.

- [x] Revalidated backup1282s/approval/config/images/source/baseline and idlework/transactions; no drift.
- [x] Fenced frontend/publicAPI, rechecked idleness, stopped old backend/worker; no active extraction cancelled or queues cleared.
- [x] Exact-image Alembic upgrade92→2f succeeded with5s/60s server timeouts; no downgrade/replay.
- [x] New backend/worker810 verified under closed ingress, then frontend810 opened; full Compose/no-deps/no-build and data IDs preserved.
- [x] HTTPS/assets/health/authrejection, exact artifacts/source, workerARQ/DB/Redis readiness, fenced rows/ledger/originals/links/usage/policy and logs PASS. No real user archive smoke/provider calls.
- [x] Browser375/1440 read-only and11samples/343.69s observation PASS; concurrent user activity allowed after opening. Final equality check found only23ownauth401 audits.
- [x] Recovery path certified, not triggered: generic legacy rollback disabled, no downgrade/production restore; archive state must remain preserved.
- [x] Active-release atomically finalized2026-11-03T13:53:23.372938+00:00, schema2f/migration_executed; old images retained but no generic rollback_override advertised.
- [x] CHANGELOG/TASKS/JOURNAL and deployment audit completed in local docs commit; no push/mainmerge. Final-readonly-proof PASS.

## Self-review / handoff

No new product behavior is proposed. The extra approval concerns availability and safe recovery, not another feature design. Sequential native execution plus one operations reviewer is recommended because migration, ingress fencing and recovery must share one stable baseline. Stop before production if any guard or rollback rehearsal cannot be proved.
