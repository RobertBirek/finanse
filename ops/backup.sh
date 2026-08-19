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
require_directory "$BACKUP_WORKDIR"
[[ -w "$BACKUP_WORKDIR" ]] || fail "The backup work directory is not writable."
require_directory "$UPLOAD_DIR"
require_readable_file "$RESTIC_PASSWORD_FILE"

repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
snapshot_dir="$(mktemp -d "$BACKUP_WORKDIR/backup.XXXXXXXX")"

printf '%s\n' "Creating database snapshot"
pg_dump --format=custom --file "$snapshot_dir/postgres.dump" "$DATABASE_URL_SYNC"

printf '%s\n' "Archiving uploads"
tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner -C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .

printf '%s\n' "Writing manifest"
git_sha="$(git -C "$repo_root" rev-parse HEAD)"
alembic_revision="$(cd "$repo_root/backend" && "$repo_root/backend/.venv/bin/alembic" current)"
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
