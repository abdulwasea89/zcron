import csv
import hashlib
import io
import json
import zipfile
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes import finance
from app.core.constants import Role
from app.core.tenancy import TenantContext
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.organization import Organization
from app.models.receipt import ReceiptUpload
from app.models.user import User


def test_accounting_period_uses_gym_timezone_across_dst():
    start, end = finance.period_bounds(date(2026, 3, 8), date(2026, 3, 8), "America/New_York")
    assert start.hour == 5 and end.hour == 4
    assert end - start == timedelta(hours=23)


@pytest.mark.parametrize("start,end", [(date(2026, 2, 1), date(2026, 1, 1)), (date(2024, 1, 1), date(2026, 1, 1)), (date.max, date.max)])
def test_accounting_period_rejects_invalid_or_unbounded_dates(start, end):
    with pytest.raises(HTTPException) as error:
        finance.period_bounds(start, end, "UTC")
    assert error.value.status_code == 422


def test_csv_escapes_formulas_and_quotes():
    row = finance.csv_row([" =HYPERLINK(\"evil\")", "safe,quoted", None])
    values = next(csv.reader(io.StringIO(row)))
    assert values == ["' =HYPERLINK(\"evil\")", "safe,quoted", ""]


@pytest.mark.asyncio
async def test_streamed_accounting_export_is_tenant_scoped_and_audited(monkeypatch):
    payment = Payment(organization_id="org", amount=100.3, refunded_amount=0.2)
    audits = []

    async def get(*_args):
        return Organization(id="org", name="Gym", timezone="UTC")

    class Rows:
        async def __aiter__(self):
            yield payment

    async def stream(query):
        assert query.compile().params["organization_id_1"] == "org"
        return Rows()

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(finance, "record_audit", audit)
    request = SimpleNamespace(headers={}, client=None)
    response = await finance.export_payments(request, date(2026, 1, 1), date(2026, 1, 31),
                                             TenantContext("actor", "org", Role.OWNER), SimpleNamespace(get=get, stream_scalars=stream))
    content = "".join([part async for part in response.body_iterator])
    rows = list(csv.reader(io.StringIO(content.lstrip("\ufeff"))))
    assert rows[1][7:11] == ["100.30", "0.00", "0.20", "100.10"]
    assert audits[0]["organization_id"] == "org"
    assert audits[0]["action"] == "finance.payments_exported"


@pytest.mark.asyncio
async def test_foreign_payment_evidence_is_denied_before_any_other_read():
    async def get(*_args):
        return Payment(organization_id="other")

    with pytest.raises(HTTPException) as error:
        await finance.payment_evidence("payment", None, TenantContext("actor", "org", Role.OWNER), SimpleNamespace(get=get))
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_evidence_zip_omits_private_profile_values_and_hashes_attachments(monkeypatch):
    member = OrganizationMember(id="member", organization_id="org", user_id="user", health_notes="PRIVATE HEALTH", id_document_last4="ABCD")
    user = User(id="user", email="member@example.com", full_name="Member", hashed_password="PRIVATE PASSWORD")
    receipt = ReceiptUpload(id="receipt", organization_id="org", member_id=member.id, image_data=b"original image", image_media_type="image/png")
    payment = Payment(id="payment", organization_id="org", member_id=member.id, receipt_id=receipt.id, amount=100)
    audits = []

    async def get(model, _id):
        return {Payment: payment, OrganizationMember: member, User: user, ReceiptUpload: receipt}[model]

    async def execute(query):
        assert "audit_logs.organization_id" in str(query)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(finance, "record_audit", audit)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
    response = await finance.payment_evidence(payment.id, request, TenantContext("actor", "org", Role.MANAGER), SimpleNamespace(get=get, execute=execute))
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        evidence = archive.read("evidence.json")
        assert b"PRIVATE HEALTH" not in evidence and b"PRIVATE PASSWORD" not in evidence and b"ABCD" not in evidence
        assert archive.read("receipt.png") == b"original image"
        manifest = json.loads(archive.read("manifest.json"))
        for name, checksum in manifest.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
    assert audits[0]["action"] == "payment.evidence_exported"
    assert response.headers["cache-control"] == "no-store"
