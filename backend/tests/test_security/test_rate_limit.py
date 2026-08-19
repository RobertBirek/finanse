import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

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
