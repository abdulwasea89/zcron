import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select
from starlette.requests import Request

from app.api.v1.routes import inbox_webhooks
from app.models.lead import Lead, LeadFollowUp
from app.models.organization import Organization
from app.models.staff import Task
from app.services import lead_capture_service as capture
from app.services.inbox_channels_service import _validate

CREDENTIALS = {"sender_id": "111", "lead_form_ids": "222", "page_access_token": "private-page-token",
               "app_secret": "private-app-secret", "verify_token": "verification-token"}
EVENT = {"page_id": "111", "form_id": "222", "leadgen_id": "1000"}


def payload(identifier="1000", name="Amina", goal="Strength"):
    return {"id": identifier, "form_id": "222", "field_data": [
        {"name": "full_name", "values": [name]}, {"name": "email", "values": ["AMINA@test.com"]},
        {"name": "phone_number", "values": ["+1 555 010 2030"]},
        {"name": "fitness_goal", "values": [goal]},
        {"name": "marketing_consent", "values": ["true"]},
    ]}


@pytest.mark.asyncio
async def test_capture_deduplicates_events_and_contacts_without_overwriting_consent(monkeypatch):
    calls = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, url, *, params, headers):
            assert "access_token" not in params and CREDENTIALS["page_access_token"] not in url
            assert headers["Authorization"] == "Bearer private-page-token"
            calls.append(url)
            identifier = url.rsplit("/", 1)[-1]
            body = payload(identifier, "Changed name" if identifier == "1001" else "Amina", "Changed goal")
            return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    async def event(*_args, **_kwargs):
        pass

    monkeypatch.setattr(capture.httpx, "AsyncClient", Client)
    monkeypatch.setattr(capture.events, "task_changed", event)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class Facade:
                def get_bind(self):
                    return db.get_bind()

                async def get(self, *args, **kwargs):
                    return db.get(*args, **kwargs)

                async def execute(self, statement):
                    return db.execute(statement)

                async def flush(self):
                    db.flush()

                def add(self, row):
                    db.add(row)

            session = Facade()
            db.add_all([Organization(id="gym", name="Gym", org_code="GYM"),
                        Organization(id="other", name="Other", org_code="OTHER")])
            db.commit()
            lead_id = await capture.capture_meta_lead(session, org_id="gym", credentials=CREDENTIALS, value=EVENT)
            db.commit()
            lead = db.get(Lead, lead_id)
            assert lead.name == "Amina" and lead.source == "facebook" and lead.email == "amina@test.com"
            assert lead.phone == "+15550102030" and lead.contact_handle is None
            assert not lead.email_followup_consent and not lead.sms_followup_consent
            assert lead.profile_sources["goal"] == "meta_lead_ads"
            assert len(db.exec(select(LeadFollowUp)).all()) == 4
            assert {row.email_status for row in db.exec(select(LeadFollowUp)).all()} == {"skipped"}
            replay = await capture.capture_meta_lead(session, org_id="gym", credentials=CREDENTIALS,
                                                      value={**EVENT, "created_time": 123})
            assert replay == lead_id and len(calls) == 1
            lead.stage = "contacted"
            lead.email_followup_consent = True
            lead.goal = "Staff agreed goal"
            db.add(lead)
            db.commit()
            duplicate = await capture.capture_meta_lead(session, org_id="gym", credentials=CREDENTIALS,
                                                        value={**EVENT, "leadgen_id": "1001"})
            db.commit()
            assert duplicate == lead_id
            assert lead.name == "Amina" and lead.stage == "contacted" and lead.goal == "Staff agreed goal"
            assert lead.email_followup_consent is True
            assert len(db.exec(select(Lead)).all()) == 1 and len(db.exec(select(Task)).all()) == 1
            await capture.capture_meta_lead(session, org_id="gym", credentials=CREDENTIALS,
                                            value={**EVENT, "leadgen_id": "1001"})
            db.commit()
            assert len(db.exec(select(Task)).all()) == 1
            other_id = await capture.capture_meta_lead(session, org_id="other", credentials={**CREDENTIALS, "sender_id": "333"},
                                                       value={**EVENT, "page_id": "333"})
            db.commit()
            assert other_id != lead_id and db.get(Lead, other_id).organization_id == "other"
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"page_id": "foreign"}, {"form_id": "333"}])
async def test_unapproved_page_or_form_is_ignored_before_accessing_data(change):
    assert await capture.capture_meta_lead(None, org_id="gym", credentials=CREDENTIALS, value={**EVENT, **change}) is None


