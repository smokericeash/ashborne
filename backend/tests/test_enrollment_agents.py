from __future__ import annotations

import uuid
from datetime import timedelta

import httpx

from app.core.database import SessionLocal
from app.core.time import utcnow
from app.models import Agent, EnrollmentToken
from tests.conftest import authorization


def identity(agent_id: str | None = None, *, ip: str = "10.20.30.40") -> dict:
    return {
        "agent_id": agent_id or str(uuid.uuid4()),
        "name": "lab-node-01",
        "hostname": "lab-node-01",
        "username": "kandor",
        "operating_system": "Linux",
        "os_version": "6.8",
        "architecture": "x86_64",
        "agent_version": "0.1.0",
        "ip_address": ip,
        "tags": ["lab", "demo"],
    }


async def create_enrolled_agent(client: httpx.AsyncClient, admin_tokens: dict) -> tuple[dict, dict]:
    token = await client.post(
        "/api/v1/enrollment/tokens", headers=authorization(admin_tokens), json={"expires_in_seconds": 600}
    )
    assert token.status_code == 201, token.text
    payload = identity()
    enrolled = await client.post("/api/v1/enrollment", json={**payload, "token": token.json()["token"]})
    assert enrolled.status_code == 201, enrolled.text
    return payload, enrolled.json()


async def test_one_time_enrollment_and_reuse_rejected(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    token = await client.post(
        "/api/v1/enrollment/tokens",
        headers=authorization(admin_tokens),
        json={"expires_in_seconds": 600, "description": "pytest"},
    )
    assert token.status_code == 201
    assert token.json()["token"].startswith("ket_")
    payload = identity()
    first = await client.post("/api/v1/enrollment", json={**payload, "token": token.json()["token"]})
    assert first.status_code == 201, first.text
    assert first.json()["credential"].startswith("kac_")
    assert first.json()["agent"]["agent_id"] == payload["agent_id"]

    second = await client.post("/api/v1/enrollment", json={**identity(), "token": token.json()["token"]})
    assert second.status_code == 401
    listing = await client.get("/api/v1/enrollment/tokens", headers=authorization(admin_tokens))
    assert listing.json()["items"][0]["token"] is None
    assert listing.json()["items"][0]["used_at"] is not None


async def test_expired_and_revoked_enrollment_tokens(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    created = await client.post(
        "/api/v1/enrollment/tokens", headers=authorization(admin_tokens), json={"expires_in_seconds": 600}
    )
    token_data = created.json()
    async with SessionLocal() as db:
        row = await db.get(EnrollmentToken, token_data["id"])
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()
    expired = await client.post("/api/v1/enrollment", json={**identity(), "token": token_data["token"]})
    assert expired.status_code == 401

    active = await client.post(
        "/api/v1/enrollment/tokens", headers=authorization(admin_tokens), json={"expires_in_seconds": 600}
    )
    revoked = await client.delete(
        f"/api/v1/enrollment/tokens/{active.json()['id']}", headers=authorization(admin_tokens)
    )
    assert revoked.status_code == 204
    rejected = await client.post("/api/v1/enrollment", json={**identity(), "token": active.json()["token"]})
    assert rejected.status_code == 401


async def test_heartbeat_auth_status_transitions_and_search(client: httpx.AsyncClient, admin_tokens: dict) -> None:
    payload, enrolled = await create_enrolled_agent(client, admin_tokens)
    credential = enrolled["credential"]
    agent_id = payload["agent_id"]
    auth = {"Authorization": f"Bearer {credential}"}
    wrong_path = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/heartbeat",
        headers=auth,
        json={"agent_version": "0.1.0", "hostname": "node", "uptime_seconds": 10},
    )
    assert wrong_path.status_code == 403
    heartbeat = await client.post(
        f"/api/v1/agents/{agent_id}/heartbeat",
        headers=auth,
        json={
            "timestamp": utcnow().isoformat(),
            "agent_version": "0.1.1",
            "hostname": "lab-node-01",
            "uptime_seconds": 123,
            "health": {"cpu_percent": 11.5},
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["status"] == "ONLINE"

    search = await client.get("/api/v1/agents", params={"search": "10.20.30.40"}, headers=authorization(admin_tokens))
    assert search.status_code == 200
    assert search.json()["total"] == 1
    by_tag = await client.get("/api/v1/agents", params={"tag": "DEMO"}, headers=authorization(admin_tokens))
    assert by_tag.status_code == 200
    assert by_tag.json()["total"] == 1
    missing_tag = await client.get("/api/v1/agents", params={"tag": "missing"}, headers=authorization(admin_tokens))
    assert missing_tag.status_code == 200
    assert missing_tag.json()["total"] == 0

    async with SessionLocal() as db:
        agent = await db.get(Agent, agent_id)
        assert agent is not None
        agent.last_seen = utcnow() - timedelta(seconds=120)
        await db.commit()
    degraded = await client.get(f"/api/v1/agents/{agent_id}", headers=authorization(admin_tokens))
    assert degraded.json()["status"] == "DEGRADED"
    status_audit = await client.get(
        "/api/v1/audit",
        params={"event_type": "AGENT_STATUS_CHANGED", "agent": agent_id},
        headers=authorization(admin_tokens),
    )
    assert any(item["metadata"].get("current") == "DEGRADED" for item in status_audit.json()["items"])
    async with SessionLocal() as db:
        agent = await db.get(Agent, agent_id)
        assert agent is not None
        agent.last_seen = utcnow() - timedelta(seconds=400)
        await db.commit()
    offline = await client.get(f"/api/v1/agents/{agent_id}", headers=authorization(admin_tokens))
    assert offline.json()["status"] == "OFFLINE"


async def test_demo_enrollment_is_dev_only_secret_gated_and_rotates(client: httpx.AsyncClient) -> None:
    payload = identity()
    denied = await client.post("/api/v1/enrollment/demo", json=payload)
    assert denied.status_code == 401
    headers = {"X-Kandor-Demo-Secret": "demo-test-secret-1234567890"}
    first = await client.post("/api/v1/enrollment/demo", json=payload, headers=headers)
    assert first.status_code == 201
    second = await client.post("/api/v1/enrollment/demo", json=payload, headers=headers)
    assert second.status_code == 201
    assert second.json()["credential"] != first.json()["credential"]
    old_credential = {"Authorization": f"Bearer {first.json()['credential']}"}
    old_denied = await client.post(
        f"/api/v1/agents/{payload['agent_id']}/heartbeat",
        headers=old_credential,
        json={"agent_version": "0.1.0", "hostname": "node"},
    )
    assert old_denied.status_code == 401
