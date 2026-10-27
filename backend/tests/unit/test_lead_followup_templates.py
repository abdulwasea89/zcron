import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from app.api.v1.routes.leads import LeadFollowupTemplate, LeadFollowupTemplatesIn
from app.services import lead_followup_delivery
from app.services.lead_followup_delivery import configured_sms_template
from app.workers.lead_followups import configured_followup_email


def test_followup_templates_default_and_custom_override():
    default_subject, _ = configured_followup_email(1)
    assert configured_followup_email(1, {"1": {"body": "Hi {name}, come visit."}}) == (
        default_subject, "Hi {name}, come visit.",
    )
    assert configured_sms_template(1, {"1": {"sms_body": "Hi {name}, come by."}}) == "Hi {name}, come by."


def test_followup_template_rejects_unknown_placeholders():
    with pytest.raises(ValidationError, match=r"only the \{name\} placeholder"):
        LeadFollowupTemplate(subject="Hello {email}", body="Welcome", sms_body="Hi {name}")


def test_followup_schedule_requires_all_days():
    with pytest.raises(ValidationError, match="days 0, 1, 3, and 7"):
        LeadFollowupTemplatesIn(templates={"0": {
            "subject": "Hello", "body": "Hi {name}", "sms_body": "Text {name}",
        }})


@pytest.mark.asyncio
async def test_consent_gated_sms_uses_custom_text_and_adds_stop_instruction(monkeypatch):
    lead = SimpleNamespace(
        id="lead", organization_id="gym", phone="+15550102030", name="Taylor Member",
        created_by="staff", sms_followup_consent=True,
    )
    seen = {}

    async def credentials(*_args):
        return {"account_sid": "sid"}

    async def find_or_create(*_args, **_kwargs):
        return SimpleNamespace(id="conversation")

    async def reply(*_args, **kwargs):
        seen["body"] = kwargs["body"]
        return {"messages": [{"direction": "outbound", "delivery_status": "sent"}]}

    class Session:
        async def get(self, *_args):
            return SimpleNamespace(lead_followup_templates={"1": {"sms_body": "Hi {name}, see you soon."}})

    monkeypatch.setattr(lead_followup_delivery, "get_credentials", credentials)
    monkeypatch.setattr(lead_followup_delivery.inbox_service, "find_or_create", find_or_create)
    monkeypatch.setattr(lead_followup_delivery.inbox_service, "reply", reply)

    status = await lead_followup_delivery.send_lead_followup_sms(Session(), lead=lead, day=1)
    assert status == "sent"
    assert seen["body"] == "Hi Taylor, see you soon. Reply STOP to opt out."


@pytest.mark.asyncio
async def test_sms_followup_skips_without_explicit_permission():
    lead = SimpleNamespace(phone="+15550102030", sms_followup_consent=False)
    assert await lead_followup_delivery.send_lead_followup_sms(object(), lead=lead, day=1) == "skipped"
