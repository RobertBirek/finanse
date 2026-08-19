# Backup And Restore Verification

`ops/backup.sh` can send PostgreSQL and uploads snapshots to a configured
encrypted Restic repository. No Restic credentials are configured, and no
backup or restore has been performed.

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
make -C /docker/finanse -n restore-verify snapshot=<id>
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

Run a monthly isolated restore drill with `make -C /docker/finanse restore-verify snapshot=<id>`.
The snapshot argument may be omitted by invoking the script directly, which uses
`latest`.

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
