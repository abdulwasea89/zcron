"""Audit logging helper + query service (Section 16.1).

Every state-changing service calls ``record_audit`` to persist an immutable
trail entry. ``list_audit_logs`` and ``distinct_actions`` serve the audit log
viewer page.
"""

from __future__ import annotations

import json
import hashlib
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.audit_chain_head import AuditChainHead
from app.models.organization import Organization
from app.models.user import User


def audit_entry_digest(entry: AuditLog) -> str:
    content = {
        "id": entry.id,
        "organization_id": entry.organization_id,
        "actor_user_id": entry.actor_user_id,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "old_values_json": entry.old_values_json,
        "new_values_json": entry.new_values_json,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "metadata_json": entry.metadata_json,
        "created_at": entry.created_at.isoformat(),
        "previous_hash": entry.previous_hash,
    }
    if entry.chain_key is not None:
        content["chain_key"] = entry.chain_key
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    organization_id: str | None = None,
    actor_user_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    old_values: Any = None,
    new_values: Any = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
    chain_key: str | None = None,
) -> AuditLog:
    previous_hash = None
    organization = None
    chain_head = None
    if organization_id and hasattr(session, "execute"):
        if chain_key:
            values = {"organization_id": organization_id, "chain_key": chain_key}
            dialect = session.get_bind().dialect.name
            insert = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
            if insert:
                await session.execute(insert(AuditChainHead).values(**values).on_conflict_do_nothing(
                    index_elements=["organization_id", "chain_key"]
                ))
            chain_head = (await session.execute(
                select(AuditChainHead).where(
                    AuditChainHead.organization_id == organization_id,
                    AuditChainHead.chain_key == chain_key,
                ).with_for_update()
            )).scalar_one()
            previous_hash = chain_head.head_hash
        else:
            organization = (await session.execute(
                select(Organization).where(Organization.id == organization_id).with_for_update()
            )).scalar_one_or_none()
            previous_hash = organization.audit_chain_head if organization else None
    entry = AuditLog(
        action=action,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values_json=json.dumps(old_values, default=str) if old_values is not None else None,
        new_values_json=json.dumps(new_values, default=str) if new_values is not None else None,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=json.dumps(metadata, default=str) if metadata else None,
        previous_hash=previous_hash,
        chain_key=chain_key,
    )
    if organization or chain_head:
        # shortcut: the head shares the database, add an external anchor to detect privileged database rewrites.
        entry.entry_hash = audit_entry_digest(entry)
        if chain_head:
            chain_head.head_hash = entry.entry_hash
            session.add(chain_head)
        else:
            organization.audit_chain_head = entry.entry_hash
            session.add(organization)
    session.add(entry)
    return entry


def verify_audit_chain(entries: list[AuditLog], chain_head: str | None) -> dict[str, int | bool]:
    chained = [entry for entry in entries if entry.entry_hash]
    legacy = len(entries) - len(chained)
    by_previous: dict[str | None, AuditLog] = {}
    for entry in chained:
        if entry.previous_hash in by_previous:
            return {"valid": False, "checked": len(chained), "legacy": legacy}
        by_previous[entry.previous_hash] = entry

    previous = None
    checked = 0
    while previous in by_previous:
        entry = by_previous[previous]
        if entry.entry_hash != audit_entry_digest(entry):
            return {"valid": False, "checked": checked + 1, "legacy": legacy}
        previous = entry.entry_hash
        checked += 1
    valid = checked == len(chained) and previous == chain_head
    return {"valid": valid, "checked": checked, "legacy": legacy}


async def list_audit_logs(
    session: AsyncSession,
    *,
    organization_id: str,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_user_id: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    base = (
        select(AuditLog, User.email, User.full_name)
        .where(AuditLog.organization_id == organization_id)
        .outerjoin(User, AuditLog.actor_user_id == User.id)
    )

    if action:
        base = base.where(AuditLog.action == action)
    if entity_type:
        base = base.where(AuditLog.entity_type == entity_type)
    if entity_id:
        base = base.where(AuditLog.entity_id == entity_id)
    if actor_user_id:
        base = base.where(AuditLog.actor_user_id == actor_user_id)
    if search:
        base = base.where(
            AuditLog.action.ilike(f"%{search}%")
            | AuditLog.entity_type.ilike(f"%{search}%")
            | AuditLog.entity_id.ilike(f"%{search}%")
        )
    if date_from:
        base = base.where(AuditLog.created_at >= date_from)
    if date_to:
        base = base.where(AuditLog.created_at <= date_to)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (
        await session.execute(
            base.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()

    items: list[dict] = []
    for audit_log, actor_email, actor_name in rows:
        items.append({
            "id": audit_log.id,
            "action": audit_log.action,
            "actor_user_id": audit_log.actor_user_id,
            "actor_email": actor_email,
            "actor_name": actor_name,
            "entity_type": audit_log.entity_type,
            "entity_id": audit_log.entity_id,
            "old_values": json.loads(audit_log.old_values_json) if audit_log.old_values_json else None,
            "new_values": json.loads(audit_log.new_values_json) if audit_log.new_values_json else None,
            "metadata": json.loads(audit_log.metadata_json) if audit_log.metadata_json else None,
            "ip_address": audit_log.ip_address,
            "created_at": audit_log.created_at,
        })

    return items, total


async def distinct_actions(session: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AuditLog.action)
            .where(AuditLog.organization_id == organization_id)
            .distinct()
            .order_by(AuditLog.action)
        )
    ).scalars().all()

    groups: dict[str, set[str]] = {}
    for action in rows:
        domain = action.split(".")[0] if "." in action else "other"
        groups.setdefault(domain, set()).add(action)

    return [
        {"domain": domain, "actions": sorted(actions)}
        for domain, actions in sorted(groups.items())
    ]
