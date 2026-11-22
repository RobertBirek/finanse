from uuid import uuid4

import pytest

from tests import migration_fixtures

owned_migration_database = migration_fixtures.owned_migration_database


@pytest.mark.migration
async def test_auto_post_migration_leaves_existing_sources_unenrolled_and_preserves_grants(
    owned_migration_database: migration_fixtures.MigrationDatabase,
) -> None:
    database = owned_migration_database
    previous, current = "e5a46dc32772", "5f1d54d40a2e"
    await database.migrate("upgrade", previous)
    db = database.connection
    owner, batch, doc, source = (uuid4() for _ in range(4))
    await db.execute(
        "INSERT INTO users(id,email,display_name,password_hash,is_active) "
        "VALUES ($1,'auto-post-migration@example.invalid','Test','synthetic',true)",
        owner,
    )
    await db.execute(
        "INSERT INTO documents(id,user_id,filename,original_name,mime_type,size_bytes,sha256_hash,"
        "storage_path,status,processing_method) "
        "VALUES ($1,$2,'x.pdf','x.pdf','application/pdf',10,$3,'synthetic.pdf','done','bank_import')",
        doc,
        owner,
        "a" * 64,
    )
    await db.execute(
        "INSERT INTO bank_import_batches(id,user_id,kind) VALUES ($1,$2,'statement')", batch, owner
    )
    await db.execute(
        "INSERT INTO bank_import_sources(id,user_id,batch_id,document_id,kind) "
        "VALUES ($1,$2,$3,$4,'statement')",
        source,
        owner,
        batch,
        doc,
    )
    await database.migrate("upgrade", current)
    assert (
        await db.fetchrow("SELECT auto_post_epoch FROM bank_import_sources WHERE id=$1", source)
        is not None
    )
    assert (
        await db.fetchval("SELECT auto_post_epoch FROM bank_import_sources WHERE id=$1", source)
        is None
    )
    assert await db.fetchval("SELECT count(*) FROM bank_import_auto_post_jobs") == 0
    await database.migrate("downgrade", previous)
    await database.migrate("upgrade", current)
    assert await db.fetchval("SELECT count(*) FROM bank_import_sources WHERE id=$1", source) == 1
    await db.execute(
        "INSERT INTO bank_import_auto_post_settings(id,user_id) VALUES ($1,$2)", uuid4(), owner
    )
    assert await db.fetchval("SELECT enabled FROM bank_import_auto_post_settings") is False
    with pytest.raises(RuntimeError, match="Preserve auto-post grants"):
        await database.migrate("downgrade", previous)
