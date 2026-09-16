from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from datetime import timedelta

import typer
from sqlalchemy import func, select

from app.auth.security import hash_password, sha256
from app.core.config import get_settings
from app.core.database import SessionLocal, create_schema
from app.core.time import utcnow
from app.models import Agent, EnrollmentToken, RoleName, Task, User
from app.schemas import UserCreate
from app.services.audit import record_audit
from app.services.seed import ensure_roles, seed_development

cli = typer.Typer(name="kandor", help="KANDOR local administrative CLI", no_args_is_help=True)


def run(coro):
    return asyncio.run(coro)


@cli.command()
def status() -> None:
    """Show database-level KANDOR status."""

    async def command() -> None:
        async with SessionLocal() as db:
            users = (await db.execute(select(func.count(User.id)))).scalar_one()
            agents = (await db.execute(select(func.count(Agent.id)).where(Agent.removed_at.is_(None)))).scalar_one()
            tasks = (await db.execute(select(func.count(Task.id)))).scalar_one()
            typer.echo(json.dumps({"status": "ok", "users": users, "agents": agents, "tasks": tasks}, indent=2))

    run(command())


@cli.command("create-user")
def create_user(
    email: str = typer.Option(..., prompt=True),
    display_name: str = typer.Option(..., prompt=True),
    role: RoleName = typer.Option(RoleName.VIEWER, case_sensitive=False),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
) -> None:
    """Create a user from the trusted local administrative shell."""
    payload = UserCreate(email=email, display_name=display_name, role=role, password=password)

    async def command() -> None:
        async with SessionLocal() as db:
            await ensure_roles(db)
            if (await db.execute(select(User.id).where(User.email == str(payload.email)))).scalar_one_or_none():
                raise typer.BadParameter("a user with this email already exists")
            user = User(
                email=str(payload.email),
                display_name=payload.display_name,
                role=payload.role,
                password_hash=hash_password(payload.password.get_secret_value()),
            )
            db.add(user)
            await db.flush()
            await record_audit(
                db, "USER_CREATED", user_id=user.id, metadata={"source": "local_cli", "role": role.value}
            )
            await db.commit()
            typer.echo(f"Created {user.email} ({user.role.value}) with id {user.id}")

    run(command())


@cli.command("create-enrollment-token")
def create_enrollment_token(
    administrator_email: str = typer.Option(..., "--administrator", help="Existing administrator email"),
    expires_in_seconds: int = typer.Option(900, min=60, max=86_400),
    description: str | None = typer.Option(None, max=255),
) -> None:
    """Create a one-time agent enrollment token. The secret is displayed once."""

    async def command() -> None:
        async with SessionLocal() as db:
            actor = (
                await db.execute(
                    select(User).where(User.email == administrator_email.lower(), User.is_active.is_(True))
                )
            ).scalar_one_or_none()
            if not actor or actor.role != RoleName.ADMINISTRATOR:
                raise typer.BadParameter("an active administrator is required")
            token_id = str(uuid.uuid4())
            raw = f"ket_{token_id}.{secrets.token_urlsafe(32)}"
            row = EnrollmentToken(
                id=token_id,
                token_hash=sha256(raw),
                prefix=raw[:16],
                description=description,
                created_by_id=actor.id,
                expires_at=utcnow() + timedelta(seconds=expires_in_seconds),
            )
            db.add(row)
            await db.flush()
            await record_audit(
                db,
                "ENROLLMENT_TOKEN_CREATED",
                user_id=actor.id,
                metadata={"source": "local_cli", "enrollment_token_id": row.id},
            )
            await db.commit()
            typer.echo(raw)

    run(command())


@cli.command("list-agents")
def list_agents() -> None:
    """List enrolled, non-removed agents."""

    async def command() -> None:
        async with SessionLocal() as db:
            rows = (
                (await db.execute(select(Agent).where(Agent.removed_at.is_(None)).order_by(Agent.name))).scalars().all()
            )
            for row in rows:
                typer.echo(f"{row.id}\t{row.status.value}\t{row.name}\t{row.hostname}")

    run(command())


@cli.command("list-tasks")
def list_tasks(limit: int = typer.Option(50, min=1, max=500)) -> None:
    """List recent tasks."""

    async def command() -> None:
        async with SessionLocal() as db:
            rows = (await db.execute(select(Task).order_by(Task.created_at.desc()).limit(limit))).scalars().all()
            for row in rows:
                typer.echo(f"{row.id}\t{row.status.value}\t{row.task_type.value}\t{row.agent_id}")

    run(command())


@cli.command()
def seed() -> None:
    """Run the explicit, opt-in development seed configuration."""

    async def command() -> None:
        if get_settings().environment == "production":
            raise typer.BadParameter("development seed cannot run in production")
        await create_schema()
        async with SessionLocal() as db:
            created = await seed_development(db)
            typer.echo(json.dumps({"created": created}, indent=2))

    run(command())


if __name__ == "__main__":
    cli()