def test_form_configuration_and_contact_validation():
    assert _validate("messenger", {**CREDENTIALS, "lead_form_ids": "222, 333,222"})["lead_form_ids"] == "222,333"
    assert "lead_form_ids" not in _validate("messenger", {**CREDENTIALS, "lead_form_ids": ""})
    for forms in ("https://unsafe.example", ",".join(str(i) for i in range(21))):
        with pytest.raises(HTTPException):
            _validate("messenger", {**CREDENTIALS, "lead_form_ids": forms})
    with pytest.raises(HTTPException):
        capture.meta_lead_fields({"field_data": [{"name": "full_name", "values": ["No contact"]}]})


@pytest.mark.asyncio
async def test_meta_webhook_checks_signature_hook_and_page_before_dispatch(monkeypatch):
    dispatched = []
    completion_order = []

    async def credentials(*_args):
        return CREDENTIALS

    async def connection(*_args):
        return SimpleNamespace(webhook_token="private-hook")

    async def org(*_args):
        pass

    async def intake(*_args, **kwargs):
        dispatched.append(kwargs["value"])
        return "captured"

    async def commit():
        completion_order.append("commit")

    async def publish(*_args):
        completion_order.append("publish")

    monkeypatch.setattr(inbox_webhooks.channels, "get_credentials", credentials)
    monkeypatch.setattr(inbox_webhooks.channels, "get_connection", connection)
    monkeypatch.setattr(inbox_webhooks, "_check_org", org)
    monkeypatch.setattr(capture, "capture_meta_lead", intake)
    monkeypatch.setattr(inbox_webhooks.events, "publish", publish)
    body = json.dumps({"entry": [
        {"id": "999", "changes": [{"field": "leadgen", "value": EVENT}]},
        {"id": "111", "changes": [{"field": "leadgen", "value": EVENT}]},
    ]}).encode()

    def request(signature):
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({"type": "http", "headers": [(b"x-hub-signature-256", signature.encode())]}, receive)

    signature = "sha256=" + hmac.new(CREDENTIALS["app_secret"].encode(), body, hashlib.sha256).hexdigest()
    await inbox_webhooks.meta_inbound("gym", "messenger", request(signature), hook="private-hook", session=SimpleNamespace(commit=commit))
    assert dispatched == [EVENT]
    assert completion_order == ["commit", "publish"]
    for supplied_signature, hook in [("invalid", "private-hook"), (signature, "wrong-hook")]:
        with pytest.raises(HTTPException) as error:
            await inbox_webhooks.meta_inbound("gym", "messenger", request(supplied_signature), hook=hook, session=object())
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_provider_failure_is_sanitized_and_unsafe_identifiers_are_rejected(monkeypatch):
    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True)

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def get(self, *_args, **_kwargs):
            raise httpx.TimeoutException("Internal provider failure private-page-token")

    monkeypatch.setattr(capture.idempotency_service, "claim", claim)
    monkeypatch.setattr(capture.httpx, "AsyncClient", Client)
    with pytest.raises(HTTPException) as error:
        await capture.capture_meta_lead(None, org_id="gym", credentials=CREDENTIALS, value=EVENT)
    assert error.value.status_code == 502 and "private-page-token" not in error.value.detail
    with pytest.raises(HTTPException) as error:
        await capture.capture_meta_lead(None, org_id="gym", credentials=CREDENTIALS,
                                       value={**EVENT, "leadgen_id": "../../unapproved-path"})
    assert error.value.status_code == 400
