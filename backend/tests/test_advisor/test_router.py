import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.advisor import service as advisor_service
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
        self.statements = []
        self.flush = AsyncMock()
        self.add = lambda _value: None

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.execution)

    def begin_nested(self):
        return NoopSavepoint()


class NoopSavepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


def execution_for(user_id, status="pending_confirmation"):
    conversation = SimpleNamespace(user_id=user_id)
    message = SimpleNamespace(conversation=conversation)
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        message=message,
        tool_name="create_task",
        arguments={"title": "Test"},
        result=None,
        status=status,
        policy_check_passed=False,
    )
    message.tool_executions = []
    execution.message_id = uuid.uuid4()
    return execution


@pytest.mark.asyncio
async def test_confirm_rejects_repeat_confirmation_without_executing(monkeypatch):
    user_id = uuid.uuid4()
    execution = execution_for(user_id, status="completed")
    executor = AsyncMock()
    tool = SimpleNamespace(executor=executor)
    monkeypatch.setattr("app.advisor.router.get_tool_by_name", lambda _name: tool, raising=False)

    session = FakeSession(execution, user_id)
    with pytest.raises(HTTPException) as error:
        await confirm_tool_execution(
            execution.id,
            SimpleNamespace(id=user_id),
            session,
        )

    assert error.value.status_code == 409
    executor.assert_not_awaited()
    assert session.statements[0]._for_update_arg is not None


@pytest.mark.asyncio
async def test_deny_rejects_repeat_denial_with_conflict():
    user_id = uuid.uuid4()
    execution = execution_for(user_id, status="denied")
    session = FakeSession(execution, user_id)

    with pytest.raises(HTTPException) as error:
        await deny_tool_execution(
            execution.id,
            SimpleNamespace(id=user_id),
            session,
        )

    assert error.value.status_code == 409
    assert session.statements[0]._for_update_arg is not None


@pytest.mark.asyncio
async def test_deny_hides_execution_from_another_user():
    owner_id = uuid.uuid4()
    another_user_id = uuid.uuid4()
    execution = execution_for(owner_id)

    with pytest.raises(HTTPException) as error:
        await deny_tool_execution(
            execution.id,
            SimpleNamespace(id=another_user_id),
            FakeSession(execution),
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_hides_execution_from_another_user(monkeypatch):
    owner_id = uuid.uuid4()
    another_user_id = uuid.uuid4()
    execution = execution_for(owner_id)
    executor = AsyncMock()
    monkeypatch.setattr(
        "app.advisor.tools.registry.get_tool_by_name",
        lambda _name: SimpleNamespace(executor=executor),
    )

    with pytest.raises(HTTPException) as error:
        await confirm_tool_execution(
            execution.id,
            SimpleNamespace(id=another_user_id),
            FakeSession(execution),
        )

    assert error.value.status_code == 404
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_returns_not_found_for_missing_execution():
    with pytest.raises(HTTPException) as error:
        await confirm_tool_execution(
            uuid.uuid4(),
            SimpleNamespace(id=uuid.uuid4()),
            FakeSession(None),
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_deny_returns_not_found_for_missing_execution():
    with pytest.raises(HTTPException) as error:
        await deny_tool_execution(
            uuid.uuid4(),
            SimpleNamespace(id=uuid.uuid4()),
            FakeSession(None),
        )

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_confirm_sanitizes_executor_failure(monkeypatch):
    user_id = uuid.uuid4()
    execution = execution_for(user_id)
    session = RollbackSession(execution)

    async def executor(db, _user_id, **_arguments):
        db.mutations.append("created task")
        await db.flush()
        raise RuntimeError("database password leaked")

    monkeypatch.setattr(
        "app.advisor.tools.registry.get_tool_by_name",
        lambda _name: SimpleNamespace(executor=executor),
    )

    await confirm_tool_execution(
        execution.id,
        SimpleNamespace(id=user_id),
        session,
    )

    assert session.mutations == []
    assert execution.status == "error"
    assert execution.result == {"error": "Nie udało się wykonać narzędzia"}
    assert "database password" not in str(execution.result)


class RollbackSession(FakeSession):
    def __init__(self, execution):
        super().__init__(execution)
        self.mutations = []

    async def flush(self):
        return None

    def begin_nested(self):
        return RollbackSavepoint(self)


class RollbackSavepoint:
    def __init__(self, session):
        self.session = session
        self.before = []

    async def __aenter__(self):
        self.before = list(self.session.mutations)
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        self.session.mutations[:] = self.before
        return False


@pytest.mark.asyncio
async def test_confirm_rolls_back_executor_flush_when_audit_fails(monkeypatch):
    user_id = uuid.uuid4()
    execution = execution_for(user_id)
    session = RollbackSession(execution)

    async def executor(db, _user_id, **_arguments):
        db.mutations.append("created task")
        await db.flush()
        return {"id": "task-id"}

    monkeypatch.setattr(
        "app.advisor.tools.registry.get_tool_by_name",
        lambda _name: SimpleNamespace(executor=executor),
    )
    monkeypatch.setattr(
        "app.audit.service.log_event",
        AsyncMock(side_effect=RuntimeError("audit unavailable")),
    )

    await confirm_tool_execution(
        execution.id,
        SimpleNamespace(id=user_id),
        session,
    )

    assert session.mutations == []
    assert execution.status == "error"
    assert execution.result == {"error": "Nie udało się wykonać narzędzia"}


class FakeAdvisorSession:
    def __init__(self):
        self.values = []

    def add(self, value):
        self.values.append(value)

    async def flush(self):
        return None


def llm_response(tool_call=None, content="Odpowiedź"):
    message = SimpleNamespace(content=content, tool_calls=[tool_call] if tool_call else None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_send_message_returns_pending_without_relying_on_relationship(monkeypatch):
    user_id = uuid.uuid4()
    conversation = SimpleNamespace(id=uuid.uuid4(), title="Nowa rozmowa")
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="create_task", arguments='{"title":"Test"}'),
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=llm_response(tool_call)))
        )
    )
    tool = SimpleNamespace(autonomy_level=2, executor=AsyncMock())
    monkeypatch.setattr(advisor_service, "_get_llm_client", lambda: client)
    monkeypatch.setattr(advisor_service, "get_openai_tools", list)
    monkeypatch.setattr(advisor_service, "get_tool_by_name", lambda _name: tool)
    monkeypatch.setattr(advisor_service, "get_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(advisor_service, "get_conversation_messages", AsyncMock(return_value=[]))

    result = await advisor_service.send_message(
        FakeAdvisorSession(), user_id, conversation.id, "Utwórz zadanie"
    )

    assert result.role == "assistant"
    assert result.tool_executions[0].status == "pending_confirmation"
    client.chat.completions.create.assert_awaited_once()
    tool.executor.assert_not_awaited()
