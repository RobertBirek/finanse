import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def revision():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/84f28fe23ab8_transaction_date_metadata.py"
    )
    spec = importlib.util.spec_from_file_location("transaction_date_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_date_migration_is_additive_only_and_keeps_existing_indexes(monkeypatch):
    module = revision()
    calls = []

    class Recorder:
        def __getattr__(self, name):
            return lambda *args, **kwargs: calls.append((name, args))

        def f(self, name):
            return name

    monkeypatch.setattr(module, "op", Recorder())
    module.upgrade()
    assert [(name, args[0]) for name, args in calls] == [
        ("create_table", "transaction_date_metadata"),
        ("create_index", "ix_transaction_date_user_booking"),
        ("create_index", "ix_transaction_date_user_purchase"),
    ]
    assert module.down_revision == "2f4b2c2a527c"


def test_date_migration_downgrade_refuses_populated_annotations_under_exclusive_lock(monkeypatch):
    module = revision()
    queries = []
    drops = []

    class Connection:
        def execute(self, query):
            queries.append(str(query))

        def scalar(self, query):
            queries.append(str(query))
            return True

    monkeypatch.setattr(
        module,
        "op",
        SimpleNamespace(
            f=lambda name: name,
            create_index=lambda *a, **kw: None,
            get_bind=lambda: Connection(),
            drop_index=lambda *a, **kw: drops.append(a),
            drop_table=lambda *a: drops.append(a),
        ),
    )
    with pytest.raises(RuntimeError, match="date metadata"):
        module.downgrade()
    assert queries[0] == "LOCK TABLE transaction_date_metadata IN ACCESS EXCLUSIVE MODE"
    assert not drops
