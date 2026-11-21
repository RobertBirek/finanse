import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from openai import APITimeoutError

from app.advisor import ai_settings_router as routes
from app.advisor.ai_settings import AdvisorCredentials, ModelUnavailable
from app.database import get_db
from app.identity.router import get_current_user
from app.security import rate_limit


async def test_benchmark_scores_six_calls_without_retry_and_preserves_missing_usage(monkeypatch):
    from app.advisor import ai_benchmark as bench

    def response(answer):
        return SimpleNamespace(
            usage=None,
            status="completed",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[
                        SimpleNamespace(type="output_text", text=json.dumps({"answer": answer}))
                    ],
                )
            ],
        )

    call = AsyncMock(
        side_effect=[
            response("task"),
            response("wrong"),
            APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            response("task"),
            response("insufficient_data"),
            response("A2"),
        ]
    )
    client = MagicMock()
    client.__aenter__.return_value = SimpleNamespace(responses=SimpleNamespace(create=call))
    factory = MagicMock(return_value=client)
    telemetry = AsyncMock()
    monkeypatch.setattr(bench, "create_openai_client", factory)
    monkeypatch.setattr(bench, "record_usage", telemetry)
    variants = (
        bench.BenchmarkVariant(model="a", instructions="First"),
        bench.BenchmarkVariant(model="b", instructions="Second"),
    )
    result = await bench.compare_configs(
        uuid4(),
        variants,
        credentials=(AdvisorCredentials("a", "synthetic"), AdvisorCredentials("b", "synthetic")),
    )
    assert result.suite_version
    assert [row.matches_expected for row in result.variants[0].cases] == [True, False, None]
    assert result.variants[0].cases[2].status == "timeout"
    assert result.variants[0].status == "partial"
    assert result.variants[1].status == "ok"
    assert all(row.matches_expected for row in result.variants[1].cases)
    assert result.variants[1].cases[0].input_tokens is None
    assert result.variants[1].cases[0].output_tokens is None
    assert call.await_count == telemetry.await_count == 6
    payloads = [entry.kwargs for entry in call.await_args_list]
    assert all(not payload["store"] and "tools" not in payload for payload in payloads)
    assert [row["input"] for row in payloads[:3]] == [row["input"] for row in payloads[3:]]
    assert len({row["input"] for row in payloads[:3]}) == 3
    assert all(
        entry.kwargs["base_url"] == "https://api.openai.com/v1" for entry in factory.call_args_list
    )


@pytest.mark.parametrize(("allowed", "status"), [(True, 422), (False, 429)])
async def test_benchmark_denial_has_no_provider_calls_and_no_profile_change(
    monkeypatch,
    allowed,
    status,
):
    owner = SimpleNamespace(id=uuid4())
    profile = SimpleNamespace(model="active", encrypted_key=None)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: owner
    check = AsyncMock(return_value=rate_limit.RateLimitResult(allowed, 60, "test"))
    monkeypatch.setattr(rate_limit, "check_rate_limit", check)
    monkeypatch.setattr(rate_limit, "log_security_event", AsyncMock())
    monkeypatch.setattr(routes, "get_profile", AsyncMock(return_value=profile))
    resolve = MagicMock(side_effect=[AdvisorCredentials("a", "synthetic"), ModelUnavailable()])
    monkeypatch.setattr(routes, "resolve_credentials", resolve)
    compare = AsyncMock()
    monkeypatch.setattr(routes, "compare_configs", compare, raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/settings/benchmark",
            json={
                "variants": [
                    {"model": "a", "instructions": None},
                    {"model": "b", "instructions": None},
                ],
            },
        )
    assert response.status_code == status
    check.assert_awaited_once()
    assert check.await_args.args[:2] == ("advisor-benchmark", str(owner.id))
    compare.assert_not_awaited()
    assert profile.model == "active"
    if allowed:
        assert resolve.call_count == 2
    else:
        resolve.assert_not_called()


async def test_benchmark_resolves_drafts_without_saving_them(monkeypatch):
    from app.advisor.ai_benchmark import BenchmarkResult

    owner = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    profile = SimpleNamespace(model="active", encrypted_key=None)
    fetch = AsyncMock(return_value=profile)
    compare = AsyncMock(return_value=BenchmarkResult(variants=[]))
    monkeypatch.setattr(routes, "get_profile", fetch)
    monkeypatch.setattr(routes, "compare_configs", compare)
    monkeypatch.setattr(routes.settings, "LLM_MODEL", "active")
    monkeypatch.setattr(routes.settings, "OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(routes.settings, "ADVISOR_ALLOWED_SERVER_MODELS", ("allowed",))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/settings/benchmark",
            json={
                "variants": [
                    {"model": "active", "instructions": "First"},
                    {"model": "allowed", "instructions": "Second"},
                ],
            },
        )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    fetch.assert_awaited_once_with(db, owner.id)
    compare.assert_awaited_once()
    call = compare.await_args
    assert call.args[0] == owner.id
    assert [variant.instructions for variant in call.args[1]] == ["First", "Second"]
    assert call.kwargs["credentials"] == (
        AdvisorCredentials("active", "synthetic"),
        AdvisorCredentials("allowed", "synthetic"),
    )
    assert profile.model == "active"
    db.add.assert_not_called()
    assert "synthetic" not in response.text
