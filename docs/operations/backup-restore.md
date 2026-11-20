# Backup And Restore Verification

`ops/backup.sh` sends PostgreSQL and uploads snapshots to the configured,
encrypted Restic repository. Credentials remain only in root-only files outside
Git.

## Ingress Network Rollout

The final Task 7 rollout uses the external bridge `finanse_ingress`
(`172.24.0.0/24`). NPMplus has the fixed address `172.24.0.2`; only
`finanse-frontend` and NPMplus join this network. The frontend also joins
`finanse_internal`, while `finanse-backend` joins only `finanse_internal`.
Do not attach or recreate running containers while preparing this configuration.

Before the approved rollout, verify both persistent stacks without printing
their secrets:

```bash
docker compose -f /docker/npmplus/compose.yaml --env-file /docker/npmplus/.env config > /dev/null
docker compose -f /docker/finanse/compose.yaml -f /docker/finanse/compose.prod.yaml --env-file /docker/finanse/.env config > /dev/null
docker network inspect finanse_ingress
```

## Setup

Install `restic`, PostgreSQL client tools, GNU tar, and configure the following
environment outside the repository and deployment manifests committed to Git:

- `BACKUP_WORKDIR`: private writable local directory for temporary snapshots.
- `DATABASE_URL_SYNC`: password-free PostgreSQL URL in the exact form
  `postgresql://user@host:5432/database`; it has no query string, fragment, or
  embedded password.
- `PGPASSFILE`: readable PostgreSQL password file with mode `0600`, outside Git.
  It supplies the password to PostgreSQL clients without placing it in a command
  line or URL. Configure entries in PostgreSQL's `.pgpass` format.
- `UPLOAD_DIR`: existing upload directory. It may be empty.
- `RESTIC_REPOSITORY`: encrypted offsite Restic repository location.
- `RESTIC_PASSWORD_FILE`: readable file containing the Restic repository password.

Run the backup with `make -C /docker/finanse backup`. Verify the manually
provisioned external Makefile targets without executing them with:

```bash
make -C /docker/finanse -n backup
```

The archive command is:

```bash
tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner -C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .
```

The database dump is captured first with `--serializable-deferrable`. The upload
archive is then created while holding an exclusive `flock` on
`$UPLOAD_DIR/.backup.lock`. Document writes use the same lock while creating the
content-addressed file. A document row is flushed only after its content exists;
document deletion currently does not remove stored content. This append-only
ordering prevents a backup database reference without its archived file.

This produces deterministic upload archives, including for an empty directory.
Each snapshot includes a JSON manifest with the UTC creation timestamp, Git SHA,
the exact Alembic revision queried from the backup target through `psql`, and
SHA-256 checksums for `postgres.dump` and `uploads.tar.gz`.

Retention is seven daily, four weekly, and six monthly snapshots. The target RPO
is 24 hours and the target RTO is 2 hours. Redis is not backed up because it is
not a source of truth; PostgreSQL is the source of truth.

## Restore Drill

Run a production restore drill only with
`sudo systemctl start finanse-restore-verify.service`. Its installed root-only
wrapper creates and removes the guarded `finanse_restore` database. The
low-level `make restore-verify` target is an internal wrapper dependency, not a
standalone production drill. The wrapper supplies `RESTORE_SNAPSHOT_ID=latest`;
legacy `snapshot=<id>` is explicitly rejected before any restore runner or
Restic process starts.

The verification script requires `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE`,
`RESTORE_DATABASE_URL_SYNC`, `RESTORE_DIR`, and `PGPASSFILE`. Both database URLs
must be password-free `postgresql://` URLs with a user, host, and database.
Query strings, fragments, and embedded passwords are rejected. `PGPASSFILE`
must be readable and mode `0600`. The restore script additionally refuses to
continue unless the database host is exactly `127.0.0.1`, and the
database name ends in `_restore` or `_test`. These guards run before Restic
restore and before `pg_restore`, preventing a production restore target.

