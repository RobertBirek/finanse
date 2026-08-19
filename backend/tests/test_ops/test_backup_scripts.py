import os
import stat
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SCRIPT = REPOSITORY_ROOT / "ops" / "backup.sh"
RESTORE_SCRIPT = REPOSITORY_ROOT / "ops" / "restore-verify.sh"


def read_script(path: Path) -> str:
    assert path.is_file(), f"missing script: {path}"
    return path.read_text()


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
    assert 'pg_dump --format=custom --file "$snapshot_dir/postgres.dump"' in content
    assert '"$DATABASE_URL_SYNC"' not in content.split("pg_dump", maxsplit=1)[1]
    assert (
        'tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner '
        '-C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .'
    ) in content
    assert 'git -C "$repo_root" rev-parse HEAD' in content
    assert "SELECT version_num FROM alembic_version" in content
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
    assert "restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6" in content
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
    assert '[[ "$pg_host" == "127.0.0.1" || "$pg_host" == "localhost" ]]' in content
    assert '[[ "$pg_database" =~ ^.+_(restore|test)$ ]]' in content
    assert 'require_private_pgpassfile "$PGPASSFILE"' in content
    assert empty_restore_dir_guard in content
    assert content.index(
        '[[ "$pg_host" == "127.0.0.1" || "$pg_host" == "localhost" ]]'
    ) < content.index('restic restore "$snapshot_id"')
    assert content.index('[[ "$pg_database" =~ ^.+_(restore|test)$ ]]') < content.index(
        'restic restore "$snapshot_id"'
    )
    assert content.index(empty_restore_dir_guard) < content.index('restic restore "$snapshot_id"')


def test_restore_script_verifies_snapshot_before_database_or_upload_changes():
    content = read_script(RESTORE_SCRIPT)

    assert 'restic restore "$snapshot_id" --target "$restore_workdir"' in content
    assert 'verify_checksum "postgres.dump" "$expected_postgres_sha256"' in content
    assert 'verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"' in content
    assert 'tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$RESTORE_DIR/uploads"' in content
    assert 'pg_restore --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"' in content
    assert '"$RESTORE_DATABASE_URL_SYNC"' not in content.split("pg_restore", maxsplit=1)[1]
    assert '"$repo_root/backend/.venv/bin/alembic" heads' in content
    assert 'manifest_alembic_revision="$(manifest_field "alembic_revision")"' in content
    assert '[[ "$restored_alembic_revision" == "$manifest_alembic_revision" ]]' in content
    assert (
        'DATABASE_URL="$async_database_url" "$repo_root/backend/.venv/bin/alembic" upgrade head'
        in content
    )
    assert '[[ "$upgraded_alembic_revision" == "$current_alembic_revision" ]]' in content
    assert content.index(
        'manifest_alembic_revision="$(manifest_field "alembic_revision")"'
    ) < content.index('pg_restore --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"')
    assert content.index(
        '[[ "$restored_alembic_revision" == "$manifest_alembic_revision" ]]'
    ) < content.index(
        'DATABASE_URL="$async_database_url" "$repo_root/backend/.venv/bin/alembic" upgrade head'
    )
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
    ) < content.index('tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$RESTORE_DIR/uploads"')
    assert content.index(
        'verify_checksum "postgres.dump" "$expected_postgres_sha256"'
    ) < content.index('pg_restore --clean --if-exists --no-owner "$snapshot_dir/postgres.dump"')
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
        "postgresql://user@localhost/finanse_restore?host=%2Ftmp%2Fsocket",
        0o600,
    )

    result = subprocess.run(
        [str(RESTORE_SCRIPT)], env=environment, capture_output=True, check=False, text=True
    )

    assert result.returncode != 0
    assert not marker.exists()


def test_restore_rejects_uri_password_before_restic_runs(tmp_path: Path):
    environment, marker = restore_environment(
        tmp_path, "postgresql://user:secret@localhost/finanse_restore", 0o600
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
