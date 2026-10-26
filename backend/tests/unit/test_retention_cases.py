import pytest
from fastapi import HTTPException

from app.core.constants import Role
from app.models.membership import OrganizationMember
from app.models.staff import Task
from app.schemas.retention import RetentionCaseUpdate
from app.services import retention_cases_service as cases


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, member, task=None, assignee=None):
        self.member, self.task, self.assignee = member, task, assignee
        self.added = []

    async def get(self, model, key, **kwargs):
        if model is OrganizationMember:
            if key == self.member.id:
                return self.member
            return self.assignee if self.assignee and key == self.assignee.id else None
        return None

    async def execute(self, _query):
        return Result(self.task)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass


@pytest.fixture
def services(monkeypatch):
    audit = []
    notices = []

    async def record_audit(_session, **values):
        audit.append(values)

    async def create_notification(_session, **values):
        notices.append(values)

    async def task_changed(*_args, **_kwargs):
        pass

    monkeypatch.setattr(cases, "record_audit", record_audit)
    monkeypatch.setattr(cases, "create_notification", create_notification)
    monkeypatch.setattr(cases.events, "task_changed", task_changed)
    return audit, notices


@pytest.mark.asyncio
async def test_manual_case_is_created_and_reused_by_scheduled_ladder(services):
    member = OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER,
                                display_name="A Member")
    assignee = OrganizationMember(id="staff", organization_id="gym", user_id="staff-user", role=Role.TRAINER)
    session = Session(member, assignee=assignee)
    task = await cases.save_case(session, org_id="gym", member_id="member",
                                 data=RetentionCaseUpdate(next_action="Call tomorrow", assignee_member_id="staff"),
                                 actor_id="owner")
    assert task.category == "retention" and task.related_member_id == "member"
    assert task.description == "Call tomorrow" and task.assignee_member_id == "staff"
    assert services[1][0]["recipient_user_id"] == "staff-user"

    session.task = task
    result = await cases.save_case(session, org_id="gym", member_id="member",
                                   data=RetentionCaseUpdate(next_action="Automated ladder action"), actor_id=None)
    assert result is task and task.description == "Call tomorrow"


@pytest.mark.asyncio
async def test_case_rejects_member_and_cross_gym_assignees():
    member = OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER)
    other_gym = OrganizationMember(id="staff", organization_id="elsewhere", user_id="staff-user", role=Role.TRAINER)
    session = Session(member, assignee=other_gym)
    with pytest.raises(HTTPException) as error:
        await cases.save_case(session, org_id="gym", member_id="member",
                              data=RetentionCaseUpdate(next_action="Call", assignee_member_id="staff"), actor_id="owner")
    assert error.value.status_code == 422
    assert session.added == []


@pytest.mark.asyncio
async def test_payment_closes_case_with_audited_outcome(services):
    task = Task(organization_id="gym", title="Save member", category="retention", related_member_id="member")
    session = Session(OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER), task)
    await cases.close_on_payment(session, org_id="gym", member_id="member")
    assert task.done is True and task.case_outcome == "payment_received"
    assert services[0][0]["action"] == "retention.case_closed"


@pytest.mark.asyncio
async def test_staff_must_load_existing_case_before_replacing_its_plan(services):
    member = OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER)
    task = Task(id="existing-case", organization_id="gym", title="Retention", category="retention",
                related_member_id="member", description="Staff already agreed on a call", assignee_member_id="staff")
    session = Session(member, task)
    with pytest.raises(HTTPException) as error:
        await cases.save_case(session, org_id="gym", member_id="member",
                              data=RetentionCaseUpdate(next_action="Unloaded default action"), actor_id="owner")
    assert error.value.status_code == 409
    assert task.description == "Staff already agreed on a call" and task.assignee_member_id == "staff"
    await cases.save_case(session, org_id="gym", member_id="member",
                          data=RetentionCaseUpdate(case_id=task.id, next_action="Agreed on a return visit"), actor_id="owner")
    assert task.description == "Agreed on a return visit"
    session.task = None
    with pytest.raises(HTTPException) as error:
        await cases.save_case(session, org_id="gym", member_id="member",
                              data=RetentionCaseUpdate(case_id=task.id, next_action="Stale edit"), actor_id="owner")
    assert error.value.status_code == 409


def test_case_action_is_trimmed_and_blank_actions_are_rejected():
    assert RetentionCaseUpdate(next_action="  Call member  ").next_action == "Call member"
    with pytest.raises(ValueError):
        RetentionCaseUpdate(next_action="  ")


def test_open_retention_case_has_database_uniqueness_guard():
    index = next(index for index in Task.__table__.indexes if index.name == "uq_tasks_open_retention")
    assert index.unique
    assert "category = 'retention'" in str(index.dialect_options["sqlite"]["where"])