The script restores into a private temporary directory, verifies manifest SHA-256
checksums before extracting uploads or touching the database, restores with
`pg_restore --clean --if-exists --no-owner`, then verifies that the restored
database revision equals the snapshot manifest revision. It upgrades the isolated
target to the repository's single current Alembic head using a password-free
asyncpg URL with an encoded `passfile` parameter in the Alembic process
environment, and verifies the upgraded database revision equals that head. It
then checks that every financial transaction has at least two postings and a zero
base-PLN balance. `RESTORE_DIR` must be empty. Uploads are extracted into a
private `.restore-run.*` staging directory under it; only after all database and
ledger checks pass is that staging `uploads` directory moved into
`RESTORE_DIR/uploads`. On failure, cleanup removes only the exact staging
directory and never a pre-existing or concurrently created user path.

## Automatyzacja systemd

Install the root-only systemd automation and inspect or operate it with:

```bash
sudo /opt/finanse/ops/systemd/install-timers.sh
systemctl list-timers --all finanse-backup.timer finanse-restore-verify.timer
sudo systemctl start finanse-backup.service
sudo journalctl -u finanse-backup.service -n 100 --no-pager
sudo systemctl start finanse-restore-verify.service
sudo journalctl -u finanse-restore-verify.service -n 100 --no-pager
sudo systemctl disable --now finanse-backup.timer finanse-restore-verify.timer
```

`finanse-backup.timer` runs daily at 02:30 and
`finanse-restore-verify.timer` on the first Sunday at 04:30, both in
`Europe/Warsaw`. Both timers use `Persistent=true`. The one-shot services share
a 15-minute `flock`, so backup and drill never overlap. Failures activate the
secret-free `finanse-operation-failure@.service` journal unit. The same shared
lock wraps manual `make backup` and the internal restore target. Failed
services retry after 15 minutes, with at most three starts in three hours.

The installer places the restore wrapper at
`/usr/local/lib/finanse/run-restore-drill.sh`, owned by `root:root` with mode
`0750`; the restore service invokes this installed path, not an executable in
the repository. It also creates the persistent, empty
`/docker/finanse/data/restore-drill` parent as `root:root` mode `0700`, required
by the service sandbox. It creates `RESTIC_CACHE_DIR=/docker/finanse/data/restic-cache`
as `root:root` mode `0700`, which systemd and Make both use; this preserves
`ProtectHome=true` without a Restic cache under `/root`. The wrapper creates
`finanse_restore` on the loopback PostgreSQL endpoint before verification. It
never restores to production.

On success or verifier failure, ownership-aware cleanup removes only the exact
`finanse_restore` database and restore output it created, retaining the empty
parent directory for systemd. Unexpected nonempty parent state must be
investigated through the failure journal before a manual rerun. No command,
unit, or journal entry contains secrets.


## Versioned Application Releases And Rollback

Production previously mounted `/opt/finanse/backend` over `/app`. Changing only
an image did not roll back that mounted code. New application releases must use
`ops/prepare_release.py` to create matching forward and rollback packages. This
tool prepares files only; it never applies Compose or changes a database.

Preserve the current backend, worker and frontend image IDs with explicit local
runtime tags. Prepare the rollback package from the current production Git
revision and a copy of the currently served frontend assets. Prepare the forward
package from the approved Git revision and its verified Vite build. The tool
rejects changed backend requirements: dependency changes need a separately built
and verified runtime, not reuse of an incompatible image.

Each package contains `release.json`, three Dockerfiles and
`compose.release.yaml`. Build each Dockerfile with `--network=none` and the exact
image tag recorded in `release.json`. Before deployment, render and inspect the
base Compose files plus the release override. The override uses `!override` to
remove host code mounts while keeping `/app/uploads`; database, Redis, ingress,
secrets and network configuration remain in the original Compose files.

