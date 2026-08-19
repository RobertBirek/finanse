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
continue unless the database host is exactly `127.0.0.1` or `localhost`, and the
database name ends in `_restore` or `_test`. These guards run before Restic
restore and before `pg_restore`, preventing a production restore target.

The script restores into a private temporary directory, verifies manifest SHA-256
checksums before extracting uploads or touching the database, restores with
`pg_restore --clean --if-exists --no-owner`, then compares the restored Alembic
revision with the repository's static `alembic heads` result. A mismatch fails
with an instruction to run an upgrade separately through controlled runtime
configuration; this script does not create an async command-line DSN. It also
checks that every financial transaction has at least two postings and a zero
base-PLN balance. `RESTORE_DIR/uploads` must not already exist, preventing an
existing upload set from being overwritten.
