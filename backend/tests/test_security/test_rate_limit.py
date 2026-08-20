import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from starlette.requests import Request

from app.audit.models import AuditEvent
from app.database import get_db
from app.identity.schemas import UserCreate
from app.identity.service import create_session, create_user
from app.main import app

TRUSTED_ORIGIN = "https://app.example"


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str, str]] = []
        self.counts: dict[str, int] = {}

    async def eval(self, script: str, key_count: int, key: str, window_seconds: str) -> list[int]:
        self.calls.append((script, key_count, key, window_seconds))
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], int(window_seconds)]


def request_from(peer_ip: str, forwarded_for: str | None = None) -> Request:
    headers = [] if forwarded_for is None else [(b"x-forwarded-for", forwarded_for.encode())]
    return Request({"type": "http", "client": (peer_ip, 1234), "headers": headers})


def trusted_proxy_resolver(_hosts: tuple[str, ...]) -> set[str]:
    return {"172.20.0.3"}


def test_trusted_frontend_uses_a_single_forwarded_client_ip(monkeypatch):
    from app.security import rate_limit

    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", trusted_proxy_resolver)

    assert rate_limit.get_client_ip(request_from("172.20.0.3", "198.51.100.8")) == "198.51.100.8"


def test_trusted_frontend_chain_falls_back_to_peer(monkeypatch):
    from app.security import rate_limit

    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", trusted_proxy_resolver)

    assert (
        rate_limit.get_client_ip(request_from("172.20.0.3", "198.51.100.8, 10.0.0.4"))
        == "172.20.0.3"
    )


def test_untrusted_peer_cannot_spoof_forwarded_client_ip(monkeypatch):
    from app.security import rate_limit

    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", trusted_proxy_resolver)

    assert rate_limit.get_client_ip(request_from("198.51.100.9", "203.0.113.99")) == "198.51.100.9"


def test_malformed_forwarded_chain_falls_back_to_trusted_peer(monkeypatch):
    from app.security import rate_limit

    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", trusted_proxy_resolver)

    assert (
        rate_limit.get_client_ip(request_from("172.20.0.3", "198.51.100.8, invalid"))
        == "172.20.0.3"
    )


def test_frontend_normalizes_npmplus_client_ip_before_backend() -> None:
    config = (Path(__file__).parents[3] / "frontend" / "nginx.conf").read_text()

    assert "set_real_ip_from 172.22.0.0/16;" in config
    assert "real_ip_header X-Forwarded-For;" in config
    assert "real_ip_recursive on;" in config
    assert config.index("set_real_ip_from") < config.index("location / {")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert "proxy_set_header X-Real-IP $remote_addr;" in config
    assert "$proxy_add_x_forwarded_for" not in config


@pytest.mark.asyncio
async def test_login_dependency_hashes_the_forwarded_client_ip(monkeypatch):
    from app.identity.schemas import UserLogin
    from app.security import rate_limit

    redis = FakeRedis()
    monkeypatch.setattr(rate_limit.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rate_limit.settings, "SECRET_KEY", "s" * 32)
    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", trusted_proxy_resolver)
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)

    await rate_limit.limit_login(
        request_from("172.20.0.3", "198.51.100.8"),
        UserLogin(email="person@example.com", password="TestPass123!"),
    )

    assert rate_limit.hash_identifier("198.51.100.8|person@example.com") in redis.calls[0][2]
    assert "172.20.0.3" not in redis.calls[0][2]


@pytest.mark.asyncio
async def test_production_limit_uses_lua_and_hashed_identifier(monkeypatch):
    from app.security import rate_limit

    redis = FakeRedis()
    monkeypatch.setattr(rate_limit.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rate_limit.settings, "SECRET_KEY", "s" * 32)
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)

    first = await rate_limit.check_rate_limit(
        "login", "203.0.113.7|person@example.com", maximum=1, window_seconds=60
    )
    second = await rate_limit.check_rate_limit(
        "login", "203.0.113.7|person@example.com", maximum=1, window_seconds=60
    )

    assert first.allowed
    assert not second.allowed
    assert second.retry_after == 60
    script, key_count, key, window_seconds = redis.calls[0]
    assert "INCR" in script and "EXPIRE" in script
    assert key_count == 1
    assert window_seconds == "60"
    assert key.startswith("security:rate-limit:v1:login:")
    assert "203.0.113.7" not in key
    assert "person@example.com" not in key


