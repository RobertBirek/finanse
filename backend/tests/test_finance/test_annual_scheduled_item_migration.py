import importlib.util
from pathlib import Path

import pytest


def revision():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/b1c2d3e4f5a6_annual_scheduled_finance_items.py"
    )
    spec = importlib.util.spec_from_file_location("annual_scheduled_item_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_populated_annual_schedule_downgrade_refuses_before_schema_changes(monkeypatch) -> None:
    migration = revision()
    queries: list[str] = []
    ddl: list[str] = []

    class Connection:
        def execute(self, query):
            queries.append(str(query))

        def scalar(self, query):
            queries.append(str(query))
            return True

    class Recorder:
        def get_bind(self):
            return Connection()

        def __getattr__(self, name):
            return lambda *args, **kwargs: ddl.append(name)

    monkeypatch.setattr(migration, "op", Recorder())

    with pytest.raises(RuntimeError, match="annual scheduled"):
        migration.downgrade()

    assert "ACCESS EXCLUSIVE" in queries[0]
    assert "cadence = 'annual'" in queries[1]
    assert ddl == []


def test_populated_conditional_obligation_downgrade_refuses_before_schema_changes(
    monkeypatch,
) -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/c3d4e5f6a7b8_conditional_recurring_obligations.py"
    )
    spec = importlib.util.spec_from_file_location("conditional_obligation_revision", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    queries: list[str] = []
    ddl: list[str] = []

    class Connection:
        def execute(self, query):
            queries.append(str(query))

        def scalar(self, query):
            queries.append(str(query))
            return True

    class Recorder:
        def get_bind(self):
            return Connection()

        def __getattr__(self, name):
            return lambda *args, **kwargs: ddl.append(name)

    monkeypatch.setattr(migration, "op", Recorder())

    with pytest.raises(RuntimeError, match="conditional recurring obligations"):
        migration.downgrade()

    assert "ACCESS EXCLUSIVE" in queries[0]
    assert "conditional_recurring_obligations" in queries[1]
    assert ddl == []
