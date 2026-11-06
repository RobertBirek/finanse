"""Color schema fixtures must refuse production/remote targets before any engine/DDL."""

from typing import Any

import pytest

from tests.test_finance import test_entity_colors as colors


@pytest.mark.parametrize(
    "target",
    [
        "postgresql+asyncpg://finanse:finanse@production:5432/finanse",
        "postgresql+asyncpg://finanse:finanse@127.0.0.1:55431/finanse",
        "postgresql+asyncpg://finanse:finanse@localhost:55432/finanse_restore",
        "postgresql+asyncpg://finanse:finanse@remote:55432/finanse_test",
        "sqlite+aiosqlite:///:memory:",
    ],
)
async def test_color_fixture_refuses_unsafe_target_before_engine(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    attempts = []

    def forbidden_engine(*args: Any, **kwargs: Any) -> None:
        attempts.append(True)
        raise AssertionError("unsafe target reached engine factory")

    monkeypatch.setenv("TEST_DATABASE_URL", target)
    monkeypatch.setattr(colors, "create_async_engine", forbidden_engine)
    generator = colors.color_db_session.__wrapped__()
    with pytest.raises(ValueError, match="Unsafe color test database"):
        await anext(generator)
    assert attempts == []
