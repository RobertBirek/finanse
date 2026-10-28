from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "7f8ce92bda94_financial_documents_and_payment_.py"
)


def test_migration_preserves_old_rows_without_backfill():
    spec = spec_from_file_location("financial_documents_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.down_revision == "c2d7e9a4f801"
    upgrade_source = module.upgrade.__code__.co_names
    assert "create_table" in upgrade_source
    assert "drop_table" not in upgrade_source
    assert "execute" not in upgrade_source
