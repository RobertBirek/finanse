from conftest import DEFAULT_TEST_DATABASE_URL, is_safe_test_database_url


def test_default_test_database_url_keeps_approved_fallback():
    assert DEFAULT_TEST_DATABASE_URL == (
        "postgresql+asyncpg://finanse:finanse@localhost:5432/finanse_test"
    )


def test_docker_test_database_url_is_safe():
    assert is_safe_test_database_url(
        "postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test"
    )


def test_production_database_url_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url(
        "postgresql+asyncpg://finanse:secret@localhost:5432/finanse"
    )


def test_remote_test_named_database_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url(
        "postgresql+asyncpg://finanse:secret@db.internal:5432/finanse_test"
    )


def test_malformed_database_url_is_not_safe_for_schema_cleanup():
    assert not is_safe_test_database_url("not-a-database-url")
