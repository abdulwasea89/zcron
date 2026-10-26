from datetime import timedelta
import importlib
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from app.core.constants import MemberStatus, Role, SubscriptionStatus
from app.core.security import now_utc
from app.models.membership import OrganizationMember
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.services import family_service as family
from app.api.v1.routes import members as member_routes
from app.core.tenancy import TenantContext
from app.schemas.members import FamilyLinkRequest


class Facade:
    def __init__(self, db):
        self.db = db

    async def get(self, *args, **kwargs):
        return self.db.get(*args, **kwargs)

    async def execute(self, statement):
        return self.db.execute(statement)

    def add(self, row):
        self.db.add(row)

    def get_bind(self):
        return self.db.get_bind()

    async def flush(self):
        self.db.flush()


@pytest.fixture
def database(monkeypatch):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(family.events, 'membership_changed', AsyncMock())
    with Session(engine) as db:
        for key in ['holder', 'dependent', 'covered', 'foreign']:
            db.add(OrganizationMember(id=key, organization_id='other' if key == 'foreign' else 'gym',
                user_id=key, role=Role.MEMBER, member_status=MemberStatus.ACTIVE))
        db.add(MembershipPlan(id='family-plan', organization_id='gym', name='Family', audience='family', family_capacity=2))
        db.add(MembershipPlan(id='own-plan', organization_id='gym', name='Own plan'))
        for member, plan in [('holder', 'family-plan'), ('dependent', 'own-plan')]:
            db.add(Subscription(id=member, organization_id='gym', member_id=member, plan_id=plan,
                status=SubscriptionStatus.ACTIVE, current_period_end=now_utc() + timedelta(days=30), classes_remaining=5))
        db.flush()
        yield db, Facade(db)
    engine.dispose()


async def link(session, dependent='dependent', mode='independent', attach=True):
    return await family.set_family_member(session, org_id='gym', owner_id='holder',
        dependent_id=dependent, attach=attach, actor_id='owner', billing_mode=mode)


async def test_independent_members_keep_own_subscription_status_and_credits(database):
    db, session = database
    await link(session)
    db.flush()
    dependent = db.get(OrganizationMember, 'dependent')
    assert dependent.family_owner_member_id == 'holder' and dependent.family_billing_mode == 'independent'
    sub = await family.covered_subscription(session, 'gym', dependent)
    assert sub.id == 'dependent' and sub.classes_remaining == 5
    await family.sync_family_status(session, 'gym', 'holder', MemberStatus.FROZEN)
    assert dependent.member_status == MemberStatus.ACTIVE
    await link(session, attach=False)
    assert dependent.member_status == MemberStatus.ACTIVE
    assert dependent.family_owner_member_id is None
    assert db.get(Subscription, 'dependent').status == SubscriptionStatus.ACTIVE


async def test_independent_members_do_not_consume_shared_places_or_require_family_plan(database):
    db, session = database
    await link(session)
    await link(session, dependent='covered', mode='shared_plan')
    db.flush()
    covered = db.get(OrganizationMember, 'covered')
    assert (await family.covered_subscription(session, 'gym', covered)).id == 'holder'
    await family.sync_family_status(session, 'gym', 'holder', MemberStatus.FROZEN)
    assert covered.member_status == MemberStatus.FROZEN
    assert db.get(OrganizationMember, 'dependent').member_status == MemberStatus.ACTIVE
    await link(session, dependent='covered', mode='shared_plan', attach=False)
    assert covered.member_status == MemberStatus.EXPIRED
    await link(session, attach=False)
    holder = db.get(Subscription, 'holder')
    holder.plan_id = 'own-plan'
    db.flush()
    await link(session)
    assert db.get(OrganizationMember, 'dependent').family_billing_mode == 'independent'


async def test_cross_gym_staff_nested_links_and_coverage_replacement_are_rejected(database):
    db, session = database
    with pytest.raises(HTTPException) as error:
        await link(session, dependent='foreign')
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await link(session, mode='shared_plan')
    assert error.value.status_code == 409
    assert db.get(OrganizationMember, 'dependent').family_owner_member_id is None
    await link(session)
    with pytest.raises(HTTPException) as error:
        await link(session, mode='shared_plan')
    assert error.value.status_code == 409
    db.get(OrganizationMember, 'covered').role = Role.TRAINER
    with pytest.raises(HTTPException) as error:
        await link(session, dependent='covered')
    assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        await family.set_family_member(session, org_id='gym', owner_id='dependent', dependent_id='holder',
                                       attach=True, actor_id='owner', billing_mode='independent')


async def test_link_replay_has_no_extra_event_or_billing_side_effect(database):
    db, session = database
    await link(session)
    db.flush()
    await link(session)
    family.events.membership_changed.assert_awaited_once()
    assert len(db.execute(select(Subscription)).all()) == 2


async def test_admin_link_and_unlink_retries_are_idempotent(database):
    db, session = database
    ctx = TenantContext('owner', 'gym', Role.OWNER)
    data = FamilyLinkRequest(member_id='dependent', billing_mode='independent')
    first = await member_routes.add_family_member('holder', data, ctx, session, 'link-key')
    replay = await member_routes.add_family_member('holder', data, ctx, session, 'link-key')
    assert first == replay
    removed = await member_routes.remove_family_member('holder', 'dependent', ctx, session, 'remove-key')
    retried = await member_routes.remove_family_member('holder', 'dependent', ctx, session, 'remove-key')
    assert removed == retried
    assert db.get(OrganizationMember, 'dependent').member_status == MemberStatus.ACTIVE
    with pytest.raises(HTTPException) as error:
        await member_routes.add_family_member('holder', data, TenantContext('desk', 'gym', Role.FRONT_DESK), session, 'desk-key')
    assert error.value.status_code == 403


async def test_new_payment_keeps_independent_household_link(database, monkeypatch):
    from app.services import cash_service, referrals_service, onboarding_service, winback_service
    from app.schemas.cash import CashPaymentLog
    db, session = database
    await link(session)
    for service, name in ((cash_service, 'send_push'), (cash_service, 'create_notification'),
                          (cash_service.events, 'payment_recorded'),
                          (referrals_service, 'qualify_referral_for_member'),
                          (onboarding_service, 'start_journey'), (winback_service, 'mark_recovered')):
        monkeypatch.setattr(service, name, AsyncMock())
    payment, member, _url = await cash_service.log_cash_payment(session, org_id='gym',
        data=CashPaymentLog(member_id='dependent', plan_id='own-plan', amount=0), staff_user_id='owner')
    assert member.family_owner_member_id == 'holder' and member.family_billing_mode == 'independent'
    assert payment.member_id == 'dependent'


def test_migration_keeps_legacy_shared_coverage_and_blocks_unsafe_downgrade():
    module = importlib.import_module('app.db.migrations.versions.l4g5h6i7j8k9_family_independent_billing')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE organization_members (id VARCHAR PRIMARY KEY, family_owner_member_id VARCHAR)')
        connection.exec_driver_sql("INSERT INTO organization_members (id,family_owner_member_id) VALUES ('dependent','holder')")
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            assert connection.exec_driver_sql('SELECT family_billing_mode FROM organization_members').scalar() == 'shared_plan'
            connection.exec_driver_sql("UPDATE organization_members SET family_billing_mode='independent'")
            with pytest.raises(RuntimeError):
                module.downgrade()
    engine.dispose()
