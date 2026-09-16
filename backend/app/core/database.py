from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_options(url: str) -> dict:
    options: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return options


settings = get_settings()
engine: AsyncEngine = create_async_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    module = dbapi_connection.__class__.__module__
    if "sqlite" in module:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_schema() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    await engine.dispose()
