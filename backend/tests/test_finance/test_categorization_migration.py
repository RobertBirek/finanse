import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def revision():
    path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2268bca97cb8_transaction_categorization_state.py"
    )
    spec = importlib.util.spec_from_file_location("category_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_only_creates_category_evidence_table(monkeypatch):
    mod = revision()
    calls = []

    class Recorder:
        def __getattr__(self, name):
            return lambda *a, **kw: calls.append((name, a))

        def f(self, name):
            return name

    monkeypatch.setattr(mod, "op", Recorder())
    mod.upgrade()
    assert [(name, args[0]) for name, args in calls] == [
        ("create_table", "transaction_categorization_states"),
        ("create_index", "ix_transaction_categorization_states_user_id"),
    ]
    assert mod.down_revision == "84f28fe23ab8"


def test_populated_downgrade_refuses_before_drops_under_lock(monkeypatch):
    mod = revision()
    queries = []
    drops = []

    class Connection:
        def execute(self, query):
            queries.append(str(query))

        def scalar(self, query):
            queries.append(str(query))
            return True

    monkeypatch.setattr(
        mod,
        "op",
        SimpleNamespace(
            f=lambda n: n,
            get_bind=lambda: Connection(),
            drop_index=lambda *a, **kw: drops.append(a),
            create_index=lambda *a, **kw: None,
            drop_table=lambda *a: drops.append(a),
        ),
    )
    with pytest.raises(RuntimeError, match="categorization"):
        mod.downgrade()
    assert queries[0] == "LOCK TABLE transaction_categorization_states IN ACCESS EXCLUSIVE MODE"
    assert not drops
