from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.lead import Lead
from app.services import leads_service
from app.services.leads_service import speed_to_lead_metrics


def test_speed_to_lead_reports_median_response_by_source_and_staff():
    start = datetime(2026, 1, 1)
    leads = [
        SimpleNamespace(source="web_form", stage="contacted", created_at=start, first_contacted_at=start + timedelta(minutes=10), first_contacted_by_user_id="staff-1"),
        SimpleNamespace(source="web_form", stage="joined", created_at=start, first_contacted_at=start + timedelta(minutes=30), first_contacted_by_user_id="staff-2"),
        SimpleNamespace(source="referral", stage="new", created_at=start, first_contacted_at=None, first_contacted_by_user_id=None),
        SimpleNamespace(source="website", stage="lost", created_at=start, first_contacted_at=None, first_contacted_by_user_id=None),
    ]

    report = speed_to_lead_metrics(leads, {"staff-1": "Amina", "staff-2": "Bilal"})

    assert report["leads"] == 4
    assert report["contacted"] == 2
    assert report["uncontacted"] == 1
    assert report["response_rate"] == 50.0
    assert report["median_minutes"] == 20
    assert report["by_source"] == [
        {"source": "referral", "leads": 1, "contacted": 0, "response_rate": 0, "median_minutes": None},
        {"source": "web_form", "leads": 2, "contacted": 2, "response_rate": 100.0, "median_minutes": 20},
        {"source": "website", "leads": 1, "contacted": 0, "response_rate": 0, "median_minutes": None},
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
        "uncontacted": 0,
        "by_source": [],
        "by_staff": [],
    }


@pytest.mark.asyncio
async def test_first_contact_is_recorded_on_first_meaningful_stage_change(monkeypatch):
    lead = Lead(organization_id="org", name="Prospect", stage="new")
    session = SimpleNamespace(add=lambda _row: None)

    async def record_audit(*_args, **_kwargs):
        return None

    monkeypatch.setattr(leads_service, "record_audit", record_audit)
    await leads_service.change_stage(session, lead=lead, stage="trial_booked", actor_id="owner")
    first_contact = lead.first_contacted_at

    await leads_service.change_stage(session, lead=lead, stage="contacted", actor_id="owner")

    assert first_contact is not None
    assert lead.first_contacted_at == first_contact
    assert lead.first_contacted_by_user_id == "owner"
