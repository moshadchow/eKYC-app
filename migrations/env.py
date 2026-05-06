"""
Alembic async environment for SQLModel + asyncpg.

Root cause of MissingGreenlet:
  asyncpg is an async-only driver. Alembic's env.py must use
  async_engine_from_config + run_sync pattern — never a sync engine
  with an asyncpg:// URL. This file implements that correctly.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

# ── Import ALL models so SQLModel.metadata knows about every table ────────────
from app.models.identity import (  # noqa: F401
    Agent, AgentDevice, AgentSession, OTPLog, Session, User,
)
from app.models.onboarding import (  # noqa: F401
    BiometricVerification, CustomerProfile, DigitalSignature,
    KYCApplication, KYCDocument, Nominee, OCRExtraction,
)
from app.models.compliance import (  # noqa: F401
    BeneficialOwner, EDDDocument, EDDRequest,
    PEPIPCheck, RiskScore, ScreeningResult,
)
from app.models.workflow import (  # noqa: F401
    Account, ApprovalDecision, ApprovalQueue, AuditLog,
    KYCRefreshEvent, KYCRefreshSchedule, Notification, PreCheckLog,
)

from app.core.config import settings

# ── URL setup ─────────────────────────────────────────────────────────────────
config = context.config

# Keep the original asyncpg URL for the live async engine connection
async_url: str = settings.DATABASE_URL

# Build a sync-dialect URL for Alembic offline SQL generation only
sync_url: str = (
    async_url
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("asyncpg://", "postgresql://")
)

# Alembic reads this for offline mode and autogenerate dialect detection
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


# ── Offline mode ──────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Inject the asyncpg URL back for the actual engine
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = async_url

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Dispatch ──────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
