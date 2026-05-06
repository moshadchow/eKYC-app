import json
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ActorType, AuditAction
from ..models.workflow import AuditLog
from ..models.base import utcnow


async def record_event(
    db: AsyncSession,
    *,
    actor_id: Optional[str],
    actor_type: ActorType,
    action: AuditAction,
    entity_type: str,
    entity_id: Optional[str] = None,
    old_value: Optional[Any] = None,
    new_value: Optional[Any] = None,
    ip_address: Optional[str] = None,
    device_fingerprint: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value_json=json.dumps(old_value, default=str) if old_value else None,
        new_value_json=json.dumps(new_value, default=str) if new_value else None,
        ip_address=ip_address,
        device_fingerprint=device_fingerprint,
        user_agent=user_agent,
        created_at=utcnow(),
    )
    db.add(log)
    return log
