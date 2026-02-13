import logging
import os
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


logger = logging.getLogger(__name__)

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = (
    create_async_engine(DATABASE_URL, future=True, echo=False)
    if DATABASE_URL
    else None
)

async_session_maker: Optional[async_sessionmaker[AsyncSession]] = (
    async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency that yields an async DB session.

    Note: In later phases, every query must include org_id for tenant isolation.
    """
    if async_session_maker is None:
        raise RuntimeError("DATABASE_URL is not configured")

    async with async_session_maker() as session:
        yield session


async def check_database_health() -> bool:
    """
    Try a trivial `SELECT 1` to confirm DB connectivity.

    Returns False if DATABASE_URL is missing or query fails.
    """
    if async_session_maker is None:
        logger.warning("Database health check: async_session_maker is None")
        return False

    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.exception("Database health check failed", exc_info=exc)
        return False

