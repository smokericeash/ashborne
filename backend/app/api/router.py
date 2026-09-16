from fastapi import APIRouter

from app.api.routes import agents, audit, auth, dashboard, enrollment, events, settings, tasks, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(enrollment.router)
api_router.include_router(agents.router)
api_router.include_router(tasks.agent_router)
api_router.include_router(tasks.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
api_router.include_router(events.router)
