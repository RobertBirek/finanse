"""Integration tests for identity authentication endpoints."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import get_db
from app.identity.models import User
from app.identity.service import create_session, revoke_session
from app.main import app

TASK2_ENVIRONMENT_VARIABLES = (
    "TRUSTED_ORIGINS",
    "CORS_ORIGINS",
    "ENVIRONMENT",
    "REGISTRATION_ENABLED",
    "SESSION_EXPIRE_MINUTES",
    "LOGIN_RATE_LIMIT",
    "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
    "ADVISOR_RATE_LIMIT",
    "ADVISOR_RATE_LIMIT_WINDOW_SECONDS",
    "UPLOAD_RATE_LIMIT",
    "UPLOAD_RATE_LIMIT_WINDOW_SECONDS",
    "SECRET_KEY",
)


@pytest.fixture
def task2_environment(monkeypatch):
    for variable in TASK2_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


@pytest_asyncio.fixture
async def identity_client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


class TestPasswordHashing:
    def test_hash_and_verify(self):
        from app.identity.service import hash_password, verify_password

        hashed = hash_password("secure_password_123")
        assert hashed != "secure_password_123"
        assert verify_password("secure_password_123", hashed)
        assert not verify_password("wrong", hashed)


@pytest.mark.integration
class TestRegisterAndLogin:
    async def test_register_issues_session_and_csrf_cookies(self, identity_client):
        response = await identity_client.post(
            "/api/auth/register",
            json={
                "email": "register@example.com",
                "password": "TestPass123!",
                "display_name": "Test User",
            },
        )

        assert response.status_code == 201
        assert response.json()["email"] == "register@example.com"
        cookies = response.headers.get_list("set-cookie")
        assert any("advisor_session=" in cookie and "HttpOnly" in cookie for cookie in cookies)
        assert any("advisor_csrf=" in cookie and "HttpOnly" not in cookie for cookie in cookies)

    async def test_login_returns_empty_response_and_cookie_authenticates_me(self, identity_client):
        await identity_client.post(
            "/api/auth/register",
            json={
                "email": "login@example.com",
                "password": "TestPass123!",
                "display_name": "Login User",
            },
        )
        response = await identity_client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "TestPass123!"},
        )

        assert response.status_code == 204
        assert response.content == b""
        assert "access_token" not in response.text
        cookies = response.headers.get_list("set-cookie")
        assert any(
            "advisor_session=" in cookie
            and "HttpOnly" in cookie
            and "SameSite=strict" in cookie
            and "Path=/" in cookie
            for cookie in cookies
        )
        assert any(
            "advisor_csrf=" in cookie
            and "HttpOnly" not in cookie
            and "SameSite=strict" in cookie
            and "Path=/" in cookie
            for cookie in cookies
        )

        me = await identity_client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "login@example.com"

    async def test_bearer_token_does_not_authenticate(self, identity_client):
        response = await identity_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer anything"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test_expired_and_revoked_session_cookies_return_generic_unauthorized(
        self, identity_client, db_session
    ):
        from datetime import UTC, datetime, timedelta

        await identity_client.post(
            "/api/auth/register",
            json={
                "email": "expired@example.com",
                "password": "TestPass123!",
                "display_name": "Expired User",
            },
        )
        user = (
            await db_session.execute(select(User).where(User.email == "expired@example.com"))
        ).scalar_one()
        expired_token, _, expired_session = await create_session(db_session, user.id)
        expired_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        revoked_token, _, _ = await create_session(db_session, user.id)
        assert await revoke_session(db_session, revoked_token)

        for token in (expired_token, revoked_token):
            response = await identity_client.get(
                "/api/auth/me", headers={"Cookie": f"advisor_session={token}"}
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Not authenticated"

    async def test_logout_revokes_only_its_exact_session(self, identity_client, db_session):
        credentials = {
            "email": "sessions@example.com",
            "password": "TestPass123!",
            "display_name": "Sessions User",
        }
        await identity_client.post("/api/auth/register", json=credentials)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as second_client:
            first_login = await identity_client.post("/api/auth/login", json=credentials)
            original_token = first_login.cookies.get("advisor_session")
            second_login = await second_client.post("/api/auth/login", json=credentials)
            assert original_token is not None
            assert second_login.status_code == 204

            logout = await identity_client.post("/api/auth/logout")
            assert logout.status_code == 204
            assert (await identity_client.get("/api/auth/me")).status_code == 401

            replay = await second_client.get(
                "/api/auth/me", headers={"Cookie": f"advisor_session={original_token}"}
            )
            assert replay.status_code == 401
            assert (await second_client.get("/api/auth/me")).status_code == 200

    async def test_login_wrong_password(self, identity_client):
        await identity_client.post(
            "/api/auth/register",
            json={
                "email": "wrongpass@example.com",
                "password": "TestPass123!",
                "display_name": "User",
            },
        )
        response = await identity_client.post(
            "/api/auth/login",
            json={"email": "wrongpass@example.com", "password": "WrongPassword1"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_returns_not_found_in_production_before_user_creation(task2_environment):
    from app.config import Settings
    from app.identity import router as identity_router

    get_user_by_email = AsyncMock()
    create_user = AsyncMock()
    create_session = AsyncMock()
    production_settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="s" * 32,
        TRUSTED_ORIGINS="https://app.example",
    )

    async def override_get_db():
        yield object()

    task2_environment.setattr(identity_router, "settings", production_settings)
    task2_environment.setattr(identity_router, "get_user_by_email", get_user_by_email)
    task2_environment.setattr(identity_router, "create_user", create_user)
    task2_environment.setattr(identity_router, "create_session", create_session)
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "production@example.com",
                    "password": "TestPass123!",
                    "display_name": "Production User",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    get_user_by_email.assert_not_awaited()
    create_user.assert_not_awaited()