Frontend build permissions are checked before any deployment. The release preparer
normalizes only the copied public `frontend-dist` to directories0755/files0644;
the verified input archive remains untouched and the package root stays0700.
The generated frontend Dockerfile reads `index.html` and every nested regular asset
as the `nginx` user. An unreadable file or untraversable directory fails the build;
do not remove this gate or compensate by changing permissions on private archives.
The frontend runtime must provide `nginx`, `/bin/sh`, `su`, `find` and `cat`, with
build privileges sufficient to switch to `nginx` (the current root-built nginx
runtime does). The gate does not change the image's inherited runtime `USER`.

Regression checks use a synthetic dist, an existing local runtime and disposable
uniquely tagged images; they neither start an HTTP server nor apply Compose:

```bash
cd backend
TEST_RELEASE_FRONTEND_RUNTIME=local/verified-nginx:explicit-tag \
  .venv/bin/pytest -m proxy tests/test_ops/test_prepare_release.py
```

Run this explicitly in addition to ordinary tests (`proxy` is excluded by default).
It proves a private0600/0700 input builds successfully, while changing one copied
nested asset back to0600 is rejected by the generated Dockerfile itself.

### Backend/worker source permissions and mandatory offline import gate

`prepare_release.py` normalizes only the extracted public backend code copy:
directories0755, regular files0644, already executable scripts0755. It keeps the
private release root0700 and preserves file contents and original inputs. Archive
links are rejected before extraction/normalization, so chmod cannot follow a link
outside the copied tree. No permissions of uploads, secrets or running services
are changed. This prevents implicit parent directories created0700 underumask077
from breaking a non-root runtime after Docker COPY.

After building the application images, **before any Compose apply**, run:

```bash
python3 ops/verify_release.py \
  --release /opt/finanse/webapp/releases/RELEASE \
  --backend-user "$TARGET_BACKEND_UID:$TARGET_BACKEND_GID" \
  --worker-user "$TARGET_WORKER_UID:$TARGET_WORKER_GID" \
  --timeout 60 > /private/evidence/offline-import-proof.json
```

Set these user values from the final rendered Compose (including hardening/active
overlays), never assume that the image's default USER is the deployed user. Both
UID and GID must be explicit positive numbers; root/named users are rejected.
The timeout is configurable. The verifier inspects local images, checks their OCI
revision against release.json and runs the **resolved image IDs**, not mutable tags.
It starts only uniquely named disposable containers: no mounts, no envfile/host
secrets, no network, read-only filesystem, all capabilities dropped, no-new-privileges.
The probe clears inherited image settings, avoids `/app/.env` by changing cwd, uses
synthetic test settings, reads all application sources and imports the appropriate
entrypoint (`app.main:app`, `app.worker.WorkerSettings`). It does not start lifespan,
an ASGI server or a worker, connect a database, apply migrations or call a provider.

An import/read-access failure, invalid revision/user, or timeout returns nonzero:
**STOP, do not run Compose up**. Check that the JSON says passed and that image IDs
and users still match the intended rollout. Rebuild/retag/user changes invalidate
the old proof: rerun the verifier. The verifier never deploys automatically, and
cannot prevent someone manually bypassing this required operator step.

Do not compensate with root, privileged mode, production credentials or a code
mount. A cached COPY may hide a directory-mode-only change; if necessary rebuild
without cache and rerun the gate, rather than accepting an earlier proof.

Offline Docker regression checks use only a local Python application runtime and
synthetic source files, with fresh uniquely tagged images and no existing services:

```bash
cd backend
TEST_RELEASE_BACKEND_RUNTIME=local/verified-python:explicit-tag \
TEST_RELEASE_FRONTEND_RUNTIME=local/verified-nginx:explicit-tag \
  .venv/bin/pytest -m proxy tests/test_ops/test_prepare_release.py
```

They verify privateumask077 preparation, real non-root users, unchanged content,
and rejection of unreadable nested source, broken imports and missing entrypoints;
the existing real-nginx access regressions remain part of the same gate.

Apply an approved package with the full Compose file list, for example:

