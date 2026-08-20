import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SCRIPT = REPOSITORY_ROOT / "ops" / "backup.sh"
RESTORE_SCRIPT = REPOSITORY_ROOT / "ops" / "restore-verify.sh"
SYSTEMD_DIRECTORY = REPOSITORY_ROOT / "ops" / "systemd"
RESTORE_DRILL_WRAPPER = SYSTEMD_DIRECTORY / "run-restore-drill.sh"
BACKUP_TIMER = SYSTEMD_DIRECTORY / "finanse-backup.timer"
RESTORE_TIMER = SYSTEMD_DIRECTORY / "finanse-restore-verify.timer"
BACKUP_SERVICE = SYSTEMD_DIRECTORY / "finanse-backup.service"
RESTORE_SERVICE = SYSTEMD_DIRECTORY / "finanse-restore-verify.service"
FAILURE_SERVICE = SYSTEMD_DIRECTORY / "finanse-operation-failure@.service"
INSTALLER = SYSTEMD_DIRECTORY / "install-timers.sh"


def read_script(path: Path) -> str:
    assert path.is_file(), f"missing script: {path}"
    return path.read_text()


def test_timer_installer_verifies_then_installs_only_known_units() -> None:
    content = read_script(INSTALLER)

    assert "set -euo pipefail" in content
    assert '[[ "$(id -u)" -eq 0 ]]' in content
    assert "systemd-analyze verify" in content
    assert "install -o root -g root -m 0644" in content
    assert "systemctl daemon-reload" in content
    assert "systemctl enable --now finanse-backup.timer finanse-restore-verify.timer" in content
    assert "rm -rf" not in content
    assert "secrets/" not in content


def test_backup_timer_has_daily_schedule_and_service():
    content = read_script(BACKUP_TIMER)

    assert "OnCalendar=*-*-* 02:30:00 Europe/Warsaw" in content
    assert "Persistent=true" in content
    assert "Unit=finanse-backup.service" in content
    assert "WantedBy=timers.target" in content


def test_restore_timer_has_monthly_schedule_and_service():
    content = read_script(RESTORE_TIMER)

    assert "OnCalendar=Sun *-*-01..07 04:30:00 Europe/Warsaw" in content
    assert "Persistent=true" in content
    assert "Unit=finanse-restore-verify.service" in content
    assert "WantedBy=timers.target" in content


def test_scheduled_services_protect_secrets_and_serialise_operations():
    for service in (BACKUP_SERVICE, RESTORE_SERVICE, FAILURE_SERVICE):
        content = read_script(service)

        assert "SECRET_KEY=" not in content
        assert "PASSWORD=" not in content
        assert "RESTIC_PASSWORD=" not in content

    for service in (BACKUP_SERVICE, RESTORE_SERVICE):
        content = read_script(service)

        assert "/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock" in content
        assert "TimeoutStartSec=2h" in content
        assert "NoNewPrivileges=true" in content
        assert "PrivateTmp=true" in content
        assert "ProtectSystem=strict" in content
        assert "ProtectHome=true" in content
        assert "UMask=0077" in content
        assert "OnFailure=finanse-operation-failure@%n.service" in content

    backup_content = read_script(BACKUP_SERVICE)
    assert (
        "ExecStart=/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock "
        "/usr/bin/make -C /docker/finanse backup"
    ) in backup_content
    assert (
        "ReadWritePaths=/docker/finanse/data/backups /docker/finanse/data/uploads /run/lock"
        in backup_content
    )

    restore_content = read_script(RESTORE_SERVICE)
    assert (
        "ExecStart=/usr/bin/flock -w 900 /run/lock/finanse-backup-restore.lock "
        "/opt/finanse/ops/systemd/run-restore-drill.sh"
    ) in restore_content
    assert "ReadWritePaths=/docker/finanse/data/restore-drill /run/lock" in restore_content

    failure_content = read_script(FAILURE_SERVICE)
    assert (
        "ExecStart=/usr/bin/logger --priority user.err --tag finanse-operation-failure "
        '"Scheduled operation %I failed; inspect journalctl -u %I"'
    ) in failure_content


def test_restore_drill_wrapper_is_private_and_runs_only_the_guarded_target() -> None:
    content = read_script(RESTORE_DRILL_WRAPPER)

    assert RESTORE_DRILL_WRAPPER.stat().st_mode & stat.S_IXUSR
    assert "set -euo pipefail" in content
    assert "umask 077" in content
    assert 'readonly COMPOSE_DIRECTORY="/docker/finanse"' in content
    assert 'readonly RESTORE_DIRECTORY="$COMPOSE_DIRECTORY/data/restore-drill"' in content
    assert 'readonly RESTORE_DATABASE="finanse_restore"' in content
    assert 'make -C "$COMPOSE_DIRECTORY" restore-verify snapshot=latest' in content
    assert content.index("restore-verify snapshot=latest") < content.index("dropdb")
    assert content.index("dropdb") < content.index('rm -rf -- "$RESTORE_DIRECTORY/uploads"')


