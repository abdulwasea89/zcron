"""One open retention case per member, backed by the regular task queue."""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import NotificationKind, Role
from app.core.security import now_utc
from app.models.membership import OrganizationMember
from app.models.staff import Task
from app.models.user import User
from app.realtime import events
from app.schemas.retention import RetentionCaseUpdate
from app.services.audit_service import record_audit
from app.services.notifications_service import create_notification


async def save_case(session: AsyncSession, *, org_id: str, member_id: str,
                    data: RetentionCaseUpdate, actor_id: str | None) -> Task:
    member = await session.get(OrganizationMember, member_id, with_for_update=True, populate_existing=True)
    if member is None or member.organization_id != org_id or member.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found.")
    assignee = await session.get(OrganizationMember, data.assignee_member_id) if data.assignee_member_id else None
    if data.assignee_member_id and (assignee is None or assignee.organization_id != org_id
                                   or assignee.role == Role.MEMBER or assignee.banned):
        raise HTTPException(status_code=422, detail="Choose an active staff member in this gym.")
    task = (await session.execute(select(Task).where(
        Task.organization_id == org_id, Task.related_member_id == member.id,
        Task.category == "retention", Task.done.is_(False),
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    # Scheduled ladder steps must not overwrite a staff member's existing plan.
    if task is not None and actor_id is None:
        return task
    if (task is not None and task.id != data.case_id) or (task is None and data.case_id is not None):
        raise HTTPException(status_code=409, detail="This member's open case changed. Reload it before saving.")
    if task is None and data.outcome:
        raise HTTPException(status_code=409, detail="Open a case before recording its outcome.")
    created = task is None
    old_assignee = task.assignee_member_id if task else None
    if task is None:
        user = await session.get(User, member.user_id)
        name = member.display_name or (user.full_name or user.email if user else "member")
        task = Task(organization_id=org_id, category="retention", related_member_id=member.id,
                    title=f"Retention: {name}", created_by=actor_id)
    task.description = data.next_action
    task.deadline = data.due_at or now_utc() + timedelta(days=1)
    task.assignee_member_id = data.assignee_member_id
    task.case_outcome = data.outcome
    task.done = data.outcome is not None
    task.updated_at = now_utc()
    session.add(task)
    await session.flush()
    await record_audit(session, action="retention.case_closed" if task.done else "retention.case_created" if created else "retention.case_updated",
                       organization_id=org_id, actor_user_id=actor_id, entity_type="task", entity_id=task.id,
                       metadata={"member_id": member.id, "outcome": task.case_outcome, "assignee_member_id": task.assignee_member_id})
    if assignee and not task.done and (created or old_assignee != assignee.id):
        await create_notification(session, org_id=org_id, recipient_user_id=assignee.user_id,
                                  category=NotificationKind.TASK, title="Retention follow-up assigned",
                                  body=task.description, data={"task_id": task.id, "member_id": member.id})
    await events.task_changed(org_id, task_id=task.id, action="completed" if task.done else "created" if created else "updated")
    return task


async def list_cases(session: AsyncSession, *, org_id: str, include_closed: bool = False,
                     member_id: str | None = None) -> list[dict]:
    statement = select(Task, OrganizationMember, User).join(
        OrganizationMember, OrganizationMember.id == Task.related_member_id,
    ).join(User, User.id == OrganizationMember.user_id).where(
        Task.organization_id == org_id, OrganizationMember.organization_id == org_id,
        Task.category == "retention",
    )
    if not include_closed:
        statement = statement.where(Task.done.is_(False))
    if member_id:
        statement = statement.where(Task.related_member_id == member_id)
    rows = (await session.execute(statement.order_by(Task.updated_at.desc()).limit(500))).all()
    return [{"id": task.id, "member_id": member.id, "member_name": member.display_name or user.full_name or user.email,
             "next_action": task.description or task.title, "assignee_member_id": task.assignee_member_id,
             "due_at": task.deadline, "done": task.done, "outcome": task.case_outcome, "updated_at": task.updated_at}
            for task, member, user in rows]


async def close_on_payment(session: AsyncSession, *, org_id: str, member_id: str) -> None:
    task = (await session.execute(select(Task).where(
        Task.organization_id == org_id, Task.related_member_id == member_id,
        Task.category == "retention", Task.done.is_(False),
    ).with_for_update())).scalar_one_or_none()
    if task:
        task.done = True
        task.case_outcome = "payment_received"
        session.add(task)
        await record_audit(session, action="retention.case_closed", organization_id=org_id,
                           entity_type="task", entity_id=task.id, metadata={"member_id": member_id, "outcome": "payment_received"})
        await events.task_changed(org_id, task_id=task.id, action="completed")
