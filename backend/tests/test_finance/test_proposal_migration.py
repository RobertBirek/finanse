import importlib.util
from pathlib import Path

import pytest

TABLES = {
    "categorization_suggestion_settings",
    "categorization_llm_policy",
    "categorization_suggestion_jobs",
    "categorization_llm_usage_reservations",
    "categorization_proposal_items",
}
ORIGIN = "transaction_categorization_origins"


def revision():
    files = list(
        (Path(__file__).resolve().parents[2] / "migrations/versions").glob(
            "*_reviewed_ai_categorization.py"
        )
    )
    assert len(files) == 1, "Missing additive reviewed AI categorization revision"
    spec = importlib.util.spec_from_file_location("proposal_revision", files[0])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_proposal_revision_creates_only_five_tables_and_origin_extension(monkeypatch):
    mod = revision()
    calls = []

    class Recorder:
        def __getattr__(self, name):
            return lambda *a, **kw: calls.append((name, a, kw))

        def f(self, name):
            return name

    monkeypatch.setattr(mod, "op", Recorder())
    mod.upgrade()
    assert {args[0] for name, args, _ in calls if name == "create_table"} == TABLES
    assert mod.down_revision == "c06315385b4e"
    for name, args, _ in calls:
        assert name in {
            "create_table",
            "create_index",
            "add_column",
            "create_foreign_key",
            "drop_constraint",
            "create_check_constraint",
        }
        if name == "add_column":
            assert args[0] == ORIGIN and args[1].name == "proposal_item_id" and args[1].nullable
        if name == "create_foreign_key":
            assert args[1] == ORIGIN and args[2] == "categorization_proposal_items"
        if name in {"drop_constraint", "create_check_constraint"}:
            assert args[1] == ORIGIN


def test_proposal_populated_downgrade_refuses_before_any_ddl_under_locks(monkeypatch):
    mod = revision()
    queries, ddl = [], []

    class Connection:
        def execute(self, query):
            queries.append(str(query))

        def scalar(self, query):
            queries.append(str(query))
            return True

    class Recorder:
        def __getattr__(self, name):
            return lambda *a, **kw: ddl.append((name, a))

        def get_bind(self):
            return Connection()

    monkeypatch.setattr(mod, "op", Recorder())
    with pytest.raises(RuntimeError, match="categorization"):
        mod.downgrade()
    assert "ACCESS EXCLUSIVE" in queries[0] and all(t in queries[0] for t in TABLES | {ORIGIN})
    assert not ddl
