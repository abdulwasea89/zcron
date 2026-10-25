import pytest
from fastapi import HTTPException

from app.services.inbox_channels_service import _validate


def test_sms_call_forward_number_is_optional_and_normalized():
    base = {"account_sid": "AC123", "auth_token": "token", "from_number": "+14155550100"}
    assert "forward_to_number" not in _validate("sms", base)
    assert _validate("sms", {**base, "forward_to_number": " +14155550123 "})["forward_to_number"] == "+14155550123"


@pytest.mark.parametrize("number", ["4155550123", "+1 415 555 0123", "+123456", "+1234567890123456"])
def test_sms_call_forward_number_requires_e164_shape(number):
    with pytest.raises(HTTPException) as exc:
        _validate("sms", {
            "account_sid": "AC123", "auth_token": "token", "from_number": "+14155550100",
            "forward_to_number": number,
        })
    assert exc.value.status_code == 422
