#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly COMPOSE_DIRECTORY="/docker/finanse"
readonly RESTORE_DIRECTORY="$COMPOSE_DIRECTORY/data/restore-drill"
readonly RESTORE_DATABASE="finanse_restore"

fail() { printf '%s\n' "$1" >&2; exit 1; }

[[ -d "$COMPOSE_DIRECTORY" ]] || fail "Compose directory is unavailable."
[[ -f "$COMPOSE_DIRECTORY/.env" ]] || fail "Compose environment is unavailable."
[[ -f "$COMPOSE_DIRECTORY/secrets/backup.env" ]] || fail "Backup environment is unavailable."

set -a
. "$COMPOSE_DIRECTORY/.env"
. "$COMPOSE_DIRECTORY/secrets/backup.env"
set +a

RESTORE_DIR="$RESTORE_DIRECTORY"
mapfile -t restore_parts < <(
  POSTGRES_CONNECTION_URL="postgresql://${POSTGRES_USER}@127.0.0.1:55431/${RESTORE_DATABASE}" POSTGRES_PASSFILE="$PGPASSFILE" python3 /opt/finanse/ops/postgres_connection.py
)
[[ ${#restore_parts[@]} -eq 5 ]] || fail "Restore connection is invalid."
restore_host="${restore_parts[0]}"
restore_port="${restore_parts[1]}"
restore_user="${restore_parts[2]}"
restore_database="${restore_parts[3]}"

[[ "$RESTORE_DIR" == "$RESTORE_DIRECTORY" ]] || fail "Restore directory is not allowed."
[[ "$restore_host" == "127.0.0.1" ]] || fail "Restore host is not allowed."
[[ "$restore_database" == "$RESTORE_DATABASE" ]] || fail "Restore database is not allowed."
[[ -d "$RESTORE_DIRECTORY" ]] || fail "Restore directory is unavailable."
[[ -z "$(find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1 -print -quit)" ]] || fail "Restore directory is not empty."

restore_database_created=false
cleanup() {
  local exit_code=$?

  if [[ "$exit_code" -ne 0 && "$restore_database_created" == true ]]; then
    dropdb --if-exists --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database" || true
    if [[ -d "$RESTORE_DIRECTORY/uploads" ]]; then
      rm -rf -- "$RESTORE_DIRECTORY/uploads" || true
    fi
  fi

  return "$exit_code"
}
trap cleanup EXIT

createdb --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database"
restore_database_created=true
FINANSE_OPERATION_LOCK_HELD=1 make -C "$COMPOSE_DIRECTORY" restore-verify snapshot=latest
dropdb --if-exists --host "$restore_host" --port "$restore_port" --username "$restore_user" "$restore_database"
[[ -d "$RESTORE_DIRECTORY/uploads" ]] || fail "Restore uploads are missing."
[[ -z "$(find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1 ! -name uploads -print -quit)" ]] || fail "Unexpected restore output."
rm -rf -- "$RESTORE_DIRECTORY/uploads"
restore_database_created=false
trap - EXIT