def test_restore_drill_wrapper_refuses_any_unexpected_restore_target() -> None:
    content = read_script(RESTORE_DRILL_WRAPPER)

    assert '[[ "$RESTORE_DIR" == "$RESTORE_DIRECTORY" ]]' in content
    assert '[[ "$restore_host" == "127.0.0.1" ]]' in content
    assert '[[ "$restore_database" == "$RESTORE_DATABASE" ]]' in content
    assert 'find "$RESTORE_DIRECTORY" -mindepth 1 -maxdepth 1' in content


def test_backup_script_is_executable_and_uses_private_temporary_snapshot():
    content = read_script(BACKUP_SCRIPT)

    assert BACKUP_SCRIPT.stat().st_mode & stat.S_IXUSR
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "umask 077" in content
    assert 'mktemp -d "$BACKUP_WORKDIR/backup.XXXXXXXX"' in content
    assert "trap cleanup EXIT INT TERM" in content
    assert 'rm -rf -- "$snapshot_dir"' in content


def test_backup_script_requires_inputs_and_creates_versioned_snapshot():
    content = read_script(BACKUP_SCRIPT)

    for variable in (
        "BACKUP_WORKDIR",
        "DATABASE_URL_SYNC",
        "UPLOAD_DIR",
        "RESTIC_REPOSITORY",
        "RESTIC_PASSWORD_FILE",
        "PGPASSFILE",
    ):
        assert f'require_env "{variable}"' in content

    assert 'parse_postgres_url "$DATABASE_URL_SYNC"' in content
    assert "ops/postgres_connection.py" in content
    assert (
        'pg_dump --serializable-deferrable --format=custom --file "$snapshot_dir/postgres.dump"'
        in content
    )
    assert '"$DATABASE_URL_SYNC"' not in content.split("pg_dump", maxsplit=1)[1]
    assert (
        'tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner '
        '-C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .'
    ) in content
    assert 'git -C "$repo_root" rev-parse HEAD' in content
    assert "SELECT version_num FROM alembic_version" in content
    assert 'flock "$UPLOAD_DIR/.backup.lock" tar' in content
    for field in (
        "created_at_utc",
        "git_sha",
        "alembic_revision",
        "postgres_dump_sha256",
        "uploads_tar_gz_sha256",
    ):
        assert f'"{field}"' in content


def test_backup_script_sends_snapshot_to_restic_and_applies_retention():
    content = read_script(BACKUP_SCRIPT)

    assert (
        'restic backup "$snapshot_dir" --tag personal-advisor --tag postgres --tag uploads'
        in content
    )
    assert (
        "restic forget --prune --tag personal-advisor --group-by tags --keep-daily 7 "
        "--keep-weekly 4 --keep-monthly 6"
    ) in content
    assert "eval" not in content


def test_restore_script_is_executable_and_fails_closed_before_restore():
    content = read_script(RESTORE_SCRIPT)
    empty_restore_dir_guard = (
        '[[ -z "$(find "$RESTORE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]'
    )

    assert RESTORE_SCRIPT.stat().st_mode & stat.S_IXUSR
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "umask 077" in content
    assert 'snapshot_id="${1:-latest}"' in content
    assert 'parse_postgres_url "$RESTORE_DATABASE_URL_SYNC"' in content
    assert '[[ "$pg_host" == "127.0.0.1" ]]' in content
    assert '[[ "$pg_database" =~ ^.+_(restore|test)$ ]]' in content
    assert 'require_private_pgpassfile "$PGPASSFILE"' in content
    assert empty_restore_dir_guard in content
    assert 'restore_staging_dir="$(mktemp -d "$RESTORE_DIR/.restore-run.XXXXXX")"' in content
    assert 'if [[ "$exit_code" -ne 0 && -n "$restore_staging_dir" ]]' in content
    assert content.index('[[ "$pg_host" == "127.0.0.1" ]]') < content.index(
        'restic restore "$snapshot_id"'
    )
    assert content.index('[[ "$pg_database" =~ ^.+_(restore|test)$ ]]') < content.index(
        'restic restore "$snapshot_id"'
    )
    assert content.index(empty_restore_dir_guard) < content.index('restic restore "$snapshot_id"')


