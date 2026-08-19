#!/usr/bin/env bash
set -euo pipefail

umask 077

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

require_env() {
    local name="$1"
    [[ -n "${!name:-}" ]] || fail "Missing required restore configuration."
}

require_directory() {
    local path="$1"
    [[ -d "$path" && -r "$path" && -w "$path" ]] || fail "A required directory is unavailable."
}

require_readable_file() {
    local path="$1"
    [[ -f "$path" && -r "$path" ]] || fail "A required file is unavailable."
}

restore_workdir=""
cleanup() {
    if [[ -n "$restore_workdir" && -d "$restore_workdir" ]]; then
        rm -rf -- "$restore_workdir"
    fi
}
trap cleanup EXIT INT TERM

require_env "RESTIC_REPOSITORY"
require_env "RESTIC_PASSWORD_FILE"
require_env "RESTORE_DATABASE_URL_SYNC"
require_env "RESTORE_DIR"
require_readable_file "$RESTIC_PASSWORD_FILE"
require_directory "$RESTORE_DIR"

database_url_without_scheme="${RESTORE_DATABASE_URL_SYNC#*://}"
[[ "$database_url_without_scheme" != "$RESTORE_DATABASE_URL_SYNC" && "$database_url_without_scheme" == */* ]] \
    || fail "Restore database target is invalid."
authority="${database_url_without_scheme%%/*}"
host_port="${authority##*@}"
host="${host_port%%:*}"
database_name="${database_url_without_scheme#*/}"
database_name="${database_name%%\?*}"

[[ "$host" == "127.0.0.1" || "$host" == "localhost" ]] \
    || fail "Restore database host is not allowed."
[[ "$database_name" =~ ^.+_(restore|test)$ ]] \
    || fail "Restore database name is not allowed."

snapshot_id="${1:-latest}"
repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)"
restore_workdir="$(mktemp -d "${TMPDIR:-/tmp}/personal-advisor-restore.XXXXXXXX")"

printf '%s\n' "Restoring snapshot"
restic restore "$snapshot_id" --target "$restore_workdir"

manifest_path="$(find "$restore_workdir" -type f -name manifest.json -print -quit)"
[[ -n "$manifest_path" ]] || fail "Restored snapshot has no manifest."
snapshot_dir="$(dirname "$manifest_path")"
[[ -f "$snapshot_dir/postgres.dump" && -f "$snapshot_dir/uploads.tar.gz" ]] \
    || fail "Restored snapshot is incomplete."

manifest_field() {
    python3 - "$snapshot_dir/manifest.json" "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as manifest_file:
    value = json.load(manifest_file)[sys.argv[2]]
if not isinstance(value, str):
    raise ValueError("manifest field must be a string")
print(value)
PY
}

verify_checksum() {
    local filename="$1"
    local expected_checksum="$2"
    [[ "$expected_checksum" =~ ^[0-9a-f]{64}$ ]] || fail "Snapshot manifest checksum is invalid."
    local actual_checksum
    actual_checksum="$(sha256sum "$snapshot_dir/$filename" | cut -d ' ' -f 1)"
    [[ "$actual_checksum" == "$expected_checksum" ]] || fail "Snapshot checksum verification failed."
}

printf '%s\n' "Verifying snapshot"
expected_postgres_sha256="$(manifest_field "postgres_dump_sha256")"
expected_uploads_sha256="$(manifest_field "uploads_tar_gz_sha256")"
verify_checksum "postgres.dump" "$expected_postgres_sha256"
verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"

[[ ! -e "$RESTORE_DIR/uploads" ]] || fail "Restore uploads directory already exists."
mkdir "$RESTORE_DIR/uploads"
printf '%s\n' "Extracting uploads"
tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$RESTORE_DIR/uploads"

printf '%s\n' "Restoring database"
pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_DATABASE_URL_SYNC" "$snapshot_dir/postgres.dump"

async_database_url="$RESTORE_DATABASE_URL_SYNC"
if [[ "$async_database_url" == postgresql://* ]]; then
    async_database_url="postgresql+asyncpg://${async_database_url#postgresql://}"
fi
printf '%s\n' "Applying migrations"
(
    cd "$repo_root/backend"
    DATABASE_URL="$async_database_url" "$repo_root/backend/.venv/bin/alembic" upgrade head
)

printf '%s\n' "Checking ledger invariants"
psql "$RESTORE_DATABASE_URL_SYNC" --set=ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM postings p
        GROUP BY p.transaction_id
        HAVING count(p.id) < 2
            OR sum(CASE WHEN p.direction = 'debit' THEN p.base_amount_pln ELSE -p.base_amount_pln END) <> 0
    ) THEN
        RAISE EXCEPTION 'ledger invariant violation';
    END IF;
END
$$;
SQL
printf '%s\n' "Restore verification complete"
