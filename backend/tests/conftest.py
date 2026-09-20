from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio

os.environ.update(
    {
        "ASHBORNE_ENVIRONMENT": "test",
        "ASHBORNE_DATABASE_URL": "sqlite+aiosqlite:///./ashborne-test.db",
        "ASHBORNE_SECRET_KEY": "test-only-secret-that-is-long-enough-1234567890",
        "ASHBORNE_REDIS_URL": "",
        "ASHBORNE_AUTO_CREATE_TABLES": "true",
        "ASHBORNE_SEED_DEVELOPMENT": "true",
        "ASHBORNE_ADMIN_PASSWORD": "AdminPassword123!",
        "ASHBORNE_OPERATOR_PASSWORD": "OperatorPassword123!",
        "ASHBORNE_VIEWER_PASSWORD": "ViewerPassword123!",
        "ASHBORNE_DEMO_BOOTSTRAP_SECRET": "demo-test-secret-1234567890",
        "ASHBORNE_RATE_LIMIT_REQUESTS": "10000",
        "ASHBORNE_LOGIN_RATE_LIMIT_REQUESTS": "1000",
        "ASHBORNE_SESSION_TIMEOUT_MINUTES": "60",
    }
)

from app.core.database import Base, SessionLocal, engine
from app.main import app
from app.services.seed import seed_development


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed_development(db)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest_asyncio.fixture
async def admin_tokens(client: httpx.AsyncClient) -> dict:
    return await login(client, "admin@example.local", "AdminPassword123!")


@pytest_asyncio.fixture
async def operator_tokens(client: httpx.AsyncClient) -> dict:
    return await login(client, "operator@example.local", "OperatorPassword123!")


@pytest_asyncio.fixture
async def viewer_tokens(client: httpx.AsyncClient) -> dict:
    return await login(client, "viewer@example.local", "ViewerPassword123!")


def authorization(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}
