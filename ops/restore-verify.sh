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

require_private_pgpassfile() {
    local path="$1"
    require_readable_file "$path"
    [[ "$(stat -c '%a' -- "$path")" == "600" ]] || fail "PGPASSFILE must have mode 0600."
}

restore_workdir=""
restore_staging_dir=""
cleanup() {
    local exit_code="$?"
    if [[ "$exit_code" -ne 0 && -n "$restore_staging_dir" ]]; then
        rm -rf -- "$restore_staging_dir"
    fi
    if [[ -n "$restore_workdir" && -d "$restore_workdir" ]]; then
        rm -rf -- "$restore_workdir"
    fi
    return "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

require_env "RESTIC_REPOSITORY"
require_env "RESTIC_PASSWORD_FILE"
require_env "RESTORE_DATABASE_URL_SYNC"
require_env "RESTORE_DIR"
require_env "PGPASSFILE"
require_readable_file "$RESTIC_PASSWORD_FILE"
require_private_pgpassfile "$PGPASSFILE"
require_directory "$RESTORE_DIR"
[[ -z "$(find "$RESTORE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] \
    || fail "Restore directory must be empty."

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
parse_postgres_url "$RESTORE_DATABASE_URL_SYNC"

[[ "$pg_host" == "127.0.0.1" ]] \
    || fail "Restore database host is not allowed."
[[ "$pg_database" =~ ^.+_(restore|test)$ ]] \
    || fail "Restore database name is not allowed."

snapshot_id="${1:-latest}"
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
manifest_alembic_revision="$(manifest_field "alembic_revision")"
[[ -n "$manifest_alembic_revision" ]] || fail "Snapshot manifest has no Alembic revision."

restore_staging_dir="$(mktemp -d "$RESTORE_DIR/.restore-run.XXXXXX")"
mkdir "$restore_staging_dir/uploads"
printf '%s\n' "Extracting uploads"
tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$restore_staging_dir/uploads"

printf '%s\n' "Restoring database"
PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    pg_restore --dbname="$pg_database" --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"

printf '%s\n' "Checking schema revision"
restored_alembic_revision="$(PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    psql --set=ON_ERROR_STOP=1 --no-align --tuples-only -c "SELECT version_num FROM alembic_version")"
[[ "$restored_alembic_revision" == "$manifest_alembic_revision" ]] \
    || fail "Restored database revision does not match the snapshot manifest."

printf '%s\n' "Applying migrations"
(
    cd "$repo_root/backend"
    env -i PATH="$PATH" HOME="${HOME:-/tmp}" DATABASE_URL="$async_database_url" \
        "$repo_root/backend/.venv/bin/alembic" upgrade head
)

mapfile -t alembic_heads < <(cd "$repo_root/backend" && "$repo_root/backend/.venv/bin/alembic" heads)
[[ ${#alembic_heads[@]} -eq 1 ]] || fail "Repository must have exactly one Alembic head."
current_alembic_revision="$(cut -d ' ' -f 1 <<<"${alembic_heads[0]}")"
upgraded_alembic_revision="$(PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    psql --set=ON_ERROR_STOP=1 --no-align --tuples-only -c "SELECT version_num FROM alembic_version")"
[[ "$upgraded_alembic_revision" == "$current_alembic_revision" ]] \
    || fail "Migrated database revision does not match the repository head."

printf '%s\n' "Checking ledger invariants"
PGHOST="$pg_host" PGPORT="$pg_port" PGUSER="$pg_user" PGDATABASE="$pg_database" PGPASSFILE="$PGPASSFILE" \
    psql --set=ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM financial_transactions transaction
        LEFT JOIN postings posting ON posting.transaction_id = transaction.id
        GROUP BY transaction.id
        HAVING count(posting.id) < 2
            OR COALESCE(SUM(CASE WHEN posting.direction = 'debit' THEN posting.base_amount_pln ELSE -posting.base_amount_pln END), 0) <> 0
    ) THEN
        RAISE EXCEPTION 'ledger invariant violation';
    END IF;
END
$$;
SQL
[[ ! -e "$RESTORE_DIR/uploads" ]] || fail "Restore uploads directory appeared during verification."
mv "$restore_staging_dir/uploads" "$RESTORE_DIR/uploads"
rmdir "$restore_staging_dir"
restore_staging_dir=""
printf '%s\n' "Restore verification complete"
