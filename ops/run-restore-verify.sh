#!/usr/bin/env bash
set -euo pipefail
umask 077

snapshot_id="${RESTORE_SNAPSHOT_ID:-latest}"
if [[ "$snapshot_id" != "latest" && ! "$snapshot_id" =~ ^[0-9a-f]{8,64}$ ]]; then
  printf '%s\n' "Invalid restore snapshot identifier." >&2
  exit 1
fi

exec /opt/finanse/ops/restore-verify.sh "$snapshot_id"
