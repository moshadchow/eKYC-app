"""
Seed script — creates all test accounts needed for end-to-end onboarding testing.
Run once from the project root after `alembic upgrade head` (or after `python -m app.db.session`).

Usage:
    python seed_all.py           # upsert all accounts (safe to run multiple times)
    python seed_all.py --reset   # delete existing seed accounts then re-insert

Accounts created
────────────────
  AGENTS (login at http://localhost:5173/agent/login)
    EMP-MAKER-01    / Maker@1234    / role: maker
    EMP-CHECKER-01  / Checker@1234  / role: checker
    EMP-COMPLY-01   / Comply@1234   / role: compliance_officer
    EMP-ADMIN-01    / Admin@1234    / role: system_admin
    EMP-AUDIT-01    / Audit@1234    / role: system_auditor

  CUSTOMERS (login at http://localhost:5173  — OTP printed in terminal)
    01712000001  — Self Check-in onboarding test
    01712000002  — Assisted onboarding test (agent creates application on their behalf)
"""

import asyncio
import sys

sys.path.insert(0, ".")

import argparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import select

from app.core.config import settings
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.identity import Agent, AgentDevice, User

DEVICE_FINGERPRINT = "web-browser-agent"

AGENTS = [
    {"employee_id": "EMP-MAKER-01",   "password": "Maker@1234",   "role": "maker",               "full_name": "Test Maker"},
    {"employee_id": "EMP-CHECKER-01", "password": "Checker@1234", "role": "checker",             "full_name": "Test Checker"},
    {"employee_id": "EMP-COMPLY-01",  "password": "Comply@1234",  "role": "compliance_officer",  "full_name": "Test Compliance Officer"},
    {"employee_id": "EMP-ADMIN-01",   "password": "Admin@1234",   "role": "system_admin",        "full_name": "Test System Admin"},
    {"employee_id": "EMP-AUDIT-01",   "password": "Audit@1234",   "role": "system_auditor",      "full_name": "Test System Auditor"},
]

CUSTOMERS = [
    {"mobile_number": "01712000001"},
    {"mobile_number": "01712000002"},
]


async def _upsert_agent(db: AsyncSession, spec: dict) -> str:
    result = await db.execute(select(Agent).where(Agent.employee_id == spec["employee_id"]))
    agent = result.scalar_one_or_none()

    if agent:
        agent.password_hash = hash_password(spec["password"])
        agent.role          = spec["role"]
        agent.full_name     = spec["full_name"]
        agent.is_active     = True
        action = "updated"
    else:
        agent = Agent(
            employee_id   = spec["employee_id"],
            full_name     = spec["full_name"],
            password_hash = hash_password(spec["password"]),
            role          = spec["role"],
            branch_code   = "DHK-001",
            is_active     = True,
        )
        db.add(agent)
        await db.flush()
        action = "created"

    # Authorize device
    dev_result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.agent_id          == agent.id,
            AgentDevice.device_fingerprint == DEVICE_FINGERPRINT,
        )
    )
    device = dev_result.scalar_one_or_none()
    if device:
        device.is_authorized = True
        device.authorized_at = utcnow()
    else:
        db.add(AgentDevice(
            agent_id           = agent.id,
            device_fingerprint = DEVICE_FINGERPRINT,
            device_name        = "Web Browser (dev)",
            is_authorized      = True,
            authorized_at      = utcnow(),
        ))

    return action


async def _upsert_customer(db: AsyncSession, spec: dict) -> str:
    result = await db.execute(select(User).where(User.mobile_number == spec["mobile_number"]))
    user = result.scalar_one_or_none()
    if user:
        user.status = "active"
        return "updated"
    db.add(User(mobile_number=spec["mobile_number"], status="active"))
    return "created"


async def _delete_seed_accounts(db: AsyncSession) -> None:
    for spec in AGENTS:
        result = await db.execute(select(Agent).where(Agent.employee_id == spec["employee_id"]))
        agent = result.scalar_one_or_none()
        if agent:
            dev_result = await db.execute(select(AgentDevice).where(AgentDevice.agent_id == agent.id))
            for dev in dev_result.scalars().all():
                await db.delete(dev)
            await db.delete(agent)

    for spec in CUSTOMERS:
        result = await db.execute(select(User).where(User.mobile_number == spec["mobile_number"]))
        user = result.scalar_one_or_none()
        if user:
            await db.delete(user)


async def seed(reset: bool = False) -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        if reset:
            print("  Deleting existing seed accounts...")
            await _delete_seed_accounts(db)
            await db.flush()

        agent_results = []
        for spec in AGENTS:
            action = await _upsert_agent(db, spec)
            agent_results.append((spec["employee_id"], spec["password"], spec["role"], action))
            print(f"  {'✅' if action == 'created' else '✏️ '} Agent {action}: {spec['employee_id']} ({spec['role']})")

        customer_results = []
        for spec in CUSTOMERS:
            action = await _upsert_customer(db, spec)
            customer_results.append((spec["mobile_number"], action))
            print(f"  {'✅' if action == 'created' else '✏️ '} Customer {action}: {spec['mobile_number']}")

        await db.commit()

    await engine.dispose()

    # ── Summary ───────────────────────────────────────────────────────────────
    w = 60
    print()
    print("=" * w)
    print("  SEED COMPLETE — TEST CREDENTIALS")
    print("=" * w)

    print()
    print("  AGENTS  →  http://localhost:5173/agent/login")
    print(f"  {'Employee ID':<18} {'Password':<16} {'Role'}")
    print(f"  {'-'*17} {'-'*15} {'-'*22}")
    for emp_id, pwd, role, _ in agent_results:
        print(f"  {emp_id:<18} {pwd:<16} {role}")

    print()
    print("  CUSTOMERS  →  http://localhost:5173")
    print(f"  {'Mobile':<16} {'Auth'}")
    print(f"  {'-'*15} {'-'*30}")
    for mobile, _ in customer_results:
        print(f"  {mobile:<16} OTP printed in server terminal")

    print()
    print("  Agent login steps:")
    print("    1. Go to http://localhost:5173/agent/login")
    print("    2. Enter Employee ID + Password")
    print("    3. OTP is printed in the uvicorn terminal — enter it to complete 2FA")
    print()
    print("  Customer login steps:")
    print("    1. Go to http://localhost:5173")
    print("    2. Enter mobile number")
    print("    3. OTP is printed in the uvicorn terminal — enter it to log in")
    print()
    print("  End-to-end test flows:")
    print("    Self Check-in : log in as 01712000001 → New Application")
    print("    Assisted      : log in as EMP-MAKER-01 → New Application → mobile 01712000002")
    print("    Approval      : maker (EMP-MAKER-01) decides → checker (EMP-CHECKER-01) counter-checks")
    print("=" * w)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed all test accounts for eKYC end-to-end testing")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing seed accounts before re-inserting (clean slate)",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
