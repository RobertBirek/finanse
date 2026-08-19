# Backup And Restore Verification

`ops/backup.sh` can send PostgreSQL and uploads snapshots to a configured
encrypted Restic repository. No Restic credentials are configured, and no
backup or restore has been performed.

## Setup

Install `restic`, PostgreSQL client tools, GNU tar, and configure the following
environment outside the repository and deployment manifests committed to Git:

- `BACKUP_WORKDIR`: private writable local directory for temporary snapshots.
- `DATABASE_URL_SYNC`: synchronous PostgreSQL DSN used only by `pg_dump`.
- `UPLOAD_DIR`: existing upload directory. It may be empty.
- `RESTIC_REPOSITORY`: encrypted offsite Restic repository location.
- `RESTIC_PASSWORD_FILE`: readable file containing the Restic repository password.

Run the backup with `make -C /docker/finanse backup`. The archive command is:

```bash
tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner -C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .
```

This produces deterministic upload archives, including for an empty directory.
Each snapshot includes a JSON manifest with the UTC creation timestamp, Git SHA,
Alembic revision, and SHA-256 checksums for `postgres.dump` and `uploads.tar.gz`.

Retention is seven daily, four weekly, and six monthly snapshots. The target RPO
is 24 hours and the target RTO is 2 hours. Redis is not backed up because it is
not a source of truth; PostgreSQL is the source of truth.

## Restore Drill

Run a monthly isolated restore drill with `make -C /docker/finanse restore-verify snapshot=<id>`.
The snapshot argument may be omitted by invoking the script directly, which uses
`latest`.

The verification script requires `RESTIC_REPOSITORY`, `RESTIC_PASSWORD_FILE`,
`RESTORE_DATABASE_URL_SYNC`, and `RESTORE_DIR`. It refuses to continue unless
the database host is exactly `127.0.0.1` or `localhost`, and the database name
ends in `_restore` or `_test`. This guard runs before Restic restore and before
`pg_restore`, preventing a production restore target.

The script restores into a private temporary directory, verifies manifest SHA-256
checksums before extracting uploads or touching the database, restores with
`pg_restore --clean --if-exists --no-owner`, migrates to the current Alembic head,
and checks that every financial transaction has at least two postings and a zero
base-PLN balance. `RESTORE_DIR/uploads` must not already exist, preventing an
existing upload set from being overwritten.
