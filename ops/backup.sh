#!/usr/bin/env bash
set -euo pipefail

umask 077

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Missing required backup configuration."
}

require_directory() {
    local path="$1"
    [[ -d "$path" && -r "$path" ]] || fail "A required directory is unavailable."
}

require_readable_file() {
    local path="$1"
    [[ -f "$path" && -r "$path" ]] || fail "A required file is unavailable."
}

require_private_pgpassfile() {
    local path="$1"
    require_readable_file "$path"
    [[ "$(stat -c '%a' -- "$path")" == "600" ]] || fail "PGPASSFILE must have mode 0600."
}

snapshot_dir=""
cleanup() {
    if [[ -n "$snapshot_dir" && -d "$snapshot_dir" ]]; then
        rm -rf -- "$snapshot_dir"
    fi
}
trap cleanup EXIT INT TERM

require_env "BACKUP_WORKDIR"
require_env "DATABASE_URL_SYNC"
require_env "UPLOAD_DIR"
require_env "RESTIC_REPOSITORY"
require_env "RESTIC_PASSWORD_FILE"
require_env "PGPASSFILE"
require_directory "$BACKUP_WORKDIR"
[[ -w "$BACKUP_WORKDIR" ]] || fail "The backup work directory is not writable."
require_directory "$UPLOAD_DIR"
require_readable_file "$RESTIC_PASSWORD_FILE"
require_private_pgpassfile "$PGPASSFILE"

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
parse_postgres_url() {
    local connection_parts
    mapfile -t connection_parts < <(
        POSTGRES_CONNECTION_URL="$1" POSTGRES_PASSFILE="$PGPASSFILE" \
            python3 "$repo_root/ops/postgres_connection.py"
    )
    [[ ${#connection_parts[@]} -eq 5 ]] || fail "PostgreSQL connection URL is invalid."
    pg_host="${connection_parts[0]}"
    pg_port="${connection_parts[1]}"
    pg_user="${connection_parts[2]}"
    pg_database="${connection_parts[3]}"
    async_database_url="${connection_parts[4]}"
}
parse_postgres_url "$DATABASE_URL_SYNC"
snapshot_dir="$(mktemp -d "$BACKUP_WORKDIR/backup.XXXXXXXX")"

printf '%s\n' "Creating database snapshot"
PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    pg_dump --format=custom --file "$snapshot_dir/postgres.dump"

printf '%s\n' "Archiving uploads"
tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner -C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .

printf '%s\n' "Writing manifest"
git_sha="$(git -C "$repo_root" rev-parse HEAD)"
alembic_revision="$(PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    psql --set=ON_ERROR_STOP=1 --no-align --tuples-only -c "SELECT version_num FROM alembic_version")"
[[ -n "$alembic_revision" ]] || fail "Backup database has no Alembic revision."
postgres_dump_sha256="$(sha256sum "$snapshot_dir/postgres.dump" | cut -d ' ' -f 1)"
uploads_tar_gz_sha256="$(sha256sum "$snapshot_dir/uploads.tar.gz" | cut -d ' ' -f 1)"

printf '{\n  "created_at_utc": "%s",\n  "git_sha": "%s",\n  "alembic_revision": "%s",\n  "postgres_dump_sha256": "%s",\n  "uploads_tar_gz_sha256": "%s"\n}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$git_sha" "$alembic_revision" "$postgres_dump_sha256" "$uploads_tar_gz_sha256" \
    > "$snapshot_dir/manifest.json"

printf '%s\n' "Uploading encrypted snapshot"
restic backup "$snapshot_dir" --tag personal-advisor --tag postgres --tag uploads

printf '%s\n' "Applying retention"
restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6
printf '%s\n' "Backup complete"
