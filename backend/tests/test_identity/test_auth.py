"""Tests for identity domain."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def auth_service():
    from app.identity import service

    return service


class TestPasswordHashing:
    def test_hash_and_verify(self, auth_service):
        password = "secure_password_123"
        hashed = auth_service.hash_password(password)
        assert hashed != password
        assert auth_service.verify_password(password, hashed)

    def test_wrong_password(self, auth_service):
        password = "secure_password_123"
        hashed = auth_service.hash_password(password)
        assert not auth_service.verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self, auth_service):
        password = "secure_password_123"
        h1 = auth_service.hash_password(password)
        h2 = auth_service.hash_password(password)
        assert h1 != h2
        assert auth_service.verify_password(password, h1)
        assert auth_service.verify_password(password, h2)


class TestToken:
    def test_create_and_decode_token(self, auth_service):
        from jose import jwt

        from app.config import settings

        user_id = "test-user-id-123"
        token = auth_service.create_access_token(user_id)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == user_id
        assert "exp" in payload


class TestRegisterAndLogin:
    pytestmark = pytest.mark.integration

    @pytest.mark.asyncio
    async def test_register_user(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "test@example.com",
                    "password": "TestPass123!",
                    "display_name": "Test User",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["email"] == "test@example.com"
            assert data["display_name"] == "Test User"
            assert "password_hash" not in data
            assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "dup@example.com",
                    "password": "TestPass123!",
                    "display_name": "User 1",
                },
            )
            response = await client.post(
                "/api/auth/register",
                json={
                    "email": "dup@example.com",
                    "password": "TestPass123!",
                    "display_name": "User 2",
                },
            )
            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_login_success(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "login@example.com",
                    "password": "TestPass123!",
                    "display_name": "Login User",
                },
            )
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": "login@example.com",
                    "password": "TestPass123!",
                },
            )
            assert response.status_code == 200
            assert "access_token" in response.json()
            assert "session" in response.cookies or response.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "wrongpass@example.com",
                    "password": "TestPass123!",
                    "display_name": "User",
                },
            )
            response = await client.post(
                "/api/auth/login",
                json={
                    "email": "wrongpass@example.com",
                    "password": "WrongPassword1",
                },
            )
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_returns_not_found_in_production_before_user_creation(monkeypatch):
    from app.config import Settings
    from app.database import get_db
    from app.identity import router as identity_router

    get_user_by_email = AsyncMock()
    create_user = AsyncMock()
    production_settings = Settings(ENVIRONMENT="production", SECRET_KEY="s" * 32)

    async def override_get_db():
        yield object()

    monkeypatch.setattr(identity_router, "settings", production_settings)
    monkeypatch.setattr(identity_router, "get_user_by_email", get_user_by_email)
    monkeypatch.setattr(identity_router, "create_user", create_user)
    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
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
