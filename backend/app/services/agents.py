from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_broker
from app.core.time import ensure_utc, utcnow
from app.models import Agent, AgentStatus
from app.services.audit import record_audit
from app.services.settings import read_settings


async def calculated_status(db: AsyncSession, agent: Agent) -> AgentStatus:
    if agent.removed_at is not None or agent.last_seen is None:
        return AgentStatus.OFFLINE
    settings = await read_settings(db)
    age = (utcnow() - ensure_utc(agent.last_seen)).total_seconds()
    if age <= settings.degraded_threshold_seconds:
        return AgentStatus.ONLINE
    if age <= settings.offline_threshold_seconds:
        return AgentStatus.DEGRADED
    return AgentStatus.OFFLINE


async def refresh_agent_statuses(db: AsyncSession) -> bool:
    agents = (await db.execute(select(Agent).where(Agent.removed_at.is_(None)))).scalars().all()
    changed = False
    for agent in agents:
        computed = await calculated_status(db, agent)
        if agent.status != computed:
            previous = agent.status
            agent.status = computed
            await record_audit(
                db,
                "AGENT_STATUS_CHANGED",
                agent_id=agent.id,
                metadata={"previous": previous.value, "current": computed.value},
            )
            await event_broker.publish(
                "agent.status_changed",
                {"agent_id": agent.id, "previous": previous.value, "status": computed.value},
            )
            changed = True
    if changed:
        await db.flush()
    return changed
