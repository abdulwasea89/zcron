from types import SimpleNamespace

import pytest

from app.api.v1.routes import cash, receipts
from app.core.constants import Role
from app.core.tenancy import TenantContext


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, value=None):
        self.value = value

    async def execute(self, _statement):
        return Result(self.value)


def _request():
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "receipt-test"},
    )


@pytest.mark.asyncio
async def test_cash_receipt_download_is_audited(monkeypatch):
    audits = []

    async def render_receipt(*_args, **_kwargs):
        return b"pdf", "receipt.pdf"

    async def record_audit(_session, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(cash.cash, "render_receipt", render_receipt)
    monkeypatch.setattr(cash, "record_audit", record_audit)
    response = await cash.cash_payment_receipt(
        "payment", _request(), TenantContext("staff", "gym", Role.OWNER), Session(),
    )

    assert response.body == b"pdf"
    assert audits[0]["action"] == "cash.payment_receipt_viewed"
    assert audits[0]["entity_id"] == "payment"
    assert audits[0]["ip_address"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_uploaded_payment_proof_view_is_audited(monkeypatch):
    audits = []

    async def record_audit(_session, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(receipts, "record_audit", record_audit)
    upload = SimpleNamespace(
        id="receipt", organization_id="gym", image_data=b"image", image_media_type="image/png",
    )
    response = await receipts.receipt_image(
        "receipt", _request(), TenantContext("staff", "gym", Role.OWNER), Session(upload),
    )

    assert response.body == b"image"
    assert audits[0]["action"] == "receipt.image_viewed"
    assert audits[0]["entity_id"] == "receipt"
    assert audits[0]["user_agent"] == "receipt-test"
