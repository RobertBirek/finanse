import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

import app.main  # noqa: F401 - register metadata for isolated schema fixtures


@pytest.mark.integration
async def test_archive_upgrade_retains_legacy_rows_and_refuses_state_losing_downgrade(
    test_database,
):
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2f4b2c2a527c_document_archive_lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location("archive_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def cycle(connection):
        connection.execute(text("ALTER TABLE documents DROP COLUMN archived_at"))
        connection.execute(
            text("""INSERT INTO documents (id,user_id,filename,original_name,mime_type,sha256_hash,size_bytes,storage_path)
          VALUES ('00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','synthetic','synthetic','application/pdf',:sha,1,'synthetic')"""),
            {"sha": "0" * 64},
        )
        before = dict(connection.execute(text("SELECT * FROM documents")).mappings().one())
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        after = dict(connection.execute(text("SELECT * FROM documents")).mappings().one())
        assert after.pop("archived_at") is None and after == before
        connection.execute(text("UPDATE documents SET archived_at=CURRENT_TIMESTAMP"))
        with (
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match="archive"),
        ):
            module.downgrade()
        assert (
            connection.execute(text("SELECT archived_at FROM documents")).scalar_one() is not None
        )

    async with test_database.begin() as connection:
        await connection.run_sync(cycle)
