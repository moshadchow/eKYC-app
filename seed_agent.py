"""
Seed script — creates a test agent with an authorized device.
Run once from the project root after `alembic upgrade head`.

Usage:
    python seed_agent.py

    # Custom credentials:
    python seed_agent.py --employee-id EMP-99999 --password MyPass123 --role maker
"""

import argparse
import asyncio
import sys
import uuid

# ── Allow running from project root ──────────────────────────────────────────
sys.path.insert(0, ".")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import select

from app.core.config import settings
from app.core.security import hash_password
from app.models.identity import Agent, AgentDevice

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_EMPLOYEE_ID      = "EMP-00001"
DEFAULT_PASSWORD         = "Agent@1234"
DEFAULT_ROLE             = "maker"           # maker | checker | compliance_officer | system_admin | system_auditor
DEFAULT_FULL_NAME        = "Test Agent"
DEFAULT_BRANCH_CODE      = "DHK-001"
DEFAULT_DEVICE_FINGERPRINT = "web-browser-agent"   # must match what the login page sends


async def seed(employee_id: str, password: str, role: str, full_name: str) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:

        # ── 1. Check if agent already exists ──────────────────────────────────
        existing = await db.execute(
            select(Agent).where(Agent.employee_id == employee_id)
        )
        agent = existing.scalar_one_or_none()

        if agent:
            # Update password and role if agent already exists
            agent.password_hash = hash_password(password)
            agent.role           = role
            agent.full_name      = full_name
            agent.is_active      = True
            print(f"  ✏️  Updated existing agent: {employee_id}")
        else:
            agent = Agent(
                employee_id   = employee_id,
                full_name     = full_name,
                password_hash = hash_password(password),
                role          = role,
                branch_code   = DEFAULT_BRANCH_CODE,
                is_active     = True,
            )
            db.add(agent)
            await db.flush()
            print(f"  ✅ Created agent: {employee_id}")

        # ── 2. Authorize the default device fingerprint ────────────────────────
        dev_existing = await db.execute(
            select(AgentDevice).where(
                AgentDevice.agent_id          == agent.id,
                AgentDevice.device_fingerprint == DEFAULT_DEVICE_FINGERPRINT,
            )
        )
        device = dev_existing.scalar_one_or_none()

        if device:
            device.is_authorized = True
            from app.models.base import utcnow
            device.authorized_at = utcnow()
            print(f"  ✏️  Re-authorized device: {DEFAULT_DEVICE_FINGERPRINT}")
        else:
            from app.models.base import utcnow
            device = AgentDevice(
                agent_id           = agent.id,
                device_fingerprint = DEFAULT_DEVICE_FINGERPRINT,
                device_name        = "Web Browser (dev)",
                is_authorized      = True,
                authorized_at      = utcnow(),
            )
            db.add(device)
            print(f"  ✅ Authorized device: {DEFAULT_DEVICE_FINGERPRINT}")

        await db.commit()

    await engine.dispose()

    # ── Print summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 52)
    print("  🔐  AGENT SEED COMPLETE")
    print("=" * 52)
    print(f"  Employee ID : {employee_id}")
    print(f"  Password    : {password}")
    print(f"  Role        : {role}")
    print(f"  Device FP   : {DEFAULT_DEVICE_FINGERPRINT}")
    print("=" * 52)
    print()
    print("  Login steps:")
    print("  1. Go to  http://localhost:5173/agent/login")
    print(f"  2. Employee ID → {employee_id}")
    print(f"  3. Password    → {password}")
    print("  4. Click Continue — OTP will print in this terminal")
    print("  5. Enter the OTP to complete 2FA")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a test agent for eKYC")
    parser.add_argument("--employee-id", default=DEFAULT_EMPLOYEE_ID)
    parser.add_argument("--password",    default=DEFAULT_PASSWORD)
    parser.add_argument("--role",        default=DEFAULT_ROLE,
                        choices=["maker", "checker", "compliance_officer", "system_admin", "system_auditor"])
    parser.add_argument("--full-name",   default=DEFAULT_FULL_NAME)
    args = parser.parse_args()

    asyncio.run(seed(args.employee_id, args.password, args.role, args.full_name))


if __name__ == "__main__":
    main()
