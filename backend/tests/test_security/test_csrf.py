"""Production-only CSRF enforcement integration tests."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.identity.models import Session
from app.identity.schemas import UserCreate
from app.identity.service import create_session, create_user, hash_session_token
from app.main import app

TRUSTED_ORIGIN = "https://app.example"
FORBIDDEN_DETAIL = "Forbidden"


@pytest.fixture
def production_csrf_settings(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", (TRUSTED_ORIGIN,))


@pytest.mark.integration
class TestProductionCsrf:
    async def test_login_requires_a_trusted_origin_but_not_a_session(
        self, db_session, production_csrf_settings
    ):
        user = await create_user(
            db_session,
            UserCreate(
                email="login@example.com",
                password="TestPass123!",
                display_name="Login User",
            ),
        )
        await db_session.commit()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                trusted = await client.post(
                    "/api/auth/login",
                    headers={"Origin": TRUSTED_ORIGIN},
                    json={"email": user.email, "password": "TestPass123!"},
                )
                foreign = await client.post(
                    "/api/auth/login",
                    headers={"Origin": "https://foreign.example"},
                    json={"email": user.email, "password": "TestPass123!"},
                )
                missing = await client.post(
                    "/api/auth/login",
                    json={"email": user.email, "password": "TestPass123!"},
                )
        finally:
            app.dependency_overrides.clear()

        assert trusted.status_code == 204
        assert foreign.status_code == 403
        assert missing.status_code == 403
        assert foreign.json() == missing.json() == {"detail": FORBIDDEN_DETAIL}

    async def test_authenticated_unsafe_requests_require_all_csrf_proofs(
        self, db_session, production_csrf_settings
    ):
        user = await create_user(
            db_session,
            UserCreate(
                email="csrf@example.com",
                password="TestPass123!",
                display_name="CSRF User",
            ),
        )
        session_token, csrf_token, session = await create_session(db_session, user.id)
        session_id = session.id
        original_created_at = session.created_at
        await db_session.commit()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"Origin": TRUSTED_ORIGIN}
                cookie = f"advisor_session={session_token}; advisor_csrf={csrf_token}"
                missing_header = await client.post(
                    "/api/finance/accounts",
                    headers={**headers, "Cookie": cookie},
                    json={"name": "Missing header", "type": "checking", "currency": "PLN"},
                )
                patch_missing_header = await client.patch(
                    "/api/finance/accounts/00000000-0000-0000-0000-000000000000",
                    headers={**headers, "Cookie": cookie},
                    json={"name": "Missing header"},
                )
                delete_missing_header = await client.delete(
                    "/api/finance/accounts/00000000-0000-0000-0000-000000000000",
                    headers={**headers, "Cookie": cookie},
                )
                missing_cookie = await client.post(
                    "/api/finance/accounts",
                    headers={
                        **headers,
                        "X-CSRF-Token": csrf_token,
                        "Cookie": f"advisor_session={session_token}",
                    },
                    json={"name": "Missing cookie", "type": "checking", "currency": "PLN"},
                )
                mismatch = await client.post(
                    "/api/finance/accounts",
                    headers={
                        **headers,
                        "X-CSRF-Token": "wrong",
                        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
                    },
                    json={"name": "Mismatch", "type": "checking", "currency": "PLN"},
                )
                session.csrf_token_hash = hash_session_token("other-token")
                await db_session.flush()
                db_mismatch = await client.post(
                    "/api/finance/accounts",
                    headers={
                        **headers,
                        "X-CSRF-Token": csrf_token,
                        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
                    },
                    json={"name": "DB mismatch", "type": "checking", "currency": "PLN"},
                )
                session.csrf_token_hash = hash_session_token(csrf_token)
                await db_session.flush()
                matching = await client.post(
                    "/api/finance/accounts",
                    headers={
                        **headers,
                        "X-CSRF-Token": csrf_token,
                        "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
                    },
                    json={"name": "Matching", "type": "checking", "currency": "PLN"},
                )
                get_me = await client.get(
                    "/api/auth/me", headers={"Cookie": f"advisor_session={session_token}"}
                )
                options = await client.options("/api/finance/accounts")
        finally:
            app.dependency_overrides.clear()

        rejected = (
            missing_header,
            patch_missing_header,
            delete_missing_header,
            missing_cookie,
            mismatch,
            db_mismatch,
        )
        assert [response.status_code for response in rejected] == [
            403,
            403,
            403,
            403,
            403,
            403,
        ]
        assert {response.json()["detail"] for response in rejected} == {FORBIDDEN_DETAIL}
        assert matching.status_code == 201
        assert get_me.status_code == 200
        assert options.status_code != 403

        persisted = (
            await db_session.execute(select(Session).where(Session.id == session_id))
        ).scalar_one()
        assert persisted.created_at == original_created_at
        assert persisted.token_hash == hash_session_token(session_token)
        assert persisted.csrf_token_hash == hash_session_token(csrf_token)
        assert persisted.last_seen_at is not None

    async def test_csrf_check_does_not_create_or_modify_a_session(
        self, db_session, production_csrf_settings
    ):
        from fastapi import Depends, FastAPI

        from app.security.csrf import require_csrf

        user = await create_user(
            db_session,
            UserCreate(
                email="read-only@example.com",
                password="TestPass123!",
                display_name="Read Only User",
            ),
        )
        session_token, csrf_token, session = await create_session(db_session, user.id)
        session_id = session.id
        original_last_seen_at = session.last_seen_at
        await db_session.commit()

        test_app = FastAPI()

        @test_app.post("/protected", dependencies=[Depends(require_csrf)])
        async def protected():
            return {"ok": True}

        async def override_get_db():
            yield db_session

        test_app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/protected",
                headers={
                    "Origin": TRUSTED_ORIGIN,
                    "X-CSRF-Token": csrf_token,
                    "Cookie": f"advisor_session={session_token}; advisor_csrf={csrf_token}",
                },
            )

        persisted = (
            await db_session.execute(select(Session).where(Session.id == session_id))
        ).scalar_one()
        assert response.status_code == 200
        assert persisted.last_seen_at == original_last_seen_at
        assert persisted.revoked_at is None
        assert (await db_session.execute(select(Session))).scalars().all() == [persisted]
