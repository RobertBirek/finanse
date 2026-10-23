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
