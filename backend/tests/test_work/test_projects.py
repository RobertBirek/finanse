"""Tests for work domain."""

import os
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.work import service as work_service
from app.work.schemas import TimeBlockCreate
from app.work.service import create_time_block, get_today_schedule


class TestWorkAPI:
    pytestmark = pytest.mark.integration

    @pytest.mark.asyncio
    async def test_create_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "work@example.com",
                    "password": "TestPass123!",
                    "display_name": "Work User",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "work@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/work/projects",
                headers=headers,
                json={
                    "name": "Personal Advisor MVP",
                    "description": "Build the first version",
                    "status": "active",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Personal Advisor MVP"
            assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_projects(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "list@example.com",
                    "password": "TestPass123!",
                    "display_name": "List User",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "list@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            await client.post(
                "/api/work/projects",
                headers=headers,
                json={
                    "name": "Project A",
                    "status": "active",
                },
            )
            await client.post(
                "/api/work/projects",
                headers=headers,
                json={
                    "name": "Project B",
                    "status": "completed",
                },
            )

            response = await client.get("/api/work/projects", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    @pytest.mark.asyncio
    async def test_create_task_with_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "task@example.com",
                    "password": "TestPass123!",
                    "display_name": "Task User",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "task@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            proj_resp = await client.post(
                "/api/work/projects",
                headers=headers,
                json={
                    "name": "MVP",
                    "status": "active",
                },
            )
            project_id = proj_resp.json()["id"]

            response = await client.post(
                "/api/work/tasks",
                headers=headers,
                json={
                    "title": "Implement ledger",
                    "project_id": project_id,
                    "priority": "high",
                    "estimated_minutes": 240,
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["title"] == "Implement ledger"
            assert data["project_id"] == project_id
            assert data["status"] == "todo"

    @pytest.mark.asyncio
    async def test_task_without_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "notask@example.com",
                    "password": "TestPass123!",
                    "display_name": "NoTask",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "notask@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/work/tasks",
                headers=headers,
                json={
                    "title": "Buy groceries",
                    "priority": "medium",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["project_id"] is None

    @pytest.mark.asyncio
    async def test_time_block(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "time@example.com",
                    "password": "TestPass123!",
                    "display_name": "Time User",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "time@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/work/time-blocks",
                headers=headers,
                json={
                    "start_time": "2026-08-10T09:00:00Z",
                    "end_time": "2026-08-10T11:00:00Z",
                    "block_type": "deep_work",
                    "title": "Implementacja księgi",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["block_type"] == "deep_work"
            assert data["title"] == "Implementacja księgi"

    @pytest.mark.asyncio
    async def test_time_block_invalid_range(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/auth/register",
                json={
                    "email": "invalid@example.com",
                    "password": "TestPass123!",
                    "display_name": "Invalid",
                },
            )
            login_resp = await client.post(
                "/api/auth/login",
                json={
                    "email": "invalid@example.com",
                    "password": "TestPass123!",
                },
            )
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                "/api/work/time-blocks",
                headers=headers,
                json={
                    "start_time": "2026-08-10T11:00:00Z",
                    "end_time": "2026-08-10T09:00:00Z",
                    "block_type": "deep_work",
                    "title": "Invalid range",
                },
            )
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_today_schedule_uses_local_midnight_boundaries(self, db_session, monkeypatch):
        previous_tz = os.environ.get("TZ")
        monkeypatch.setenv("TZ", "Europe/Warsaw")
        time.tzset()

        try:
            local_zone = ZoneInfo("Europe/Warsaw")
            local_today = datetime.now(UTC).astimezone(local_zone).date()
            local_start = datetime.combine(local_today, dt_time.min, tzinfo=local_zone)
            next_local_start = datetime.combine(
                local_today + timedelta(days=1), dt_time.min, tzinfo=local_zone
            )
            user_id = uuid.uuid4()

            at_local_start = await create_time_block(
                db_session,
                user_id,
                TimeBlockCreate(
                    title="Local midnight",
                    start_time=(local_start + timedelta(minutes=30)).astimezone(UTC),
                    end_time=(local_start + timedelta(hours=1)).astimezone(UTC),
                ),
            )
            after_local_day = await create_time_block(
                db_session,
                user_id,
                TimeBlockCreate(
                    title="Next local midnight",
                    start_time=(next_local_start + timedelta(minutes=30)).astimezone(UTC),
                    end_time=(next_local_start + timedelta(hours=1)).astimezone(UTC),
                ),
            )

            schedule = await get_today_schedule(db_session, user_id)

            assert [block.id for block in schedule["time_blocks"]] == [at_local_start.id]
            assert after_local_day.id not in [block.id for block in schedule["time_blocks"]]
        finally:
            if previous_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous_tz
            time.tzset()


@pytest.mark.parametrize(
    ("local_date", "expected_start", "expected_end"),
    [
        (
            date(2026, 3, 29),
            datetime(2026, 3, 28, 23, tzinfo=UTC),
            datetime(2026, 3, 29, 22, tzinfo=UTC),
        ),
        (
            date(2026, 10, 25),
            datetime(2026, 10, 24, 22, tzinfo=UTC),
            datetime(2026, 10, 25, 23, tzinfo=UTC),
        ),
    ],
)
def test_local_day_utc_bounds_use_date_specific_dst_offset(
    monkeypatch, local_date, expected_start, expected_end
):
    previous_tz = os.environ.get("TZ")
    monkeypatch.setenv("TZ", "Europe/Warsaw")
    time.tzset()

    try:
        bounds_helper = getattr(work_service, "_local_day_utc_bounds", None)
        assert bounds_helper is not None
        assert bounds_helper(local_date) == (expected_start, expected_end)
    finally:
        if previous_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_tz
        time.tzset()