@pytest.mark.asyncio
async def test_development_bypasses_redis_factory(monkeypatch):
    from app.security import rate_limit

    def factory_should_not_run():
        raise AssertionError("development requests must not create a Redis client")

    monkeypatch.setattr(rate_limit.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(rate_limit, "get_redis_client", factory_should_not_run)

    result = await rate_limit.check_rate_limit("advisor", str(uuid.uuid4()), 1, 60)

    assert result.allowed


@pytest.mark.asyncio
async def test_advisor_and_upload_scopes_are_independent(monkeypatch):
    from app.security import rate_limit

    redis = FakeRedis()
    monkeypatch.setattr(rate_limit.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(rate_limit.settings, "SECRET_KEY", "s" * 32)
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    identifier = str(uuid.uuid4())

    assert (await rate_limit.check_rate_limit("advisor", identifier, 1, 60)).allowed
    assert not (await rate_limit.check_rate_limit("advisor", identifier, 1, 60)).allowed
    assert (await rate_limit.check_rate_limit("upload", identifier, 1, 60)).allowed


@pytest.fixture
def production_rate_limit_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", "s" * 32)
    monkeypatch.setattr(settings, "_trusted_origins", (TRUSTED_ORIGIN,))
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT", 1)
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "ADVISOR_RATE_LIMIT", 1)
    monkeypatch.setattr(settings, "ADVISOR_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT", 1)
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT_WINDOW_SECONDS", 60)


@pytest_asyncio.fixture
async def rate_limit_client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
async def test_login_limit_audits_rejection_without_raw_identifiers(
    rate_limit_client, db_session, monkeypatch, production_rate_limit_settings
):
    from app.security import rate_limit

    user = await create_user(
        db_session,
        UserCreate(email="person@example.com", password="TestPass123!", display_name="Person"),
    )
    await db_session.commit()
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    headers = {"Origin": TRUSTED_ORIGIN}

    first = await rate_limit_client.post(
        "/api/auth/login", headers=headers, json={"email": user.email, "password": "TestPass123!"}
    )
    other = await rate_limit_client.post(
        "/api/auth/login",
        headers=headers,
        json={"email": "other@example.com", "password": "TestPass123!"},
    )
    limited = await rate_limit_client.post(
        "/api/auth/login", headers=headers, json={"email": user.email, "password": "TestPass123!"}
    )
    logout = await rate_limit_client.post(
        "/api/auth/logout",
        headers={
            "Origin": TRUSTED_ORIGIN,
            "X-CSRF-Token": first.cookies["advisor_csrf"],
            "Cookie": (
                f"advisor_session={first.cookies['advisor_session']}; "
                f"advisor_csrf={first.cookies['advisor_csrf']}"
            ),
        },
    )

    assert first.status_code == 204
    assert other.status_code == 401
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    events = (
        (await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at)))
        .scalars()
        .all()
    )
    assert logout.status_code == 204
    assert [event.action for event in events] == ["login_success", "rate_limited", "logout"]
    assert all("person@example.com" not in str(event.new_state) for event in events)
    assert all("127.0.0.1" not in str(event.new_state) for event in events)
    assert "person@example.com" not in redis.calls[0][2]


@pytest.mark.integration
async def test_redis_outage_rejects_mutations_but_not_gets(
    rate_limit_client, db_session, monkeypatch, production_rate_limit_settings
):
    from app.security import rate_limit

    user = await create_user(
        db_session,
        UserCreate(email="outage@example.com", password="TestPass123!", display_name="Outage"),
    )
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()

    class OutageRedis:
        async def eval(self, *_args):
            raise TimeoutError

    factory = lambda: OutageRedis()
    monkeypatch.setattr(rate_limit, "get_redis_client", factory)
    headers = {
        "Origin": TRUSTED_ORIGIN,
        "X-CSRF-Token": csrf_token,
        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
    }

    login = await rate_limit_client.post(
        "/api/auth/login",
        headers={"Origin": TRUSTED_ORIGIN},
        json={"email": user.email, "password": "TestPass123!"},
    )
    advisor = await rate_limit_client.post(
        "/api/advisor/messages", headers=headers, json={"content": "hello"}
    )
    upload = await rate_limit_client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("receipt.pdf", b"%PDF", "application/pdf")},
    )
    get_response = await rate_limit_client.get("/api/documents", headers=headers)

    assert [response.status_code for response in (login, advisor, upload)] == [503, 503, 503]
    assert get_response.status_code == 200


