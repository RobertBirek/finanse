from uuid import uuid4

import pytest

from tests import migration_fixtures

owned_migration_database = migration_fixtures.owned_migration_database


@pytest.mark.migration
async def test_openai_scope_migration_preserves_previous_settings_and_refuses_loss(
    owned_migration_database,
):
    database = owned_migration_database
    await database.migrate("upgrade", "c435e5526e23")
    db = database.connection
    owner = uuid4()
    await db.execute(
        "INSERT INTO users(id,email,display_name,password_hash,is_active) "
        "VALUES ($1,'migration@example.invalid','Test','synthetic',true)",
        owner,
    )
    profile = uuid4()
    await db.execute(
        "INSERT INTO advisor_ai_profiles (id,user_id,model,encrypted_key) VALUES ($1,$2,'advisor-test',$3)",
        profile,
        owner,
        b"synthetic-encrypted",
    )
    await database.migrate("upgrade", "head")
    row = await db.fetchrow("SELECT * FROM advisor_ai_profiles WHERE id=$1", profile)
    assert row["purpose"] == "advisor"
    assert row["model"] == "advisor-test"
    assert row["encrypted_key"] == b"synthetic-encrypted"
    event = uuid4()
    await db.execute(
        "INSERT INTO advisor_ai_usage (id,user_id,kind,model,status,duration_ms) "
        "VALUES ($1,$2,'operation','test','ok',1)",
        event,
        owner,
    )
    with pytest.raises(RuntimeError, match="configuration generations and usage must be retained"):
        await database.migrate("downgrade", "c435e5526e23")
    await db.execute("DELETE FROM advisor_ai_usage WHERE id=$1", event)
    await db.execute(
        "UPDATE advisor_ai_profiles SET configuration_id=$2 WHERE id=$1", profile, uuid4()
    )
    with pytest.raises(RuntimeError, match="configuration generations and usage must be retained"):
        await database.migrate("downgrade", "c435e5526e23")
    await db.execute("UPDATE advisor_ai_profiles SET configuration_id=NULL WHERE id=$1", profile)
    await db.execute(
        "INSERT INTO advisor_ai_profiles (id,user_id,purpose,model) VALUES ($1,$2,'vision','test')",
        uuid4(),
        owner,
    )
    with pytest.raises(RuntimeError, match="settings for other purposes must be retained"):
        await database.migrate("downgrade", "c435e5526e23")
    assert await db.fetchval("SELECT count(*) FROM advisor_ai_profiles") == 2
