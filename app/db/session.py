"""
Async PostgreSQL engine and session factory.
Uses SQLModel + asyncpg via SQLAlchemy async extension.

MissingGreenlet fix notes:
  1. expire_on_commit=False  — prevents SQLAlchemy from expiring attributes
     after commit() which would trigger lazy IO outside async context.
  2. NullPool for Alembic only — app uses QueuePool (default).
  3. All relationships must use selectin or joined loading, never lazy.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,      # must be postgresql+asyncpg://
    echo=settings.DB_ECHO,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    # future=True is default in SQLAlchemy 2.x
)

# ── Session factory ───────────────────────────────────────────────────────────
# Use async_sessionmaker (SQLAlchemy 2.x) instead of the generic sessionmaker.
# expire_on_commit=False is CRITICAL — without it, accessing any attribute
# after session.commit() triggers a lazy SQL load → MissingGreenlet error.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,     # ← fixes MissingGreenlet on attribute access
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yields one AsyncSession per request.
    Commits on success, rolls back on exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Dev helper (not used in production — use Alembic instead) ─────────────────
async def init_db() -> None:
    """Create all tables directly from metadata. Use only in tests or dev."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
