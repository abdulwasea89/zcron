from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.lead import Lead
from app.services import leads_service
from app.services.leads_service import speed_to_lead_metrics


def test_speed_to_lead_reports_median_response_by_source_and_staff():
    start = datetime(2026, 1, 1)
    leads = [
        SimpleNamespace(source="web_form", stage="contacted", created_at=start, first_contacted_at=start + timedelta(minutes=10), first_contacted_by_user_id="staff-1", first_contact_logged=True, first_contact_delivery_status="delivered"),
        SimpleNamespace(source="web_form", stage="joined", created_at=start, first_contacted_at=start + timedelta(minutes=30), first_contacted_by_user_id="staff-2", first_contact_logged=True, first_contact_delivery_status="failed"),
        SimpleNamespace(source="referral", stage="new", created_at=start, first_contacted_at=start + timedelta(minutes=4), first_contacted_by_user_id="staff-2", first_contact_logged=False, first_contact_delivery_status="unknown"),
        SimpleNamespace(source="website", stage="lost", created_at=start, first_contacted_at=None, first_contacted_by_user_id=None, first_contact_logged=False, first_contact_delivery_status="unknown"),
    ]

    report = speed_to_lead_metrics(leads, {"staff-1": "Amina", "staff-2": "Bilal"})

    assert report["leads"] == 4
    assert report["contacted"] == 2
    assert report["uncontacted"] == 1
    assert report["response_rate"] == 50.0
    assert report["median_minutes"] == 20
    assert (report["delivery_confirmed"], report["delivery_failed"], report["delivery_unconfirmed"]) == (1, 1, 0)
    assert report["by_source"] == [
        {"source": "referral", "leads": 1, "contacted": 0, "response_rate": 0, "median_minutes": None, "conversions": 0, "conversion_rate": 0.0},
        {"source": "web_form", "leads": 2, "contacted": 2, "response_rate": 100.0, "median_minutes": 20, "conversions": 1, "conversion_rate": 50.0},
        {"source": "website", "leads": 1, "contacted": 0, "response_rate": 0, "median_minutes": None, "conversions": 0, "conversion_rate": 0.0},
    ]
    assert report["by_staff"] == [
        {"staff_name": "Amina", "contacted": 1, "median_minutes": 10, "conversions": 0, "conversion_rate": 0.0},
        {"staff_name": "Bilal", "contacted": 1, "median_minutes": 30, "conversions": 1, "conversion_rate": 100.0},
    ]


def test_speed_to_lead_empty_period_returns_zero_rates():
    assert speed_to_lead_metrics([]) == {
        "leads": 0,
        "contacted": 0,
        "response_rate": 0,
        "median_minutes": None,
        "delivery_confirmed": 0,
        "delivery_failed": 0,
        "delivery_unconfirmed": 0,
        "uncontacted": 0,
        "by_source": [],
        "by_staff": [],
    }


def test_manual_and_provider_accepted_contacts_are_unconfirmed_until_callback():
    start = datetime(2026, 1, 1)
    leads = [
        SimpleNamespace(source="call", stage="contacted", created_at=start,
                        first_contacted_at=start, first_contacted_by_user_id="staff",
                        first_contact_logged=True, first_contact_delivery_status="manual_logged"),
        SimpleNamespace(source="sms", stage="contacted", created_at=start,
                        first_contacted_at=start, first_contacted_by_user_id="staff",
                        first_contact_logged=True, first_contact_delivery_status="provider_accepted"),
    ]
    report = speed_to_lead_metrics(leads)
    assert report["delivery_confirmed"] == 0
    assert report["delivery_failed"] == 0
    assert report["delivery_unconfirmed"] == 2


@pytest.mark.asyncio
async def test_pipeline_stage_change_does_not_fake_a_contact_log(monkeypatch):
    lead = Lead(organization_id="org", name="Prospect", stage="new")
    session = SimpleNamespace(add=lambda _row: None)

    async def record_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(leads_service, "record_audit", record_audit)
    await leads_service.change_stage(session, lead=lead, stage="trial_booked", actor_id="owner")
    await leads_service.change_stage(session, lead=lead, stage="contacted", actor_id="owner")

    assert lead.first_contacted_at is None
    assert lead.first_contact_logged is False


@pytest.mark.asyncio
async def test_first_outreach_log_is_recorded_once_with_staff_and_method(monkeypatch):
    lead = Lead(organization_id="org", name="Prospect", stage="new")

    async def get(_model, _id, **_kwargs):
        return lead

    session = SimpleNamespace(get=get, add=lambda _row: None)
    audits = []

    async def record_audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(leads_service, "record_audit", record_audit)
    await leads_service.log_first_contact(
        session, org_id="org", lead_id=lead.id, actor_id="owner", method="call",
    )
    assert lead.first_contact_logged is True
    assert lead.first_contacted_at is not None
    assert lead.first_contacted_by_user_id == "owner"
    assert audits[0]["metadata"] == {"method": "call"}

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await leads_service.log_first_contact(
            session, org_id="org", lead_id=lead.id, actor_id="owner", method="call",
        )
    assert exc.value.status_code == 409