```bash
docker compose -p finanse \
  -f /docker/finanse/compose.yaml \
  -f /docker/finanse/compose.prod.yaml \
  -f /opt/finanse/webapp/releases/RELEASE/compose.release.yaml \
  --env-file /docker/finanse/.env \
  up -d --no-deps --no-build backend worker frontend
```

Rollback uses the same command with the prepared rollback override. Do not use
`make up`, `make restart` or a Compose command omitting the active override:
that can restore the obsolete host-code mounts. Keep both package directories
and their images until a later approved release retires them. A container's
`org.opencontainers.image.revision` label and `release.json` identify live code;
the original host checkout is no longer the live application code. Legacy
backup `git_sha` metadata identifies that host checkout, so retain the release
metadata alongside deployment backups for application-version recovery.

Before applying: create a fresh encrypted backup, verify it on an isolated local
PostgreSQL restore target, confirm ledger balance, drain both old/new Redis
queues and record data-service container IDs. After applying: check all three
revision labels, absence of `/app` host mounts, unchanged data-service IDs,
HTTPS frontend/health, unauthenticated API rejection, and worker status/errors.
Do not rewrite historic transactions or run imports as a deployment step.
### Read-only release preflight

V2 classifies **source and schema changes**, not
external configuration-only changes. It never builds, creates, starts, stops,
removes, migrates, restores, rolls back, or publishes metadata. Reading a real
environment still needs separate approval. Local fake-tool tests do not grant it.

**Local implementation only, not certified for production.** First publish only
after approval and run CI for the exact SHA. Separately review and accept the
exact checker/runtime bundle, toolchain and optional tooling-scope proof.
Packaging, installation and real-environment readonly acceptance need explicit
permission; neither this procedure nor a test result grants it.

V1's historical `blocked/unknown_change_scope` remains valid evidence; V1 cannot
approve its replacement. Never rewrite metadata, adopt observations or filter
diffs to obtain success. Direct `release_preflight.py` denies unbootstrapped use.

#### Separate trust artifacts (outside candidate checkout)

- `prepare_preflight_bundle.prepare_bundle` only reads pinned local Git objects
  and an explicitly provided existing PyYAML6.0.3 distribution (pure Python,
  license included). It has no fetch/pip/install/approval step, refuses existing
  output and takes an explicit positive `max_output_bytes`. Dirty worktree code
  is not a source. This implementation does not create a real approved bundle.
- Bundle manifest version1 has exactly `version`, `source_revision`, `runtime`,
  `files`. Runtime fields: `python_path`, `python_sha256`, `stdlib_root`,
  `stdlib_tree_sha256`; members: relative `path`, `sha256`, `mode`. It includes
  launcher/checker/lock/vendor/license, excludes itself and all approval evidence.
  The bundle identifier is SHA256 of exact manifest bytes. Runtime tree digest
  covers sorted `[relative_path, sha256, mode]` for `.py/.pyc/.so` (excluding
  site/dist-packages), canonical JSON `ensure_ascii=True,separators=(",",":")`.
  Extra members, symlinks, unpinned zip imports or wrong ownership/modes block.
- Toolchain version1: `version`, `executables` (`git/docker/compose`, each
  canonical absolute `path`, `sha256`, integer `mode`, `uid:0`), `postgres`,
  `limits`. The ComposeV2 executable is called directly, not plugin discovery.
  PG fields: full `container_id`, `image_id`, numeric nonroot OS `uid`, `gid`,
  absolute `env_executable`, `psql_executable`, `socket_directory`, explicit
  `port`, `auth` (`peer` or existing `trust`). All limits must be explicit positive
  integers: `max_file_bytes`, `max_yaml_nodes`, `max_yaml_depth`, `max_output_bytes`.
