import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.advisor.router import confirm_tool_execution, deny_tool_execution


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class FakeSession:
    def __init__(self, execution, user_id=None):
        self.execution = execution
        self.user_id = user_id
        self.flush = AsyncMock()
        self.add = lambda _value: None

    async def execute(self, _statement):
        if self.user_id is not None and self.execution.message.conversation.user_id != self.user_id:
            return FakeResult(None)
        return FakeResult(self.execution)


def execution_for(user_id, status="pending_confirmation"):
    conversation = SimpleNamespace(user_id=user_id)
    message = SimpleNamespace(conversation=conversation)
    return SimpleNamespace(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        message=message,
        tool_name="create_task",
        arguments={"title": "Test"},
        result=None,
        status=status,
        policy_check_passed=False,
    )


@pytest.mark.asyncio
async def test_confirm_rejects_repeat_confirmation_without_executing(monkeypatch):
    user_id = uuid.uuid4()
    execution = execution_for(user_id, status="completed")
    executor = AsyncMock()
    tool = SimpleNamespace(executor=executor)
    monkeypatch.setattr("app.advisor.tools.registry.get_tool_by_name", lambda _name: tool)

    with pytest.raises(HTTPException) as error:
        await confirm_tool_execution(
            execution.id,
            SimpleNamespace(id=user_id),
            FakeSession(execution, user_id),
        )

    assert error.value.status_code == 409
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_deny_rejects_repeat_denial_with_conflict():
    user_id = uuid.uuid4()
    execution = execution_for(user_id, status="denied")

    with pytest.raises(HTTPException) as error:
        await deny_tool_execution(
            execution.id,
            SimpleNamespace(id=user_id),
            FakeSession(execution, user_id),
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_deny_hides_execution_from_another_user():
    owner_id = uuid.uuid4()
    another_user_id = uuid.uuid4()
    execution = execution_for(owner_id)

    with pytest.raises(HTTPException) as error:
        await deny_tool_execution(
            execution.id,
            SimpleNamespace(id=another_user_id),
            FakeSession(execution, another_user_id),
        )

    assert error.value.status_code == 404
