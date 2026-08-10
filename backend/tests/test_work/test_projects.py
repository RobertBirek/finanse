"""Tests for work domain."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


class TestWorkAPI:
    @pytest.mark.asyncio
    async def test_create_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "work@example.com",
                "password": "TestPass123!",
                "display_name": "Work User",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "work@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post("/api/work/projects", headers=headers, json={
                "name": "Personal Advisor MVP",
                "description": "Build the first version",
                "status": "active",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Personal Advisor MVP"
            assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_projects(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "list@example.com",
                "password": "TestPass123!",
                "display_name": "List User",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "list@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            await client.post("/api/work/projects", headers=headers, json={
                "name": "Project A", "status": "active",
            })
            await client.post("/api/work/projects", headers=headers, json={
                "name": "Project B", "status": "completed",
            })

            response = await client.get("/api/work/projects", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2

    @pytest.mark.asyncio
    async def test_create_task_with_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "task@example.com",
                "password": "TestPass123!",
                "display_name": "Task User",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "task@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            proj_resp = await client.post("/api/work/projects", headers=headers, json={
                "name": "MVP", "status": "active",
            })
            project_id = proj_resp.json()["id"]

            response = await client.post("/api/work/tasks", headers=headers, json={
                "title": "Implement ledger",
                "project_id": project_id,
                "priority": "high",
                "estimated_minutes": 240,
            })
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "Implement ledger"
            assert data["project_id"] == project_id
            assert data["status"] == "todo"

    @pytest.mark.asyncio
    async def test_task_without_project(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "notask@example.com",
                "password": "TestPass123!",
                "display_name": "NoTask",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "notask@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post("/api/work/tasks", headers=headers, json={
                "title": "Buy groceries",
                "priority": "medium",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] is None

    @pytest.mark.asyncio
    async def test_time_block(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "time@example.com",
                "password": "TestPass123!",
                "display_name": "Time User",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "time@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post("/api/work/time-blocks", headers=headers, json={
                "start_time": "2026-08-10T09:00:00Z",
                "end_time": "2026-08-10T11:00:00Z",
                "block_type": "deep_work",
                "title": "Implementacja księgi",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["block_type"] == "deep_work"
            assert data["title"] == "Implementacja księgi"

    @pytest.mark.asyncio
    async def test_time_block_invalid_range(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/auth/register", json={
                "email": "invalid@example.com",
                "password": "TestPass123!",
                "display_name": "Invalid",
            })
            login_resp = await client.post("/api/auth/login", json={
                "email": "invalid@example.com",
                "password": "TestPass123!",
            })
            token = login_resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post("/api/work/time-blocks", headers=headers, json={
                "start_time": "2026-08-10T11:00:00Z",
                "end_time": "2026-08-10T09:00:00Z",
                "block_type": "deep_work",
                "title": "Invalid range",
            })
            assert response.status_code in (400, 422)
