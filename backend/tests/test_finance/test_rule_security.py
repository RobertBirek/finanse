import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_db
from app.identity.service import create_session
from app.main import app
from tests.test_finance.test_categorization import setup

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_rules_settings_and_every_rule_mutation_require_real_session_csrf(
    db_session, monkeypatch
):
    owner, _, _, marker, _ = await setup(db_session)
    token, csrf, _ = await create_session(db_session, owner)
    await db_session.commit()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "_trusted_origins", ("https://ui.test.invalid",))

    async def database():
        yield db_session

    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://ui.test.invalid"
        ) as client:
            common = {
                "Origin": "https://ui.test.invalid",
                "Cookie": f"advisor_session={token}; advisor_csrf={csrf}",
                "Idempotency-Key": "guarded-test",
            }
            root = "/api/finance/categorization"
            for method, path in [
                ("PATCH", "/settings"),
                ("POST", "/rules"),
                ("PATCH", f"/rules/{uuid.uuid4()}"),
                ("POST", f"/rules/{uuid.uuid4()}/preview"),
                ("POST", f"/rules/{uuid.uuid4()}/approve"),
                ("POST", f"/rules/{uuid.uuid4()}/pause"),
                ("POST", f"/rules/{uuid.uuid4()}/retire"),
            ]:
                result = await client.request(method, root + path, headers=common, json={})
                assert result.status_code == 403, (path, result.text)
            result = await client.patch(
                root + "/settings",
                headers={**common, "X-CSRF-Token": csrf},
                json={
                    "expected_version": 0,
                    "uncategorized_category_id": str(marker.id),
                    "rules_enabled": True,
                    "confirm_future_only": True,
                },
            )
            assert result.status_code == 200, result.text
            unauthenticated = await client.get(root + "/rules")
            assert unauthenticated.status_code == 401
    finally:
        app.dependency_overrides.clear()