- Optional tooling scope version1: `candidate`, all three `service_revisions`,
  `checker_bundle_sha256`, `review_report_sha256`, `review_result` equal to
  `accepted_no_open_critical_or_important`, and exact `changes`. Each change has
  `service`, `path`, `before_mode/blob`, `after_mode/blob`, `after_sha256` (individual
  fields are named `before_mode`, `before_blob`, etc.; null for missing sides).
   Only the explicit `CHECKER_SOURCE_PATHS`, `.opencode/command/deploy.md`, and
   the exact PR #11 transition of `.github/workflows/ci.yml` qualify.
   The workflow witness pins the old/new Git blobs, regular file modes and the
   SHA-256 of the new bytes. It remains blocked without the full approved proof;
   no other workflow change is allowed by it.
  Every pair/path/mode/blob/hash must match actual Git; no glob or omitted path.
  New candidate (even docs-only), any baseline or checker change invalidates proof.
- After actual administrator acceptance in authenticated conversation, an
  operator may record private receipt version1: `operator_reference`,
  `bundle_sha256`, `toolchain_sha256`, nullable `review_scope_sha256`, plus
  `version`. It is not a signature or an issuer. The launcher requires hashes
  independently supplied from that acceptance and equality with the receipt.
  Test receipts and review JSON are not approval.

Code bundles are root-owned0700, members non-group/world-writable, manifests0600.
External evidence/receipt stays in private0700 directories with files0600,
outside both bundle and candidate. Proposed locations (not already installed):
`/opt/finanse/webapp/tooling/preflight/<bundle-sha256>/` and
`/opt/finanse/webapp/approvals/preflight/<approval-id>/`.

Inputs must identify the exact current environment, not a future release overlay:

- A full candidate commit SHA and existing Git objects for each service revision.
  The candidate must descend from every running service revision. The tool does
  not fetch, import migrations, or trust dirty worktree source.
- Full ordered current Compose files (at least two), explicit project/env-file
  and PostgreSQL service. The active release override must be last; a deployment
   with a later hardening overlay is unsupported and blocks rather than
  silently dropping that overlay.
- An independently approved inventory, in a regular file mode0600 within an owned
  private0700 directory, plus its independently approved SHA256. Do not create
  an inventory by automatically adopting the observations that this check gathers.
  The tool has no issuer. Never copy an inventory or env values into this repo.

Inventory v1 has exactly `version: 1`, `project`, `active_release_sha256`,
`compose_files` (ordered `{path, sha256}` records), `env_file` (`{path, sha256}`),
`services` (exactly backend/worker/frontend, each `{container_id, image_id, revision}`)
and `postgres` (`{service, container_id, database, role}`). Paths are absolute,
container IDs/digests are64lowercase hex, image IDs are `sha256:` plus64hex, service
revisions are40hex. Input files and paths may not be symlinks. Extra or duplicate
inventory keys, changed digests, wrong ownership/modes and ambiguous observations
block; the check does not chmod, repair or adopt them.

Inventory v2 adds `compose_dependencies`, a list of exact `{path, sha256}`
records for the reachable `extends.file` inputs, not additional overlays.
It requires `--isolated-compose`; inventory v1 rejects that flag. Unlisted,
unused, duplicate or changed dependencies block. The renderer uses a private
path-preserving snapshot and has no daemon access. Its parent performs only
pinned read-only observations after successful render and help checks.

Inventory v2 may optionally include `retained_backend_migrators`: at most
three exact `{container_id, image_id, finished_at}` entries. Each must match
a historical, successfully exited backend one-off for the approved project,
including the exact Docker `FinishedAt` timestamp. The active backend must
be running and not a one-off. Unexpected, missing, duplicate or changed
containers block; never delete evidence to pass the check.

Isolated mode requires receipt v2: the v1 fields plus `isolated_readiness`
with exact `candidate`, `inventory_sha256`, `report_sha256`, `kernel_release`,
`kernel_version`, `machine` and `compose_sha256`. Obtain an independent review
of the readiness evidence for those inputs and a new administrator acceptance.
Do not reuse approvals for other candidates or package bytes. The approved
Compose must match the build qualified by the checker. Pass the exact private
report file outside the checkout and bundle; the launcher verifies its bytes
against `report_sha256` before importing the checker.

