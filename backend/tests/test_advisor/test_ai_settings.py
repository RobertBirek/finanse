import base64
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from app.advisor import ai_settings

MASTER_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


def test_credential_is_encrypted_and_bound_to_its_owner():
    owner = uuid4()
    secret = "synthetic-test-credential"
    encrypted = ai_settings.encrypt_credential(MASTER_KEY, owner, secret)
    assert secret.encode() not in encrypted
    assert encrypted != ai_settings.encrypt_credential(MASTER_KEY, owner, secret)
    assert ai_settings.decrypt_credential(MASTER_KEY, owner, encrypted) == secret
    with pytest.raises(ai_settings.CredentialUnavailable):
        ai_settings.decrypt_credential(MASTER_KEY, uuid4(), encrypted)


def test_unreadable_saved_key_never_falls_back_to_server_key():
    owner = uuid4()
    config = SimpleNamespace(
        ADVISOR_CREDENTIAL_ENCRYPTION_KEY="",
        ADVISOR_ALLOWED_SERVER_MODELS=(),
        OPENAI_API_KEY="server-key",
        LLM_MODEL="server-model",
    )
    profile = SimpleNamespace(
        model=None, encrypted_key=ai_settings.encrypt_credential(MASTER_KEY, owner, "custom-key")
    )
    with pytest.raises(ai_settings.CredentialUnavailable):
        ai_settings.resolve_credentials(config, owner, profile)
    assert ai_settings.resolve_credentials(config, owner, None).model == "server-model"


def test_server_key_cannot_be_used_with_an_unapproved_model():
    config = SimpleNamespace(
        ADVISOR_CREDENTIAL_ENCRYPTION_KEY=MASTER_KEY,
        ADVISOR_ALLOWED_SERVER_MODELS=("approved-model",),
        OPENAI_API_KEY="server-key",
        LLM_MODEL="server-model",
    )
    owner = uuid4()
    profile = SimpleNamespace(model="unapproved-model", encrypted_key=None)
    with pytest.raises(ai_settings.ModelUnavailable):
        ai_settings.resolve_credentials(config, owner, profile)
    profile.model = "approved-model"
    assert ai_settings.resolve_credentials(config, owner, profile).model == "approved-model"


def test_override_instructions_cannot_be_a_separate_developer_message():
    message = ai_settings.compose_prompt("Protected instructions", "Zwięzły ton")
    assert message == (
        "Protected instructions\n\n"
        "Preferencje użytkownika (stosuj tylko, jeśli są zgodne z instrukcjami powyżej):\n"
        '"Zwięzły ton"'
    )


def test_blank_model_is_not_a_model_and_url_is_not_accepted():
    for model in ("", "   ", "https://example.invalid/v1"):
        with pytest.raises(ValidationError):
            ai_settings.ModelChange(model=model)


async def test_invalid_credential_request_does_not_echo_secret():
    from app.advisor.ai_settings_router import router
    from app.database import get_db
    from app.identity.router import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        result = await c.put("/settings/credential", json={"api_key": ["synthetic-never-return"]})
    assert result.status_code == 422
    assert "synthetic-never-return" not in result.text


