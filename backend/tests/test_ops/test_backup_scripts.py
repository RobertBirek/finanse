import stat
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SCRIPT = REPOSITORY_ROOT / "ops" / "backup.sh"
RESTORE_SCRIPT = REPOSITORY_ROOT / "ops" / "restore-verify.sh"
INFRA_MAKEFILE = Path("/docker/finanse/Makefile")


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
    ):
        assert f'require_env "{variable}"' in content

    assert (
        'pg_dump --format=custom --file "$snapshot_dir/postgres.dump" "$DATABASE_URL_SYNC"'
        in content
    )
    assert (
        'tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner '
        '-C "$UPLOAD_DIR" -czf "$snapshot_dir/uploads.tar.gz" .'
    ) in content
    assert 'git -C "$repo_root" rev-parse HEAD' in content
    assert '"$repo_root/backend/.venv/bin/alembic" current' in content
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

    assert RESTORE_SCRIPT.stat().st_mode & stat.S_IXUSR
    assert "#!/usr/bin/env bash" in content
    assert "set -euo pipefail" in content
    assert "umask 077" in content
    assert 'snapshot_id="${1:-latest}"' in content
    assert '[[ "$host" == "127.0.0.1" || "$host" == "localhost" ]]' in content
    assert '[[ "$database_name" =~ ^.+_(restore|test)$ ]]' in content
    assert content.index('[[ "$host" == "127.0.0.1" || "$host" == "localhost" ]]') < content.index(
        'restic restore "$snapshot_id"'
    )
    assert content.index('[[ "$database_name" =~ ^.+_(restore|test)$ ]]') < content.index(
        'pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_DATABASE_URL_SYNC"'
    )


def test_restore_script_verifies_snapshot_before_database_or_upload_changes():
    content = read_script(RESTORE_SCRIPT)

    assert 'restic restore "$snapshot_id" --target "$restore_workdir"' in content
    assert 'verify_checksum "postgres.dump" "$expected_postgres_sha256"' in content
    assert 'verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"' in content
    assert 'tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$RESTORE_DIR/uploads"' in content
    assert (
        'pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_DATABASE_URL_SYNC"' in content
    )
    assert (
        'DATABASE_URL="$async_database_url" "$repo_root/backend/.venv/bin/alembic" upgrade head'
        in content
    )
    assert "count(p.id) < 2" in content
    assert (
        "sum(CASE WHEN p.direction = 'debit' THEN p.base_amount_pln ELSE -p.base_amount_pln END) <> 0"
        in content
    )
    assert "RAISE EXCEPTION 'ledger invariant violation'" in content
    assert content.index(
        'verify_checksum "uploads.tar.gz" "$expected_uploads_sha256"'
    ) < content.index('tar -xzf "$snapshot_dir/uploads.tar.gz" -C "$RESTORE_DIR/uploads"')
    assert content.index(
        'verify_checksum "postgres.dump" "$expected_postgres_sha256"'
    ) < content.index(
        'pg_restore --clean --if-exists --no-owner --dbname "$RESTORE_DATABASE_URL_SYNC"'
    )
    assert "eval" not in content


def test_infrastructure_makefile_exposes_backup_and_restore_verification():
    content = INFRA_MAKEFILE.read_text()

    assert ".PHONY: up down restart logs ps backup restore-verify" in content
    assert "bash /opt/finanse/ops/backup.sh" in content
    assert 'bash /opt/finanse/ops/restore-verify.sh "$(snapshot)"' in content
    assert "sudo" not in content