The adapter requires active metadata fields `release_status: "verified-live"`,
`service_revisions`, `application_images[S].id`, and `compose_override`. It never
falls back to a common `revision` or docs-only `git_tip`. **Compatibility with the
actual production metadata format has not been certified by the local tests.**
Verify it in a separately approved read-only acceptance before real use; absent
fields mean blocked, not permission to rewrite existing metadata.

#### Approved invocation and configuration subset

Example only after all separate approvals, using approved absolute paths and
pins (`PREFLIGHT_PYTHON` is the exact accepted Python3.12+ runtime). A trusted
supervisor/administrator must supply a clean startup environment, including no
LD_PRELOAD/LD_LIBRARY_PATH/PYTHON*; Python cannot undo loader code run before it.
The launcher itself must already be externally pinned before execution.

```bash
env -i PATH=/usr/bin:/bin HOME=/nonexistent \
  "$PREFLIGHT_PYTHON" -I -S -B "$APPROVED_BUNDLE/preflight_launcher.py" \
  --bundle "$APPROVED_BUNDLE" --bundle-sha256 "$APPROVED_BUNDLE_SHA256" \
  --toolchain "$APPROVED_TOOLCHAIN" --toolchain-sha256 "$APPROVED_TOOLCHAIN_SHA256" \
  --approval "$APPROVAL_RECEIPT" --check \
  --repository "$REPO" --candidate "$CANDIDATE_SHA" \
  --active-release "$ACTIVE_METADATA" \
  --approved-inventory "$APPROVED_INVENTORY" --inventory-sha256 "$APPROVED_INVENTORY_SHA256" \
  --project "$COMPOSE_PROJECT" --env-file "$CURRENT_ENV_FILE" \
  --compose-file "$CURRENT_BASE_COMPOSE" \
  --compose-file "$CURRENT_PROD_COMPOSE" \
  --compose-file "$CURRENT_RELEASE_COMPOSE" \
  --postgres-service "$POSTGRES_SERVICE" --scratch-directory "$PRIVATE_EMPTY_SCRATCH"
```

If applicable append all three: `--review-scope "$APPROVED_SCOPE"`
`--review-scope-sha256 "$APPROVED_SCOPE_SHA256" --review-report "$PRIVATE_REVIEW_REPORT"`.
Absent proof still blocks unknown tooling. These are not production credentials.
For inventory and receipt v2, also append
`--isolated-compose --readiness-report "$APPROVED_READINESS_REPORT"`.

Git/Docker/Compose use absolute pinned executable bytes and clean environments;
only `unix:///var/run/docker.sock` is supported. Remote/custom contexts block.
For inventory v1, consumed Compose/env bytes go into private0600 snapshots under an explicit
empty0700 scratch. `service.env_file` may reference only that approved env-file
(scalar/list); aliases, merge precedence and `!override/!reset` are preserved by
token edits. Original project directory and ordered merge stay unchanged.
Inventory v1 rejects `extends`; v2 only supports its approved dependency graph.
`include`, `label_file`, file-based secrets/configs, external env, unknown
file readers and unsupported forms block before rendering in both modes. Bind/build paths
are not read/copied. Missing pinned YAML runtime blocks; no ad hoc install.
Scratch paths containing `$` are unsupported. Snapshots may contain secrets:
never log/commit them. Cleanup removes only owned files, does not promise secure
erase; drift, write or cleanup failure suppresses success. Do not erase a
non-owned leftover to force green. Original identities and hashes are rechecked.

Run the real-binary isolation and equivalence tests separately from portable CI,
as a qualified operator on the intended Linux host:

```bash
ADVISOR_DEV_PYTHON="$QUALIFICATION_PYTHON" \
FINANSE_TEST_PINNED_COMPOSE="$PINNED_COMPOSE" \
  bash backend/tests/test_ops/run_preflight_linux_readiness.sh
```