def test_restore_script_verifies_snapshot_before_database_or_upload_changes():
    content = read_script(RESTORE_SCRIPT)

    assert 'restic restore "$snapshot_id" --target "$restore_workdir"' in content
    assert 'verify_checksum "postgres.dump" "$expected_postgres_sha256"' in content
    assert 'verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"' in content
    assert 'tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$restore_staging_dir/uploads"' in content
    assert (
        'pg_restore --dbname="$pg_database" --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"'
        in content
    )
    assert '"$RESTORE_DATABASE_URL_SYNC"' not in content.split("pg_restore", maxsplit=1)[1]
    assert '"$repo_root/backend/.venv/bin/alembic" heads' in content
    assert 'manifest_alembic_revision="$(manifest_field "alembic_revision")"' in content
    assert '[[ "$restored_alembic_revision" == "$manifest_alembic_revision" ]]' in content
    assert 'env -i PATH="$PATH" HOME="${HOME:-/tmp}" DATABASE_URL="$async_database_url"' in content
    assert '"$repo_root/backend/.venv/bin/alembic" upgrade head' in content
    assert '[[ "$upgraded_alembic_revision" == "$current_alembic_revision" ]]' in content
    assert content.index(
        'manifest_alembic_revision="$(manifest_field "alembic_revision")"'
    ) < content.index(
        'pg_restore --dbname="$pg_database" --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"'
    )
    assert content.index(
        '[[ "$restored_alembic_revision" == "$manifest_alembic_revision" ]]'
    ) < content.index('env -i PATH="$PATH" HOME="${HOME:-/tmp}" DATABASE_URL="$async_database_url"')
    assert "FROM financial_transactions transaction" in content
    assert "LEFT JOIN postings posting ON posting.transaction_id = transaction.id" in content
    assert "GROUP BY transaction.id" in content
    assert "count(posting.id) < 2" in content
    assert (
        "COALESCE(SUM(CASE WHEN posting.direction = 'debit' THEN posting.base_amount_pln "
        "ELSE -posting.base_amount_pln END), 0) <> 0" in content
    )
    assert "RAISE EXCEPTION 'ledger invariant violation'" in content
    assert content.index(
        'verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"'
    ) < content.index('tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$restore_staging_dir/uploads"')
    assert content.index(
        'verify_checksum "postgres.dump" "$expected_postgres_sha256"'
    ) < content.index(
        'pg_restore --dbname="$pg_database" --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"'
    )
    assert "eval" not in content


