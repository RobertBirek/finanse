import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI

from app.advisor import service as advisor_service


class FakeSession:
    def __init__(self):
        self.added = []
        self.flush = AsyncMock()

    def add(self, value):
        self.added.append(value)

    @asynccontextmanager
    async def begin_nested(self):
        yield self


def llm_response(*, content=None, tool_calls=None):
    if tool_calls:
        output = tool_calls
    else:
        output = [
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=content)],
            )
        ]
    return SimpleNamespace(status="completed", output=output)


def tool_call(name, arguments, call_id="call-1"):
    values = {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
    }
    return SimpleNamespace(
        **values,
        model_dump=lambda mode: values,
    )


def setup_service(monkeypatch, responses, tool=None, history=None):
    conversation = SimpleNamespace(id=uuid.uuid4(), title="Nowa rozmowa")
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=responses)),
        close=AsyncMock(),
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
    assert client.responses.create.await_count == 1
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
    assert client.responses.create.await_count == 2
    second_input = client.responses.create.await_args_list[1].kwargs["input"]
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"accounts": [{"name": "Konto główne"}]}',
    }
    assistant_tool_message = next(
        item
        for item in db.added
        if item.__class__.__name__ == "Message" and item.tool_calls is not None
    )
    assert assistant_tool_message.content == ""
    executions = [item for item in db.added if item.__class__.__name__ == "ToolExecution"]
    assert len(executions) == 1
    assert executions[0].status == "completed"
    assert executions[0].result == {"accounts": [{"name": "Konto główne"}]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call_name", "arguments", "tool", "expected_result", "expected_status"),
    [
        ("get_accounts", "{", "known", {"error": advisor_service.INVALID_ARGUMENTS}, "error"),
        (
            "get_accounts",
            "not-json",
            "known",
            {"error": advisor_service.INVALID_ARGUMENTS},
            "error",
        ),
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
    assert client.responses.create.await_count == 2
    executor.assert_not_awaited()


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
    assert execution.result == {"error": advisor_service.TOOL_ERROR}
    assert client.responses.create.await_count == 2


@pytest.mark.asyncio
async def test_level_two_tool_call_stays_pending_without_executor_call(monkeypatch):
    executor = AsyncMock()
    tool = SimpleNamespace(name="create_task", autonomy_level=2, executor=executor)
    call = tool_call("create_task", '{"title":"Zadanie"}')
    _, client = setup_service(monkeypatch, [llm_response(tool_calls=[call])], tool=tool)
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Utwórz zadanie")

    assert result.content == ""
    assert result.tool_executions[0].status == "pending_confirmation"
    assert result.tool_executions[0].result == {"title": "Zadanie", "tool": "create_task"}
    executor.assert_not_awaited()
    client.responses.create.assert_awaited_once()


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
    assert client.responses.create.await_count == advisor_service.MAX_TOOL_ITERATIONS
    assert executor.await_count == advisor_service.MAX_TOOL_ITERATIONS
    executions = [item for item in db.added if item.__class__.__name__ == "ToolExecution"]
    assert len(executions) == advisor_service.MAX_TOOL_ITERATIONS


@pytest.mark.asyncio
async def test_second_user_turn_replays_prior_tool_result(monkeypatch):
    executor = AsyncMock(return_value={"accounts": [{"name": "Konto główne"}]})
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    first_call = tool_call("get_accounts", "{}", "call-first")
    conversation = SimpleNamespace(id=uuid.uuid4(), title="Nowa rozmowa")
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                side_effect=[
                    llm_response(tool_calls=[first_call]),
                    llm_response(content="Masz jedno konto."),
                    llm_response(content="To konto jest aktywne."),
                ]
            )
        ),
        close=AsyncMock(),
    )
    history_calls = 0

    monkeypatch.setattr(advisor_service, "_get_llm_client", lambda: client)
    monkeypatch.setattr(advisor_service, "get_openai_tools", list)
    monkeypatch.setattr(advisor_service, "get_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(advisor_service, "get_tool_by_name", lambda _name: tool)

    async def conversation_history(_db, _user_id, _conversation_id):
        nonlocal history_calls
        history_calls += 1
        if history_calls == 1:
            return []
        return [item for item in db.added if item.__class__.__name__ == "Message"]

    monkeypatch.setattr(advisor_service, "get_conversation_messages", conversation_history)
    user_id = uuid.uuid4()
    db = FakeSession()

    first_result = await advisor_service.send_message(db, user_id, conversation.id, "Pokaż konta")
    second_result = await advisor_service.send_message(
        db, user_id, conversation.id, "Czy to konto jest aktywne?"
    )

    assert first_result.content == "Masz jedno konto."
    assert second_result.content == "To konto jest aktywne."
    second_messages = client.responses.create.await_args_list[2].kwargs["input"]
    assert {
        "type": "function_call_output",
        "call_id": "call-first",
        "output": '{"accounts": [{"name": "Konto główne"}]}',
    } in second_messages
    assert second_messages[-1] == {
        "role": "user",
        "content": "Czy to konto jest aktywne?",
    }
    assert sum(message.get("type") == "function_call_output" for message in second_messages) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["[]", "null", "42", '"text"'])
