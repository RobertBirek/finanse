#!/usr/bin/env bash
set -euo pipefail

readonly UNIT_SOURCE_DIRECTORY="/opt/finanse/ops/systemd"
readonly UNIT_DESTINATION_DIRECTORY="/etc/systemd/system"
readonly WRAPPER_SOURCE="$UNIT_SOURCE_DIRECTORY/run-restore-drill.sh"
readonly WRAPPER_DESTINATION="/usr/local/lib/finanse/run-restore-drill.sh"
readonly UNITS=(
    finanse-backup.service
    finanse-backup.timer
    finanse-restore-verify.service
    finanse-restore-verify.timer
    finanse-operation-failure@.service
)

[[ "$(id -u)" -eq 0 ]] || { printf '%s\n' "Run as root." >&2; exit 1; }

for unit in "${UNITS[@]}"; do
    [[ -f "${UNIT_SOURCE_DIRECTORY}/${unit}" ]] || {
        printf '%s\n' "Required systemd unit is missing." >&2
        exit 1
    }
done
[[ -f "$WRAPPER_SOURCE" ]] || {
    printf '%s\n' "Required systemd unit is missing." >&2
    exit 1
}

systemd-analyze verify "${UNIT_SOURCE_DIRECTORY}"/*.service "${UNIT_SOURCE_DIRECTORY}"/*.timer
for unit in "${UNITS[@]}"; do
    install -o root -g root -m 0644 "${UNIT_SOURCE_DIRECTORY}/${unit}" "${UNIT_DESTINATION_DIRECTORY}/${unit}"
done
install -D -o root -g root -m 0750 "$WRAPPER_SOURCE" "$WRAPPER_DESTINATION"
install -d -o root -g root -m 0700 /docker/finanse/data/restore-drill
install -d -o root -g root -m 0700 /docker/finanse/data/restic-cache
systemctl daemon-reload
systemctl enable --now finanse-backup.timer finanse-restore-verify.timer
systemctl list-timers --all finanse-backup.timer finanse-restore-verify.timer
