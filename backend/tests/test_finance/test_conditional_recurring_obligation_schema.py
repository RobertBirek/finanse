"""Offline CI guard for ownership constraints on conditional obligations."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from app.finance.models import ConditionalRecurringObligation


def _foreign_keys(
    items: tuple[object, ...],
) -> set[tuple[tuple[str, ...], tuple[str, ...], str | None]]:
    return {
        (
            tuple(constraint.column_keys),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in items
        if isinstance(constraint, sa.ForeignKeyConstraint)
    }


def test_conditional_obligation_model_and_unreleased_migration_enforce_the_same_owner_links(
    monkeypatch,
) -> None:
    """Fails in CI if direct database ownership checks drift from model metadata."""

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/c3d4e5f6a7b8_conditional_recurring_obligations.py"
    )
    spec = importlib.util.spec_from_file_location("conditional_obligation_revision", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    created: list[tuple[object, ...]] = []

    class Recorder:
        def create_table(self, _name: str, *items: object) -> None:
            created.append(items)

        def create_index(self, *_args: object, **_kwargs: object) -> None:
            pass

    monkeypatch.setattr(migration, "op", Recorder())
    migration.upgrade()

    expected = {
        (("user_id",), ("users.id",), "RESTRICT"),
        (("primary_account_id", "user_id"), ("accounts.id", "accounts.user_id"), "RESTRICT"),
        (("fallback_account_id", "user_id"), ("accounts.id", "accounts.user_id"), "RESTRICT"),
    }
    assert len(created) == 1
    assert _foreign_keys(ConditionalRecurringObligation.__table__.constraints) >= expected
    assert _foreign_keys(created[0]) >= expected