Retain the generated synthetic JUnit evidence (two passing tests, no skips),
and have the readiness report bind it to the exact candidate, bundle,
inventory, host, and Compose pin. Synthetic qualification alone does not
authorize access to production.

Schema read is exactly one literal `SELECT version_num FROM alembic_version`
in the validated PG container/image as explicit numeric postgres OS UID:GID,
with separate inventory DB role. `env -i`, `HOME=/nonexistent`, no password/rc,
`PGPASSFILE=/dev/null`, explicit Unix socket/port, read-only transactions,
statement timeout10s and connect timeout5s. Socket bind/shared volumes block;
no root/password/TCP/auth-map fallback. Existing local peer mapping or trust
must already work; never change pg_hba to pass. Synthetic tests do not certify
actual auth or production compatibility. Each subprocess timeout is10s and
combined stdout/stderr is bounded; raw output/errors are not reported.

| Report action | Meaning (not authorization) |
|---|---|
| `no_rollout` | No service-relevant runtime changes; schema already current. Docs/test-only changes do not need identical image rebuilds or restarts. |
| `app_only` | Source/build changes need review for application rollout; schema already current. BO after a migration followed by application rollback must not repeat backfill. |
| `migration_then_app` | Current DB revision precedes candidate head in a supported linear graph. Separate exact migration approval is required. |
| `blocked` | Missing, unsupported, ambiguous or inconsistent evidence. Stop; do not infer a fallback action. |

Unknown paths (including unrelated ops/workflow changes), changed historical migrations,
branch/merge/dependency or nested migration layouts block. Backend/worker and
frontend source comparisons use their own revisions, not a shared latest Git tip.
Compose must support `up --no-start --no-deps --no-build` for application actions;
the check only reads help, never runs that command. Do not use unsupported
`create --no-deps`.

An exact separately approved tooling proof adds `approved_tooling_review` and
`reviewed_tooling_changes` without hiding paths or changing app/migration gates.
Tooling-only `no_rollout` is not tooling installation or application relabeling.
`.dockerignore` retains its existing runtime/build classification, not a new
tooling exemption. Report_version2 adds checker/toolchain/proof digests; blocked
reports suppress candidate/facts and reviewed scope.

The stdout JSON always has `authorized=false`, `production_ready=false`,
`source_binding="operator_approved_inventory"`, `content_provenance_verified=false`
and `external_configuration_reviewed=false`. OCI labels and operator-approved
expectations are not cryptographic content provenance. Exit0 means classification,
exit2 means blocked; a stale saved JSON or successful exit is never a deploy permit.
Separately review external env/mount/ingress changes, even for `no_rollout`.
This is not a health, login-cookie, ARQ, image-content or retention test.

Existing approval, CI/build, exact non-root image verification, backup/restore,
fencing/data retention, rollback compatibility and runtime observation gates all
remain required. Do not regenerate inventory just to turn a mismatch green.
Snapshots do not make the whole server observation atomic.
State changes invalidate the report: recheck under the existing deploy lock
immediately before any authorized mutation. The preflight itself is not a lock.

# Document safety package — staging and release gate (2026-10-22)

This package is **not deployed**. Do not apply the overlay or run a production
migration without approval of the exact release and a verified backup.

## Compatible rollout

1. Build a verified runtime containing Pillow/pypdf and this source revision.
2. Test migration `c7f8c620460d` on an isolated restored schema; it adds only
   document retry columns and an index. It does not enqueue/reset existing errors.
3. On an approved deployment, apply the migration before switching backend/worker;
   roll out backend, worker and frontend coherently. Old readers tolerate the new
   columns, but the new ORM cannot run against the old schema.
4. Nginx upload limit is 21 MiB (multipart envelope); file limit is 20 MiB.
   Deploy increased ingress admission only together with resource controls.
   Overrides of backend limits must be reconciled with Nginx and UI limits.
