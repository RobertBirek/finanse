import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.advisor import service as advisor_service


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush = AsyncMock()

    def add(self, value):
        self.added.append(value)


def llm_response(*, content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_call(name, arguments, call_id="call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def setup_service(monkeypatch, responses, tool=None, history=None):
    conversation = SimpleNamespace(id=uuid.uuid4(), title="Nowa rozmowa")
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=responses)))
    )
    monkeypatch.setattr(advisor_service, "_get_llm_client", lambda: client)
    monkeypatch.setattr(advisor_service, "get_openai_tools", list)
    monkeypatch.setattr(advisor_service, "get_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(
        advisor_service,
        "get_conversation_messages",
        AsyncMock(return_value=history or []),
    )
    monkeypatch.setattr(advisor_service, "get_tool_by_name", lambda _name: tool)
    return conversation, client


@pytest.mark.asyncio
async def test_send_message_returns_plain_llm_response(monkeypatch):
    _, client = setup_service(monkeypatch, [llm_response(content="Zwykła odpowiedź")])
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Cześć")

    assert result.role == "assistant"
    assert result.content == "Zwykła odpowiedź"
    assert result.tool_calls is None
    assert client.chat.completions.create.await_count == 1
    assert not [item for item in db.added if item.__class__.__name__ == "ToolExecution"]


@pytest.mark.asyncio
async def test_level_zero_tool_call_is_followed_by_second_llm_response(monkeypatch):
    executor = AsyncMock(return_value={"accounts": [{"name": "Konto główne"}]})
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    call = tool_call("get_accounts", "{}")
    _, client = setup_service(
        monkeypatch,
        [
            llm_response(tool_calls=[call]),
            llm_response(content="Masz jedno konto."),
        ],
        tool=tool,
    )
    user_id = uuid.uuid4()
    db = FakeSession()

    result = await advisor_service.send_message(db, user_id, uuid.uuid4(), "Pokaż konta")

    assert result.content == "Masz jedno konto."
    executor.assert_awaited_once_with(db, str(user_id))
    assert client.chat.completions.create.await_count == 2
    second_messages = client.chat.completions.create.await_args_list[1].kwargs["messages"]
    assert second_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"accounts": [{"name": "Konto główne"}]}',
    }
    executions = [item for item in db.added if item.__class__.__name__ == "ToolExecution"]
    assert len(executions) == 1
    assert executions[0].status == "completed"
    assert executions[0].result == {"accounts": [{"name": "Konto główne"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call_name", "arguments", "tool", "expected_result", "expected_status"),
    [
        ("get_accounts", "not-json", "known", {"ok": True}, "completed"),
        ("missing_tool", "{}", None, {"error": "Unknown tool: missing_tool"}, "error"),
    ],
)
async def test_tool_call_handles_invalid_json_and_unknown_tool(
    monkeypatch, call_name, arguments, tool, expected_result, expected_status
):
    executor = AsyncMock(return_value={"ok": True})
    registered_tool = (
        SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor) if tool else None
    )
    _, client = setup_service(
        monkeypatch,
        [
            llm_response(tool_calls=[tool_call(call_name, arguments)]),
            llm_response(content="Błąd narzędzia."),
        ],
        tool=registered_tool,
    )
    db = FakeSession()

    user_id = uuid.uuid4()
    result = await advisor_service.send_message(db, user_id, uuid.uuid4(), "Uruchom narzędzie")
    execution = next(item for item in db.added if item.__class__.__name__ == "ToolExecution")

    assert result.content == "Błąd narzędzia."
    assert execution.status == expected_status
    assert execution.result == expected_result
    assert execution.arguments == {}
    assert client.chat.completions.create.await_count == 2
    if registered_tool is None:
        executor.assert_not_awaited()
    else:
        executor.assert_awaited_once_with(db, str(user_id))


@pytest.mark.asyncio
async def test_tool_executor_error_is_returned_as_error_result(monkeypatch):
    executor = AsyncMock(side_effect=RuntimeError("executor failed"))
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    _, client = setup_service(
        monkeypatch,
        [
            llm_response(tool_calls=[tool_call("get_accounts", "{}")]),
            llm_response(content="Nie udało się pobrać danych."),
        ],
        tool=tool,
    )
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Pobierz konta")
    execution = next(item for item in db.added if item.__class__.__name__ == "ToolExecution")

    assert result.content == "Nie udało się pobrać danych."
    assert execution.status == "error"
    assert execution.result == {"error": "executor failed"}
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_level_two_tool_call_stays_pending_without_executor_call(monkeypatch):
    executor = AsyncMock()
    tool = SimpleNamespace(name="create_task", autonomy_level=2, executor=executor)
    call = tool_call("create_task", '{"title":"Zadanie"}')
    _, client = setup_service(monkeypatch, [llm_response(tool_calls=[call])], tool=tool)
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Utwórz zadanie")

    assert result.tool_executions[0].status == "pending_confirmation"
    assert result.tool_executions[0].result == {"title": "Zadanie", "tool": "create_task"}
    executor.assert_not_awaited()
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_message_stops_after_max_tool_iterations(monkeypatch):
    executor = AsyncMock(return_value={"ok": True})
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    responses = [
        llm_response(tool_calls=[tool_call("get_accounts", "{}", f"call-{index}")])
        for index in range(advisor_service.MAX_TOOL_ITERATIONS)
    ]
    _, client = setup_service(monkeypatch, responses, tool=tool)
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Pokaż konta")

    assert result.content == "Przetworzyłem dane. Czy potrzebujesz dodatkowych informacji?"
    assert client.chat.completions.create.await_count == advisor_service.MAX_TOOL_ITERATIONS
    assert executor.await_count == advisor_service.MAX_TOOL_ITERATIONS
    executions = [item for item in db.added if item.__class__.__name__ == "ToolExecution"]
    assert len(executions) == advisor_service.MAX_TOOL_ITERATIONS
