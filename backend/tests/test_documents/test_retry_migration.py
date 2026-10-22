import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retry_migration_preserves_existing_documents_and_cycles(test_database):
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/c7f8c620460d_document_retry_metadata.py"
    )
    spec = importlib.util.spec_from_file_location("retry_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def cycle(connection):
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
            connection.execute(
                sa.text("""INSERT INTO documents
                (id, user_id, filename, original_name, mime_type, sha256_hash, size_bytes, storage_path)
                VALUES ('00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000002',
                        'a.pdf', 'a.pdf', 'application/pdf', 'hash', 20, 'aa/hash')""")
            )
            module.upgrade()
            row = connection.execute(
                sa.text("SELECT attempt_count, next_attempt_at, last_error_code FROM documents")
            ).one()
            assert tuple(row) == (0, None, None)
            module.downgrade()
            assert connection.scalar(sa.text("SELECT count(*) FROM documents")) == 1
            module.upgrade()

    async with test_database.begin() as conn:
        await conn.run_sync(cycle)