@pytest.mark.parametrize("level", [0, 2])
async def test_non_object_arguments_never_execute_or_request_approval(monkeypatch, raw, level):
    executor = AsyncMock()
    tool = SimpleNamespace(name="tool", autonomy_level=level, executor=executor)
    setup_service(
        monkeypatch,
        [
            llm_response(tool_calls=[tool_call("tool", raw)]),
            llm_response(content="Invalid arguments"),
        ],
        tool=tool,
    )
    db = FakeSession()
    await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Test")
    execution = next(item for item in db.added if item.__class__.__name__ == "ToolExecution")
    assert execution.status == "error"
    assert execution.arguments == {}
    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_error_does_not_leak_credentials(monkeypatch, caplog):
    setup_service(monkeypatch, [RuntimeError("SECRET_PROVIDER_CREDENTIAL")])
    result = await advisor_service.send_message(FakeSession(), uuid.uuid4(), uuid.uuid4(), "Test")
    assert result.content == advisor_service.ADVISOR_ERROR
    assert "SECRET_PROVIDER_CREDENTIAL" not in caplog.text


@pytest.mark.asyncio
async def test_responses_tool_roundtrip_replays_reasoning_and_matching_output(monkeypatch):
    """Dropping encrypted reasoning or changing a call id breaks stateless tool continuation."""
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "id": "response-one",
                    "object": "response",
                    "created_at": 0,
                    "model": "sol-test",
                    "status": "completed",
                    "output": [
                        {
                            "id": "reasoning-one",
                            "type": "reasoning",
                            "summary": [],
                            "encrypted_content": "opaque-reasoning",
                        },
                        {
                            "id": "function-one",
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "get_accounts",
                            "arguments": "{}",
                            "status": "completed",
                        },
                    ],
                    "parallel_tool_calls": False,
                    "tool_choice": "auto",
                    "tools": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "response-two",
                "object": "response",
                "created_at": 0,
                "model": "sol-test",
                "status": "completed",
                "output": [
                    {
                        "id": "message-two",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "Masz konto."}],
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    executor = AsyncMock(return_value={"accounts": []})
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    conversation = SimpleNamespace(id=uuid.uuid4(), title="Nowa rozmowa")
    monkeypatch.setattr(advisor_service, "_get_llm_client", lambda: client)
    monkeypatch.setattr(advisor_service, "get_openai_tools", list)
    monkeypatch.setattr(advisor_service, "get_tool_by_name", lambda _name: tool)
    monkeypatch.setattr(advisor_service, "get_conversation", AsyncMock(return_value=conversation))
    monkeypatch.setattr(advisor_service, "get_conversation_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(advisor_service.settings, "LLM_MODEL", "sol-test")
    monkeypatch.setattr(advisor_service.settings, "LLM_MAX_OUTPUT_TOKENS", 4096)
    monkeypatch.setattr(advisor_service.settings, "LLM_REASONING_EFFORT", "low")

    result = await advisor_service.send_message(
        FakeSession(), uuid.uuid4(), conversation.id, "Pokaż konta"
    )

    assert result.content == "Masz konto."
    assert requests[0]["model"] == "sol-test"
    assert requests[0]["reasoning"] == {"effort": "low"}
    assert requests[0]["max_output_tokens"] == 4096
    assert requests[0]["include"] == ["reasoning.encrypted_content"]
    assert requests[0]["store"] is False
    assert not {"messages", "temperature", "max_tokens", "response_format"} & requests[0].keys()
    replayed_reasoning = next(
        item for item in requests[1]["input"] if item.get("type") == "reasoning"
    )
    assert replayed_reasoning["id"] == "reasoning-one"
    assert replayed_reasoning["encrypted_content"] == "opaque-reasoning"
    assert replayed_reasoning["summary"] == []
    assert any(
        item.get("type") == "function_call" and item["call_id"] == "call-1"
        for item in requests[1]["input"]
    )
    assert {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"accounts": []}',
    } in requests[1]["input"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status="incomplete", output=[tool_call("get_accounts", "{}")]),
        SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="message", content=[SimpleNamespace(type="refusal", refusal="no")]
                ),
                tool_call("get_accounts", "{}"),
            ],
        ),
    ],
)
async def test_terminal_or_refused_tool_output_never_executes(monkeypatch, response):
    """Executing a function from incomplete or refused output bypasses the model terminal guard."""
    executor = AsyncMock()
    tool = SimpleNamespace(name="get_accounts", autonomy_level=0, executor=executor)
    _, client = setup_service(monkeypatch, [response], tool=tool)
    db = FakeSession()

    result = await advisor_service.send_message(db, uuid.uuid4(), uuid.uuid4(), "Pokaż konta")

    assert result.content == advisor_service.ADVISOR_ERROR
    executor.assert_not_awaited()
    assert not [item for item in db.added if item.__class__.__name__ == "ToolExecution"]
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_error_does_not_leak_credentials(monkeypatch):
    from fastapi import HTTPException

    from app.advisor import router
    from app.advisor.schemas import SendMessageRequest

    monkeypatch.setattr(
        router, "send_message", AsyncMock(side_effect=ValueError("SECRET_PROVIDER_CREDENTIAL"))
    )
    with pytest.raises(HTTPException) as error:
        await router.send_message_endpoint(
            SendMessageRequest(content="Test"),
            SimpleNamespace(id=uuid.uuid4()),
            None,
            FakeSession(),
        )
    assert error.value.detail == advisor_service.ADVISOR_ERROR


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sql_read_failure_is_rolled_back_to_savepoint(db_session):
    from sqlalchemy import select, text

    async def fail(db, _user_id):
        await db.execute(text("SELECT 1 / 0"))

    tool = SimpleNamespace(executor=fail)
    result, status = await advisor_service._execute_read_tool(db_session, tool, uuid.uuid4(), {})
    assert status == "error" and result == {"error": advisor_service.TOOL_ERROR}
    assert await db_session.scalar(select(1)) == 1


def test_history_messages_adds_sanitized_result_when_execution_is_missing():
    history = [
        SimpleNamespace(
            role="assistant",
            content="",
            tool_calls=[
                {
                    "id": "call-missing",
                    "type": "function",
                    "function": {"name": "get_accounts", "arguments": "{}"},
                }
            ],
            tool_executions=[],
        )
    ]

    messages = advisor_service._history_messages(history)

    assert messages[-1] == {
        "type": "function_call_output",
        "call_id": "call-missing",
        "output": '{"error": "Nie udało się odtworzyć wyniku narzędzia"}',
    }
