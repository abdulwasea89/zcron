"""Lead trial and tour booking business rules."""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.security import now_utc
from app.models.audit_log import AuditLog
from app.models.class_session import ClassSession
from app.models.lead import Lead, LeadBooking
from app.models.organization import Organization
from app.models.user import User
from app.schemas.leads import LeadBookingCreate, LeadCreate
from app.services import leads_service


@pytest_asyncio.fixture
async def booking_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        Organization.__table__,
        User.__table__,
        ClassSession.__table__,
        Lead.__table__,
        LeadBooking.__table__,
        AuditLog.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: SQLModel.metadata.create_all(sync_connection, tables=tables))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def test_booking_schema_requires_valid_trial_or_tour_target():
    with pytest.raises(ValidationError):
        LeadBookingCreate(booking_type="trial")
    with pytest.raises(ValidationError):
        LeadBookingCreate(booking_type="tour")
    with pytest.raises(ValidationError):
        LeadBookingCreate(
            booking_type="tour",
            starts_at=now_utc(),
            ends_at=now_utc() - timedelta(minutes=1),
        )


@pytest.mark.asyncio
async def test_trial_booking_reserves_capacity_and_tracks_visit(booking_db):
    db = booking_db
    org = Organization(name="Trial Gym", org_code="TRIAL-GYM")
    actor = User(email="trial-owner@example.com", hashed_password="unused")
    db.add_all([org, actor])
    await db.flush()
    lead = await leads_service.create_lead(
        db,
        org_id=org.id,
        actor_id=actor.id,
        data=LeadCreate(name="Trial Prospect", preferred_times="Evenings"),
    )
    class_session = ClassSession(
        organization_id=org.id,
        title="Beginner Boxing",
        starts_at=now_utc() + timedelta(days=1),
        ends_at=now_utc() + timedelta(days=1, hours=1),
        capacity=2,
    )
    db.add(class_session)
    await db.flush()

    booking = await leads_service.create_lead_booking(
        db,
        org_id=org.id,
        actor_id=actor.id,
        lead_id=lead.id,
        booking_type="trial",
        class_session_id=class_session.id,
        trainer_member_id=None,
        starts_at=None,
        ends_at=None,
        notes="First boxing class",
    )

    assert booking["class_title"] == "Beginner Boxing"
    assert booking["status"] == "scheduled"
    assert class_session.booked_count == 1
    assert lead.stage == "trial_booked"

    with pytest.raises(HTTPException) as duplicate_error:
        await leads_service.create_lead_booking(
            db,
            org_id=org.id,
            actor_id=actor.id,
            lead_id=lead.id,
            booking_type="trial",
            class_session_id=class_session.id,
            trainer_member_id=None,
            starts_at=None,
            ends_at=None,
            notes=None,
        )
    assert duplicate_error.value.status_code == 409

    updated = await leads_service.update_lead_booking_status(
        db,
        org_id=org.id,
        actor_id=actor.id,
        lead_id=lead.id,
        booking_id=booking["id"],
        status="attended",
    )
    assert updated["status"] == "attended"
    assert updated["attended_at"] is not None
    assert lead.stage == "visited"


@pytest.mark.asyncio
async def test_cancelled_trial_releases_capacity_and_allows_tour(booking_db):
    db = booking_db
    org = Organization(name="Tour Gym", org_code="TOUR-GYM")
    actor = User(email="tour-owner@example.com", hashed_password="unused")
    db.add_all([org, actor])
    await db.flush()
    lead = await leads_service.create_lead(
        db, org_id=org.id, actor_id=actor.id, data=LeadCreate(name="Tour Prospect"),
    )
    class_session = ClassSession(
        organization_id=org.id,
        title="Intro Strength",
        starts_at=now_utc() + timedelta(days=2),
        capacity=1,
    )
    db.add(class_session)
    await db.flush()
    trial = await leads_service.create_lead_booking(
        db,
        org_id=org.id,
        actor_id=actor.id,
        lead_id=lead.id,
        booking_type="trial",
        class_session_id=class_session.id,
        trainer_member_id=None,
        starts_at=None,
        ends_at=None,
        notes=None,
    )

    await leads_service.update_lead_booking_status(
        db,
        org_id=org.id,
        actor_id=actor.id,
        lead_id=lead.id,
        booking_id=trial["id"],
        status="cancelled",
    )
    assert class_session.booked_count == 0

    tour = await leads_service.create_lead_booking(
        db,
        org_id=org.id,
        actor_id=actor.id,
        lead_id=lead.id,
        booking_type="tour",
        class_session_id=None,
        trainer_member_id=None,
        starts_at=now_utc() + timedelta(days=3),
        ends_at=None,
        notes="Show accessible entrance",
    )
    assert tour["booking_type"] == "tour"
    assert tour["ends_at"] - tour["starts_at"] == timedelta(minutes=30)


@pytest.mark.asyncio
async def test_trial_slots_and_bookings_are_tenant_scoped(booking_db):
    db = booking_db
    org = Organization(name="Primary Gym", org_code="PRIMARY-TRIAL")
    other_org = Organization(name="Other Gym", org_code="OTHER-TRIAL")
    actor = User(email="tenant-trial@example.com", hashed_password="unused")
    db.add_all([org, other_org, actor])
    await db.flush()
    lead = await leads_service.create_lead(
        db, org_id=org.id, actor_id=actor.id, data=LeadCreate(name="Scoped Prospect"),
    )
    other_class = ClassSession(
        organization_id=other_org.id,
        title="Other Gym Class",
        starts_at=now_utc() + timedelta(days=1),
        capacity=4,
    )
    db.add(other_class)
    await db.flush()

    assert await leads_service.list_trial_slots(db, org_id=org.id) == []
    with pytest.raises(HTTPException) as class_error:
        await leads_service.create_lead_booking(
            db,
            org_id=org.id,
            actor_id=actor.id,
            lead_id=lead.id,
            booking_type="trial",
            class_session_id=other_class.id,
            trainer_member_id=None,
            starts_at=None,
            ends_at=None,
            notes=None,
        )
    assert class_error.value.status_code == 404
    with pytest.raises(HTTPException) as lead_error:
        await leads_service.list_lead_bookings(db, org_id=other_org.id, lead_id=lead.id)
    assert lead_error.value.status_code == 404
