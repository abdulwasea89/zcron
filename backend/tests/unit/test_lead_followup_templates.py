import pytest
from pydantic import ValidationError

from app.api.v1.routes.leads import LeadFollowupEmail, LeadFollowupTemplatesIn
from app.workers.lead_followups import configured_followup_email


def test_followup_templates_default_and_custom_override():
    default_subject, _ = configured_followup_email(1)
    assert configured_followup_email(1, {"1": {"body": "Hi {name}, come visit."}}) == (
        default_subject, "Hi {name}, come visit.",
    )


def test_followup_template_rejects_unknown_placeholders():
    with pytest.raises(ValidationError, match=r"only the \{name\} placeholder"):
        LeadFollowupEmail(subject="Hello {email}", body="Welcome")


def test_followup_schedule_requires_all_days():
    with pytest.raises(ValidationError, match="days 0, 1, 3, and 7"):
        LeadFollowupTemplatesIn(templates={"0": {"subject": "Hello", "body": "Hi {name}"}})
