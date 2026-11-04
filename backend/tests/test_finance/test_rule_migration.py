import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

TABLES = {
    "transaction_categorization_settings",
    "transaction_categorization_rules",
    "transaction_categorization_origins",
    "transaction_rule_events",
}


def revision():
    files = list(
        (Path(__file__).resolve().parents[2] / "migrations/versions").glob(
            "*approved_categorization_rules.py"
        )
    )
    assert len(files) == 1, "Missing additive rules revision"
    spec = importlib.util.spec_from_file_location("rules_revision", files[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rules_revision_only_creates_four_evidence_tables(monkeypatch):
    mod = revision()
    calls = []

    class Recorder:
        def __getattr__(self, name):
            return lambda *a, **kw: calls.append((name, a))

        def f(self, name):
            return name

    monkeypatch.setattr(mod, "op", Recorder())
    mod.upgrade()
    assert {args[0] for name, args in calls if name == "create_table"} == TABLES
    assert all(name in {"create_table", "create_index"} for name, args in calls)
    assert mod.down_revision == "2268bca97cb8"


def test_rules_populated_downgrade_refuses_before_any_drop_under_all_table_locks(monkeypatch):
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
            get_bind=lambda: Connection(),
            f=lambda n: n,
            drop_table=lambda *a, **kw: drops.append(a),
            drop_index=lambda *a, **kw: drops.append(a),
            create_index=lambda *a, **kw: drops.append(a),
        ),
    )
    with pytest.raises(RuntimeError, match="categorization"):
        mod.downgrade()
    assert "ACCESS EXCLUSIVE" in queries[0] and all(t in queries[0] for t in TABLES)
    assert not drops