5. Terminal errors are not automatically reset by re-upload. Transient upstream
   errors retry after 30/120 seconds (three completed attempts total). Integrity,
   oversized result and permanent errors do not retry. The UI shows scheduled
   retry without promising completion. Operator recovery is a separate action.

## Limits and residual risks

Defaults in Settings: parser address space 512 MiB, CPU 10 s, wall time 15 s,
two children/API process and two seconds queue wait; PDF 100 pages, image 25M
pixels/one frame; OCR binary response 64 MiB and UTF-8 text 2 MiB. HTTP calls
request identity encoding and **reject unexpected compression before decoding**.
This intentionally trades compatibility for allocation safety; verify Stirling
honours identity in staging.

Storage admission uses a global PostgreSQL advisory lock and logical byte quotas
(1 GiB/user, 10 GiB total), plus 1 GiB free-space reserve. It is not a filesystem
quota: orphans, backup processes and other writers still consume disk. Deleting
metadata does not delete originals; GC/retention require a separate decision.
Do not run a cleanup as part of this release.

Parser subprocesses have sanitized environments but are **not a filesystem or
network sandbox**; a compromised parser could still use the process UID's access.
The application worker still holds a DB transaction over OCR and optional LLM.
Crash/cancellation recovery is retained; the attempt counter records completed
controlled failures, not every crashed invocation. Durable leases are deferred.

## Hardening candidate (not an automatic production override)

`ops/document-hardening.compose.yaml` is applied LAST after base, production and
immutable-release Compose files, only after staging acceptance. It requires
explicit verified `ADVISOR_UID/GID` and `STIRLING_UID/GID`. They must be non-root.
Starting resource budgets: backend 2 GiB/1 CPU/128 PID, worker 1 GiB/1 CPU/128 PID,
Stirling 2 GiB/2 CPU/256 PID; reserve host memory for DB, Redis and other services.

Before approval:
- Pin and verify a Stirling digest; no digest is invented or automatically changed.
- Verify non-root image startup and OCR for PDF/PNG/JPEG, required writable
  directories, Java/OCR caches and tmpfs capacity with the selected image.
  Read-only/noexec can expose image incompatibilities: fix and re-test explicitly,
  never silently drop protections.
- Verify non-root access to a COPY of uploads and the backup lock, including files
  owned by the old runtime. Do not recursively chown production originals here.
- Inspect merged config for root/privileged mode, published internal ports,
  Docker socket, unexpected writable mounts, code mounts and correct networks.
- Test representative worst-case allowed files at configured concurrency and
  measure RSS, queue time and OCR latency; container contract tests are not sizing.
- Verify rollback image compatibility and preserve new columns when rolling back
  application code. A downgrade removes retry metadata and needs separate approval.

## Verification commands in an isolated checkout

Run project `/test`, `/lint`, `/typecheck` definitions with explicit test DSN;
then `pytest -q tests/test_documents/test_proxy_upload.py
tests/test_documents/test_parser_container.py tests/test_document_hardening.py -m proxy`.
The `proxy` tests require Docker and create only disposable containers. Normal
pytest deselects these tests rather than silently claiming coverage; the CI workflow
runs them in a separate Docker-enabled step. Run frontend build and Playwright.

The hardening profile has only been structurally checked and generic container
limits smoke-tested. **No claim is made that the live Stirling image is compatible
with the new UID/read-only profile. That staging check is a deploy blocker.**

### Non-root follow-up staging (not deployed)

See `ops/upload-permissions/README.md` for the scoped ACL snapshot, rollback and
post-restore acceptance contract. No default ACL inheritance is approved.
Production application of ACLs remains a separate reviewed operator action;
the tests use only synthetic root-owned files. Do not run the helper image as an
application runtime. ACL rollback must abort on inventory/inode/hash/mode drift,
not delete newly created originals. Existing tar archives do not retain named
ACLs: reapply approved permissions and verify reads, atomic writes, duplicates
and backup-lock contention before starting non-root consumers after restore.
