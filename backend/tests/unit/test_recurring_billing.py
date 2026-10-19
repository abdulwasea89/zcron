from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.constants import MemberStatus, SubscriptionStatus
from app.services import recurring_billing_service as billing


@pytest.mark.parametrize(
    ("decline_code", "advice_code", "retryable"),
    [
        ("insufficient_funds", None, True),
        ("processing_error", None, True),
        ("issuer_not_available", None, True),
        ("card_declined", "try_again_later", True),
        ("insufficient_funds", "do_not_try_again", False),
        ("card_declined", None, False),
    ],
)
def test_classifies_retryable_stripe_declines(decline_code, advice_code, retryable):
    details = billing._stripe_failure_details(
        {"last_payment_error": {"code": "card_error", "decline_code": decline_code,
                                "advice_code": advice_code}}
    )

    assert details["retryable"] is retryable
    assert details["code"] == "card_error"
    assert details["decline_code"] == decline_code


def test_reads_error_body_and_payment_intent_references():
    details = billing._stripe_failure_details(
        SimpleNamespace(json_body={"error": {"code": "card_error",
                                               "decline_code": "insufficient_funds",
                                               "payment_intent": {"id": "pi_123",
                                                                   "latest_charge": {"id": "ch_123"}}}})
    )

    assert details == {
        "retryable": True,
        "code": "card_error",
        "decline_code": "insufficient_funds",
        "payment_intent_id": "pi_123",
        "charge_id": "ch_123",
    }


@pytest.mark.parametrize(
    ("attempt", "decline_code", "expected"),
    [
        (1, "insufficient_funds", timedelta(days=1)),
        (1, "processing_error", timedelta(hours=6)),
        (2, "issuer_not_available", timedelta(hours=18)),
    ],
)
def test_retry_delay_policy(attempt, decline_code, expected):
    assert billing._retry_delay(attempt, decline_code) == expected


def test_retry_scheduling_preserves_grace_and_stops_after_final_attempt(monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(billing, "now_utc", lambda: now)
    sub = SimpleNamespace(status=None, renewal_attempt_count=0, grace_until=None,
                          next_renewal_attempt_at=None)
    member = SimpleNamespace(member_status=None)

    billing._schedule_retry(sub, member, attempt=2, retryable=True,
                            decline_code="processing_error")
    assert sub.status == SubscriptionStatus.GRACE
    assert member.member_status == MemberStatus.GRACE
    assert sub.next_renewal_attempt_at == now + timedelta(hours=18)
    assert sub.grace_until == now + timedelta(days=3)

    billing._schedule_retry(sub, member, attempt=3, retryable=True,
                            decline_code="processing_error")
    assert sub.renewal_attempt_count == 3
    assert sub.next_renewal_attempt_at is None
