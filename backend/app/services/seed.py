from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.core.config import Settings, get_settings
from app.models import Role, RoleName, User

logger = logging.getLogger("ashborne.seed")

ROLE_DESCRIPTIONS = {
    RoleName.ADMINISTRATOR: "Full platform administration",
    RoleName.OPERATOR: "Lab-host operations and approved adversary-emulation tasking",
    RoleName.VIEWER: "Read-only platform access",
}


async def ensure_roles(db: AsyncSession) -> None:
    existing = set((await db.execute(select(Role.name))).scalars().all())
    for role, description in ROLE_DESCRIPTIONS.items():
        if role not in existing:
            db.add(Role(name=role, description=description))
    await db.flush()


async def seed_development(db: AsyncSession, settings: Settings | None = None) -> list[str]:
    config = settings or get_settings()
    await ensure_roles(db)
    if not config.seed_development:
        await db.commit()
        return []
    if config.environment == "production":
        raise RuntimeError("development seed is disabled in production")
    candidates = [
        ("admin@example.local", "ASHBORNE Administrator", RoleName.ADMINISTRATOR, config.admin_password),
        ("operator@example.local", "ASHBORNE Operator", RoleName.OPERATOR, config.operator_password),
        ("viewer@example.local", "ASHBORNE Viewer", RoleName.VIEWER, config.viewer_password),
    ]
    created: list[str] = []
    for email, display_name, role, password in candidates:
        if password is None:
            logger.warning("development seed skipped %s because its password environment variable is unset", email)
            continue
        raw = password.get_secret_value()
        if (
            len(raw) < 12
            or len(raw) > 128
            or not (
                any(character.islower() for character in raw)
                and any(character.isupper() for character in raw)
                and any(character.isdigit() for character in raw)
            )
        ):
            raise RuntimeError(
                f"development password for {email} must be 12-128 characters "
                "and include upper-case, lower-case, and numeric characters"
            )
        if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
            continue
        db.add(User(email=email, display_name=display_name, password_hash=hash_password(raw), role=role))
        created.append(email)
    await db.commit()
    return created
