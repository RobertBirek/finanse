"""Import compatibility while finance implementations have focused owners."""

import importlib
import inspect
import uuid

import pytest

from app.finance import service


@pytest.mark.parametrize(
    "module_name,names",
    [
        (
            "transactions",
            (
                "create_transaction",
                "create_exchange_transaction",
                "update_transaction",
                "delete_transaction",
            ),
        ),
        ("reporting", ("get_financial_summary", "get_category_summary")),
        (
            "budgets",
            (
                "create_budget",
                "get_budgets",
                "update_budget",
                "delete_budget",
                "get_budget_status",
            ),
        ),
        (
            "cashflow",
            (
                "get_or_create_finance_settings",
                "update_finance_settings",
                "create_scheduled_item",
                "get_scheduled_items",
                "update_scheduled_item",
                "delete_scheduled_item",
                "get_cashflow_forecast",
                "confirm_scheduled_item",
            ),
        ),
    ],
)
def test_service_preserves_public_entrypoints_from_focused_modules(module_name, names):
    implementation = importlib.import_module(f"app.finance.{module_name}")
    for name in names:
        entrypoint = getattr(service, name)
        assert inspect.iscoroutinefunction(entrypoint)
        assert entrypoint is getattr(implementation, name)


def test_service_retains_transaction_and_forecast_call_signatures():
    assert str(inspect.signature(service.create_transaction)) == (
        "(db: sqlalchemy.ext.asyncio.session.AsyncSession, user_id: uuid.UUID, "
        "data: app.finance.schemas.TransactionCreate, *, "
        "allow_category_reversal: bool = False) -> app.finance.models.FinancialTransaction"
    )
    signature = inspect.signature(service.get_cashflow_forecast)
    assert list(signature.parameters) == ["db", "user_id", "today"]
    assert signature.parameters["today"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["today"].default is None


def test_category_descendants_handles_branches_missing_nodes_and_cycles():
    from app.finance.budgets import category_descendants

    root, first, second, grandchild, unrelated = [uuid.uuid4() for _ in range(5)]
    children = {root: [first, second], first: [grandchild], unrelated: []}
    assert category_descendants(children, root) == {first, second, grandchild}
    assert category_descendants(children, unrelated) == set()
    assert category_descendants(children, uuid.uuid4()) == set()
    assert children == {root: [first, second], first: [grandchild], unrelated: []}
    # Preserve the old traversal's termination even for preexisting malformed data.
    assert category_descendants({root: [first], first: [root]}, root) == {root, first}
