import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from .security import decode_token
from ..db.session import get_session
from ..models.enums import AgentRole
from ..models.identity import Agent, User

bearer_scheme = HTTPBearer()

DBSession = Annotated[AsyncSession, Depends(get_session)]


# ── Token extraction ──────────────────────────────────────────────────────────

def _extract_payload(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> dict:
    try:
        return decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Current customer ──────────────────────────────────────────────────────────

async def get_current_user(
    db: DBSession,
    payload: Annotated[dict, Depends(_extract_payload)],
) -> User:
    if payload.get("actor_type") != "customer":
        raise HTTPException(status_code=403, detail="Customer token required")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Current agent ─────────────────────────────────────────────────────────────

async def get_current_agent(
    db: DBSession,
    payload: Annotated[dict, Depends(_extract_payload)],
) -> Agent:
    if payload.get("actor_type") != "agent":
        raise HTTPException(status_code=403, detail="Agent token required")
    agent_id = payload.get("sub")
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent or not agent.is_active:
        raise HTTPException(status_code=404, detail="Agent not found or inactive")
    return agent


CurrentAgent = Annotated[Agent, Depends(get_current_agent)]


# ── Role guards ───────────────────────────────────────────────────────────────

def require_roles(*roles: AgentRole):
    async def _guard(agent: CurrentAgent) -> Agent:
        if agent.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role {agent.role} not permitted. Required: {[r.value for r in roles]}",
            )
        return agent
    return _guard


def require_checker(agent: CurrentAgent) -> Agent:
    if agent.role not in (AgentRole.checker, AgentRole.compliance_officer, AgentRole.system_admin):
        raise HTTPException(status_code=403, detail="Checker role required")
    return agent


CheckerAgent = Annotated[Agent, Depends(require_checker)]
