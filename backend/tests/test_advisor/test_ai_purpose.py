from base64 import urlsafe_b64encode
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.advisor.ai_settings import CredentialUnavailable


def test_scoped_credentials_never_decrypt_a_key_from_another_purpose():
    from app.advisor.ai_settings import decrypt_credential, encrypt_credential

    owner = uuid4()
    key = urlsafe_b64encode(bytes(32)).decode()
    value = encrypt_credential(key, owner, "test-key", purpose="receipt")
    assert decrypt_credential(key, owner, value, purpose="receipt") == "test-key"
    with pytest.raises(CredentialUnavailable):
        decrypt_credential(key, owner, value, purpose="vision")


def test_default_configuration_fingerprint_is_preserved_and_edits_are_versioned():
    from app.advisor.ai_purpose import PurposeBaseline, PurposeRuntime
    from app.advisor.ai_settings import AdvisorCredentials

    credentials = AdvisorCredentials("test-model", "test-key")
    default = PurposeRuntime(credentials, None, None)
    assert default.fingerprint("f" * 64) == "f" * 64
    active = replace(default, version=uuid4())
    assert active.fingerprint("f" * 64) != "f" * 64
    assert active.fingerprint("f" * 64) != replace(active, version=uuid4()).fingerprint("f" * 64)
    assert "test-key" not in repr(PurposeBaseline(credentials, True))


def test_openai_overrides_are_fail_closed_without_server_gate(monkeypatch):
    from app.advisor.ai_purpose import PurposeBaseline, resolve_purpose
    from app.advisor.ai_settings import AdvisorCredentials, ModelUnavailable, encrypt_credential
    from app.config import settings

    owner = uuid4()
    secret = urlsafe_b64encode(bytes(32)).decode()
    monkeypatch.setattr(settings, "ADVISOR_CREDENTIAL_ENCRYPTION_KEY", SecretStr(secret))
    ciphertext = encrypt_credential(secret, owner, "own-key", purpose="vision")
    baseline = PurposeBaseline(AdvisorCredentials("base-model", "base-key"), False)
    kwargs = {
        "model": "own-model",
        "encrypted_key": ciphertext,
        "instructions": "style",
        "version": uuid4(),
    }
    with pytest.raises(ModelUnavailable):
        resolve_purpose("vision", owner, baseline, **kwargs)
    effective = resolve_purpose("vision", owner, replace(baseline, operational=True), **kwargs)
    assert effective.credentials == AdvisorCredentials("own-model", "own-key")
    assert effective.instructions == "style"


async def test_runtime_retries_when_edit_races_with_loading_the_prompt(monkeypatch):
    from app.advisor import ai_purpose
    from app.advisor.ai_settings import AdvisorCredentials

    a = SimpleNamespace(configuration_id=uuid4(), model="base", encrypted_key=None)
    b = SimpleNamespace(configuration_id=uuid4(), model="base", encrypted_key=None)
    monkeypatch.setattr(ai_purpose, "get_profile", AsyncMock(side_effect=[a, b, b, b]))
    monkeypatch.setattr(
        ai_purpose,
        "prompt_history",
        AsyncMock(
            side_effect=[
                [SimpleNamespace(instructions="old")],
                [SimpleNamespace(instructions="new")],
            ]
        ),
    )
    result = await ai_purpose.read_purpose(
        None,
        uuid4(),
        "receipt",
        baseline=ai_purpose.PurposeBaseline(AdvisorCredentials("base", "test"), True),
    )
    assert result.version == b.configuration_id
    assert result.instructions == "new"


async def test_image_probe_uses_only_synthetic_image_no_tools_and_records_its_purpose(monkeypatch):
    from app.advisor import ai_provider
    from app.advisor.ai_settings import AdvisorCredentials

    create = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text='{"check":"ok"}')],
                )
            ],
        )
    )

    class Client:
        responses = SimpleNamespace(create=create)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    record = AsyncMock()
    monkeypatch.setattr(ai_provider, "create_openai_client", lambda **_args: Client())
    monkeypatch.setattr(ai_provider, "record_usage", record)
    owner = uuid4()
    result = await ai_provider.probe(
        owner, AdvisorCredentials("synthetic-model", "synthetic-key"), purpose="vision"
    )
    assert result.status == "ok"
    payload = create.await_args.kwargs
    assert "tools" not in payload and payload["store"] is False
    assert [x["type"] for x in payload["input"][0]["content"]] == ["input_text", "input_image"]
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    assert record.await_args.kwargs["purpose"] == "vision"