def restore_environment(
    tmp_path: Path, database_url: str, pgpass_mode: int
) -> tuple[dict[str, str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "restic-ran"
    fake_restic = fake_bin / "restic"
    fake_restic.write_text('#!/usr/bin/env bash\n: > "$RESTIC_MARKER"\n')
    fake_restic.chmod(0o700)
    pgpassfile = tmp_path / "pgpass"
    pgpassfile.write_text("localhost:5432:*:user:password\n")
    pgpassfile.chmod(pgpass_mode)
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "RESTIC_MARKER": str(marker),
        "RESTIC_REPOSITORY": "test-repository",
        "RESTIC_PASSWORD_FILE": str(pgpassfile),
        "RESTORE_DATABASE_URL_SYNC": database_url,
        "RESTORE_DIR": str(restore_dir),
        "PGPASSFILE": str(pgpassfile),
    }
    return environment, marker


def test_restore_rejects_uri_query_before_restic_runs(tmp_path: Path):
    environment, marker = restore_environment(
        tmp_path,
        "postgresql://user@127.0.0.1/finanse_restore?host=%2Ftmp%2Fsocket",
        0o600,
    )

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_restore_rejects_localhost_before_restic_runs(tmp_path: Path):
    environment, marker = restore_environment(
        tmp_path, "postgresql://user@localhost/finanse_restore", 0o600
    )

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_restore_rejects_uri_password_before_restic_runs(tmp_path: Path):
    environment, marker = restore_environment(
        tmp_path, "postgresql://user:secret@127.0.0.1/finanse_restore", 0o600
    )

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_restore_rejects_non_private_pgpassfile_before_restic_runs(tmp_path: Path):
    environment, marker = restore_environment(
        tmp_path, "postgresql://user@localhost/finanse_restore", 0o644
    )

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def write_fake_command(directory: Path, name: str, body: str) -> None:
    command = directory / name
    command.write_text(f"#!/usr/bin/env bash\nset -euo pipefail\n{body}\n")
    command.chmod(0o700)


def test_backup_mocked_commands_run_in_snapshot_order_without_secrets(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    order_log = tmp_path / "order"
    manifest_copy = tmp_path / "manifest.json"
    write_fake_command(
        fake_bin,
        "pg_dump",
        'for ((i=1; i <= $#; i++)); do if [[ "${!i}" == "--file" ]]; then j=$((i + 1)); printf dump > "${!j}"; fi; done\nprintf "pg_dump\\n" >> "$ORDER_LOG"',
    )
    write_fake_command(
        fake_bin,
        "tar",
        'for ((i=1; i <= $#; i++)); do if [[ "${!i}" == "-czf" ]]; then j=$((i + 1)); printf uploads > "${!j}"; fi; done\nprintf "tar\\n" >> "$ORDER_LOG"',
    )
    write_fake_command(fake_bin, "psql", "printf oldrev\n")
    write_fake_command(
        fake_bin,
        "restic",
        'printf "restic\\n" >> "$ORDER_LOG"\nif [[ "$1" == "backup" ]]; then cp "$2/manifest.json" "$MANIFEST_COPY"; fi',
    )
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    pgpass = tmp_path / "pgpass"
    pgpass.write_text("127.0.0.1:5432:*:user:secret\n")
    pgpass.chmod(0o600)
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "ORDER_LOG": str(order_log),
        "MANIFEST_COPY": str(manifest_copy),
        "BACKUP_WORKDIR": str(tmp_path),
        "DATABASE_URL_SYNC": "postgresql://user@127.0.0.1/finanse",
        "UPLOAD_DIR": str(uploads),
        "RESTIC_REPOSITORY": "test-repository",
        "RESTIC_PASSWORD_FILE": str(pgpass),
        "PGPASSFILE": str(pgpass),
    }

    result = subprocess.run(
        [str(BACKUP_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode == 0
    assert order_log.read_text().splitlines()[:3] == ["pg_dump", "tar", "restic"]
    assert "secret" not in manifest_copy.read_text()


def test_failed_pg_restore_removes_only_created_uploads(tmp_path: Path):
    environment, _ = restore_environment(
        tmp_path, "postgresql://user@127.0.0.1/finanse_restore", 0o600
    )
    fake_bin = Path(environment["PATH"].split(":", maxsplit=1)[0])
    payload = tmp_path / "payload"
    payload.mkdir()
    dump = payload / "postgres.dump"
    archive = payload / "uploads.tar.gz"
    dump.write_bytes(b"dump")
    archive.write_bytes(b"uploads")
    (payload / "manifest.json").write_text(
        json.dumps(
            {
                "alembic_revision": "oldrev",
                "postgres_dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                "uploads_tar_gz_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        )
    )
    write_fake_command(
        fake_bin,
        "restic",
        'target=""; for ((i=1; i <= $#; i++)); do if [[ "${!i}" == "--target" ]]; then j=$((i + 1)); target="${!j}"; fi; done\nmkdir -p "$target/snapshot"\ncp "$RESTIC_PAYLOAD"/* "$target/snapshot/"',
    )
    write_fake_command(fake_bin, "tar", "exit 0")
    write_fake_command(
        fake_bin,
        "pg_restore",
        '[[ "$*" == *"--dbname=finanse_restore"* ]] || exit 2\n[[ "$*" == *"postgres.dump"* ]] || exit 2\n[[ "$*" != *"postgresql://"* ]] || exit 2\nmkdir -p "$RESTORE_DIR/uploads"; : > "$RESTORE_DIR/uploads/sentinel"; exit 1',
    )
    environment["RESTIC_PAYLOAD"] = str(payload)

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert (Path(environment["RESTORE_DIR"]) / "uploads" / "sentinel").exists()


def test_checksum_mismatch_prevents_pg_restore(tmp_path: Path):
    environment, _ = restore_environment(
        tmp_path, "postgresql://user@127.0.0.1/finanse_restore", 0o600
    )
    fake_bin = Path(environment["PATH"].split(":", maxsplit=1)[0])
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "postgres.dump").write_bytes(b"changed")
    (payload / "uploads.tar.gz").write_bytes(b"uploads")
    (payload / "manifest.json").write_text(
        json.dumps(
            {
                "alembic_revision": "oldrev",
                "postgres_dump_sha256": "0" * 64,
                "uploads_tar_gz_sha256": hashlib.sha256(b"uploads").hexdigest(),
            }
        )
    )
    marker = tmp_path / "pg-restore-ran"
    write_fake_command(
        fake_bin,
        "restic",
        'target=""; for ((i=1; i <= $#; i++)); do if [[ "${!i}" == "--target" ]]; then j=$((i + 1)); target="${!j}"; fi; done\nmkdir -p "$target/snapshot"\ncp "$RESTIC_PAYLOAD"/* "$target/snapshot/"',
    )
    write_fake_command(fake_bin, "pg_restore", ': > "$PG_RESTORE_MARKER"')
    environment["RESTIC_PAYLOAD"] = str(payload)
    environment["PG_RESTORE_MARKER"] = str(marker)

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()