@pytest.mark.integration
async def test_advisor_and_upload_routes_audit_their_own_limit_rejections(
    rate_limit_client, db_session, monkeypatch, production_rate_limit_settings
):
    from app.security import rate_limit

    user = await create_user(
        db_session,
        UserCreate(email="limits@example.com", password="TestPass123!", display_name="Limits"),
    )
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: redis)
    monkeypatch.setattr(rate_limit, "resolve_trusted_proxy_hosts", lambda _hosts: set())
    monkeypatch.setattr("app.worker.enqueue_process_document", AsyncMock())
    headers = {
        "Origin": TRUSTED_ORIGIN,
        "X-CSRF-Token": csrf_token,
        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
    }
    advisor_key = f"security:rate-limit:v1:advisor:{rate_limit.hash_identifier(str(user.id))}"
    upload_key = (
        f"security:rate-limit:v1:upload:{rate_limit.hash_identifier(f'{user.id}|127.0.0.1')}"
    )
    redis.counts.update({advisor_key: 1, upload_key: 1})

    advisor = await rate_limit_client.post(
        "/api/advisor/messages", headers=headers, json={"content": "hi"}
    )
    upload = await rate_limit_client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("receipt.pdf", b"%PDF", "application/pdf")},
    )

    events = (
        (await db_session.execute(select(AuditEvent).order_by(AuditEvent.created_at)))
        .scalars()
        .all()
    )
    assert redis.calls[-1][2] == upload_key
    assert advisor.status_code == upload.status_code == 429
    assert advisor.headers["retry-after"] == upload.headers["retry-after"] == "60"
    assert [event.new_state["scope"] for event in events] == ["advisor", "upload"]
    assert all("127.0.0.1" not in str(event.new_state) for event in events)
    assert all("limits@example.com" not in str(event.new_state) for event in events)


@pytest.mark.integration
async def test_rejected_session_audit_is_opaque(rate_limit_client, db_session):
    rejected = await rate_limit_client.get(
        "/api/documents", headers={"Cookie": "advisor_session=raw-session-token"}
    )

    events = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "Not authenticated"}
    assert [event.action for event in events] == ["session_rejected"]
    assert "raw-session-token" not in events[0].entity_id


@pytest.mark.integration
async def test_authenticated_get_does_not_create_a_limiter_client(
    rate_limit_client, db_session, monkeypatch, production_rate_limit_settings
):
    from app.security import rate_limit

    user = await create_user(
        db_session,
        UserCreate(email="read@example.com", password="TestPass123!", display_name="Read"),
    )
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()

    def factory_should_not_run():
        raise AssertionError("authenticated GET must not create a limiter client")

    monkeypatch.setattr(rate_limit, "get_redis_client", factory_should_not_run)
    response = await rate_limit_client.get(
        "/api/documents",
        headers={
            "Origin": TRUSTED_ORIGIN,
            "X-CSRF-Token": csrf_token,
            "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
        },
    )

    assert response.status_code == 200


@pytest.mark.integration
async def test_csrf_rejection_records_only_an_opaque_identifier(
    rate_limit_client, db_session, production_rate_limit_settings
):
    user = await create_user(
        db_session,
        UserCreate(email="csrf@example.com", password="TestPass123!", display_name="CSRF"),
    )
    session_token, csrf_token, _ = await create_session(db_session, user.id)
    await db_session.commit()

    rejected = await rate_limit_client.post(
        "/api/finance/accounts",
        headers={
            "Origin": TRUSTED_ORIGIN,
            "X-CSRF-Token": "attacker-token",
            "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
        },
        json={"name": "Account", "type": "checking", "currency": "PLN"},
    )

    events = (await db_session.execute(select(AuditEvent))).scalars().all()
    assert rejected.status_code == 403
    assert [event.action for event in events] == ["csrf_rejected"]
    assert "attacker-token" not in str(events[0].new_state)
    assert "attacker-token" not in events[0].entity_id