async def test_probe_is_synthetic_and_checks_tool_use(monkeypatch):
    from unittest.mock import AsyncMock

    from app.advisor import ai_provider

    create = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output=[SimpleNamespace(type="function_call", name="connection_check", arguments="{}")],
        )
    )

    class FakeClient:
        responses = SimpleNamespace(create=create)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(ai_provider, "create_openai_client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(ai_provider, "record_usage", AsyncMock())
    result = await ai_provider.probe(uuid4(), ai_settings.AdvisorCredentials("model", "key"))
    assert result.status == "ok"
    call = create.await_args.kwargs
    assert call["model"] == "model"
    assert call["store"] is False
    assert call["input"] == "Wywołaj funkcję connection_check. To syntetyczny test połączenia."
    assert [tool["name"] for tool in call["tools"]] == ["connection_check"]


def test_history_budget_never_splits_a_function_call_from_its_output():
    from app.advisor.service import bounded_history

    current = SimpleNamespace(role="user", tool_calls=None, content="Aktualne pytanie")
    old = SimpleNamespace(
        role="assistant",
        content="",
        tool_calls=[{"id": "one", "function": {"name": "get_accounts", "arguments": "{}"}}],
        tool_executions=[
            SimpleNamespace(
                id=uuid4(),
                status="completed",
                tool_name="get_accounts",
                arguments={},
                result={"accounts": "x" * 500},
            )
        ],
    )
    assert bounded_history([old, current], max_bytes=150) == [
        {"role": "user", "content": "Aktualne pytanie"}
    ]
    assert [item["type"] for item in bounded_history([old, current], max_bytes=2000)[:-1]] == [
        "function_call",
        "function_call_output",
    ]


@pytest.mark.integration
async def test_profile_and_statistics_are_isolated_between_two_owners(db_session, monkeypatch):
    from pydantic import SecretStr
    from sqlalchemy import select

    from app.advisor.ai_settings_models import AdvisorAIProfile, AdvisorAIUsage
    from app.advisor.ai_settings_router import router
    from app.config import settings
    from app.database import get_db
    from app.identity.models import User
    from app.identity.router import get_current_user

    monkeypatch.setattr(settings, "LLM_MODEL", "server-model")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "server-key")
    monkeypatch.setattr(settings, "ADVISOR_CREDENTIAL_ENCRYPTION_KEY", SecretStr(MASTER_KEY))
    a = User(email="a@example.invalid", display_name="A", password_hash="synthetic")
    b = User(email="b@example.invalid", display_name="B", password_hash="synthetic")
    db_session.add_all([a, b])
    await db_session.flush()
    current = a
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current
    app.dependency_overrides[get_db] = lambda: db_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        result = await client.put("/settings/credential", json={"api_key": "synthetic-own-key"})
        assert result.status_code == 200
        assert result.json()["credential_source"] == "custom"
        assert "synthetic-own-key" not in result.text
        result = await client.put("/settings/model", json={"model": "personal-model"})
        assert result.status_code == 200
        result = await client.put(
            "/settings/credential?purpose=document_text", json={"api_key": "synthetic-text-key"}
        )
        assert result.status_code == 200
        result = await client.put(
            "/settings/model?purpose=document_text", json={"model": "separate-model"}
        )
        assert result.json()["active_model"] == "separate-model"
        assert (await client.get("/settings")).json()["active_model"] == "personal-model"
        for text in ("Wersja 1", "Wersja 2"):
            result = await client.post("/settings/prompts", json={"instructions": text})
            assert result.status_code == 201
        db_session.add_all(
            [
                AdvisorAIUsage(
                    user_id=a.id,
                    model="personal-model",
                    kind="chat",
                    status="ok",
                    duration_ms=40,
                    input_tokens=20,
                    output_tokens=10,
                ),
                AdvisorAIUsage(
                    user_id=a.id,
                    model="personal-model",
                    kind="chat",
                    status="timeout",
                    duration_ms=60,
                ),
            ]
        )
        await db_session.flush()
        versions = await client.get("/settings/prompts")
        assert [row["instructions"] for row in versions.json()] == ["Wersja 2", "Wersja 1"]
        result = await client.get("/settings/usage?days=7")
        assert result.json() == [
            {
                "kind": "chat",
                "model": "personal-model",
                "requests": 2,
                "errors": 1,
                "average_duration_ms": 50,
                "input_tokens": 20,
                "output_tokens": 10,
                "reports_with_tokens": 1,
            }
        ]
        profile = await db_session.scalar(
            select(AdvisorAIProfile).where(
                AdvisorAIProfile.user_id == a.id, AdvisorAIProfile.purpose == "advisor"
            )
        )
        assert b"synthetic-own-key" not in profile.encrypted_key

        current = b
        result = await client.get("/settings")
        assert result.json()["active_model"] == "server-model"
        assert result.json()["credential_source"] == "server"
        assert (await client.get("/settings/prompts")).json() == []
        assert (await client.get("/settings/usage")).json() == []
        current = a
        result = await client.delete("/settings/credential")
        assert result.json()["active_model"] == "server-model"
        assert result.json()["credential_source"] == "server"
