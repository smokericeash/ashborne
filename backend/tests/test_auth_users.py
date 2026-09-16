from __future__ import annotations

import httpx

from tests.conftest import authorization


async def test_login_me_refresh_rotation_and_logout(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    headers = authorization(admin_tokens)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.local"
    assert me.json()["role"] == "ADMINISTRATOR"

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": admin_tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != admin_tokens["refresh_token"]

    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": admin_tokens["refresh_token"]})
    assert reuse.status_code == 401
    family_revoked = await client.post("/api/v1/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})
    assert family_revoked.status_code == 401

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-token"})
    assert logout.status_code == 204


async def test_invalid_login_is_generic_and_audited(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    request_id = "r" * 64
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.local", "password": "WrongPassword123!"},
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid email or password"
    audit = await client.get(
        "/api/v1/audit", params={"event_type": "USER_LOGIN_FAILURE"}, headers=authorization(admin_tokens)
    )
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["items"][0]["request_id"] == request_id
    assert "password" not in str(audit.json()).lower()


async def test_user_management_rbac_and_last_admin_guard(
    client: httpx.AsyncClient, admin_tokens: dict, viewer_tokens: dict
) -> None:
    forbidden = await client.get("/api/v1/users", headers=authorization(viewer_tokens))
    assert forbidden.status_code == 403
    created = await client.post(
        "/api/v1/users",
        headers=authorization(admin_tokens),
        json={
            "email": "analyst@example.local",
            "display_name": "Analyst",
            "password": "AnalystPassword123!",
            "role": "VIEWER",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    updated = await client.patch(
        f"/api/v1/users/{user_id}", headers=authorization(admin_tokens), json={"role": "OPERATOR"}
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "OPERATOR"
    analyst_session = await client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@example.local", "password": "AnalystPassword123!"},
    )
    assert analyst_session.status_code == 200
    deactivated = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=authorization(admin_tokens),
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    reactivated = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=authorization(admin_tokens),
        json={"is_active": True},
    )
    assert reactivated.status_code == 200
    stale_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": analyst_session.json()["refresh_token"]},
    )
    assert stale_refresh.status_code == 401
    admin_id = admin_tokens["user"]["id"]
    guarded = await client.patch(
        f"/api/v1/users/{admin_id}", headers=authorization(admin_tokens), json={"role": "VIEWER"}
    )
    assert guarded.status_code == 409

    blank_name = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=authorization(admin_tokens),
        json={"display_name": "   "},
    )
    assert blank_name.status_code == 422
    for field in ("display_name", "role", "is_active"):
        explicit_null = await client.patch(
            f"/api/v1/users/{user_id}",
            headers=authorization(admin_tokens),
            json={field: None},
        )
        assert explicit_null.status_code == 422


async def test_security_headers_validation_redaction_and_body_limit(client: httpx.AsyncClient) -> None:
    unauthenticated_stream = await client.get("/api/v1/events/stream")
    assert unauthenticated_stream.status_code == 401

    generated = await client.get("/health/live")
    assert len(generated.headers["x-request-id"]) == 36

    health = await client.get("/health/live", headers={"X-Request-ID": "valid-request-id"})
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert health.headers["x-request-id"] == "valid-request-id"

    docs = await client.get("/docs")
    assert docs.status_code == 200
    assert "https://cdn.jsdelivr.net" in docs.text
    assert "https://cdn.jsdelivr.net" in docs.headers["content-security-policy"]

    invalid = await client.post("/api/v1/auth/login", json={"email": "not-email", "password": "secret-value"})
    assert invalid.status_code == 422
    assert "secret-value" not in invalid.text

    oversized = await client.post(
        "/api/v1/auth/login",
        content=b"x" * 1_100_000,
        headers={
            "Content-Type": "application/json",
            "Origin": "http://localhost:3000",
            "X-Request-ID": "oversized-request",
        },
    )
    assert oversized.status_code == 413
    assert oversized.headers["x-request-id"] == "oversized-request"
    assert oversized.headers["content-security-policy"].startswith("default-src 'none'")
    assert oversized.headers["access-control-allow-origin"] == "http://localhost:3000"

    async def oversized_chunks():
        for _ in range(17):
            yield b"x" * 65_536

    chunked = await client.post(
        "/api/v1/auth/login",
        content=oversized_chunks(),
        headers={"Content-Type": "application/json", "X-Request-ID": "chunked-request"},
    )
    assert chunked.status_code == 413
    assert chunked.headers["x-request-id"] == "chunked-request"
