from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes import finance
from app.core.constants import Role
from app.core.tenancy import TenantContext
from app.integrations import stripe_connect
from app.models.organization import Organization
from app.models.payment import Payment
from app.schemas.disputes import DisputeEvidenceRequest


@pytest.mark.asyncio
async def test_disputes_are_matched_only_to_the_current_gyms_payments(monkeypatch):
    payment = Payment(id="payment-1", organization_id="gym-1", stripe_charge_id="ch_1")
    audits = []

    class Rows:
        def scalars(self):
            return SimpleNamespace(all=lambda: [payment])

    async def execute(query):
        assert "payments.organization_id" in str(query)
        return Rows()

    async def list_disputes(*, connected_account_id):
        assert connected_account_id == "acct_gym"
        return [{"id": "dp_1", "charge_id": "ch_1", "payment_intent_id": None,
                 "amount": 1299, "currency": "usd", "reason": "product_not_received",
                 "status": "needs_response", "created": 1, "evidence_due_by": 2,
                 "has_evidence": False, "submission_count": 0}]

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(finance.connect_stripe, "list_disputes", list_disputes)
    monkeypatch.setattr(finance, "record_audit", audit)
    session = SimpleNamespace(
        get=lambda *_: None,
        execute=execute,
    )
    async def get(model, _id):
        assert model is Organization
        return Organization(id="gym-1", name="Gym", stripe_connect_account_id="acct_gym")
    session.get = get

    result = await finance.list_disputes(
        SimpleNamespace(headers={}, client=None), TenantContext("actor", "gym-1", Role.OWNER), session,
    )
    assert result[0]["amount"] == "12.99"
    assert result[0]["currency"] == "USD"
    assert result[0]["payment_id"] == "payment-1"
    assert audits[0]["action"] == "finance.disputes_viewed"


@pytest.mark.asyncio
@pytest.mark.parametrize("submit", [False, True])
async def test_dispute_evidence_is_idempotent_and_audits_field_names_only(monkeypatch, submit):
    record = object()
    saved = {}
    audits = []

    async def claim(*_args, **kwargs):
        assert kwargs["endpoint"] == "finance.dispute-evidence:gym-1:dp_1"
        return SimpleNamespace(claimed=True, record=record)

    async def retrieve(*, connected_account_id, dispute_id):
        assert (connected_account_id, dispute_id) == ("acct_gym", "dp_1")
        return {"status": "needs_response"}

    async def save_evidence(**kwargs):
        saved.update(kwargs)
        return {"status": "under_review" if kwargs["submit"] else "needs_response"}

    async def complete(_session, _record, *, code, body):
        saved["cached_response"] = body
        assert (_record, code) == (record, 200)

    async def audit(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(finance.idempotency_service, "claim", claim)
    monkeypatch.setattr(finance.idempotency_service, "complete", complete)
    monkeypatch.setattr(finance.connect_stripe, "retrieve_dispute", retrieve)
    monkeypatch.setattr(finance.connect_stripe, "submit_dispute_evidence", save_evidence)
    monkeypatch.setattr(finance, "record_audit", audit)

    async def get(model, _id):
        assert model is Organization
        return Organization(id="gym-1", name="Gym", stripe_connect_account_id="acct_gym")

    result = await finance.submit_dispute_evidence(
        "dp_1", DisputeEvidenceRequest(customer_name="Member", customer_communication=" ", submit=submit),
        SimpleNamespace(headers={}, client=None), "idem-1",
        TenantContext("actor", "gym-1", Role.OWNER), SimpleNamespace(get=get),
    )
    assert saved["evidence"] == {"customer_name": "Member"}
    assert saved["submit"] is submit
    assert result["submitted"] is submit
    assert audits[0]["metadata"]["evidence_fields"] == ["customer_name"]
    assert "Member" not in str(audits[0]["metadata"])


@pytest.mark.asyncio
async def test_dispute_evidence_rejects_closed_dispute(monkeypatch):
    failures = []
    async def claim(*_args, **_kwargs):
        return SimpleNamespace(claimed=True, record=object())
    async def fail(_session, record, *, code, body):
        failures.append((code, body))
    async def get(*_args):
        return Organization(id="gym-1", name="Gym", stripe_connect_account_id="acct_gym")
    async def retrieve(**_kwargs):
        return {"status": "won"}
    async def should_not_submit(**_kwargs):
        raise AssertionError("Closed disputes must not accept evidence")

    monkeypatch.setattr(finance.idempotency_service, "claim", claim)
    monkeypatch.setattr(finance.idempotency_service, "fail", fail)
    monkeypatch.setattr(finance.connect_stripe, "retrieve_dispute", retrieve)
    monkeypatch.setattr(finance.connect_stripe, "submit_dispute_evidence", should_not_submit)
    with pytest.raises(HTTPException) as error:
        await finance.submit_dispute_evidence(
            "dp_1", DisputeEvidenceRequest(customer_name="Member"),
            SimpleNamespace(headers={}, client=None), "idem-1",
            TenantContext("actor", "gym-1", Role.OWNER), SimpleNamespace(get=get),
        )
    assert error.value.status_code == 409
    assert failures[0][0] == 409


@pytest.mark.asyncio
async def test_dispute_file_upload_validates_file_and_uploads_to_connected_account(monkeypatch):
    record = object()
    saved = {}
    async def get(*_args):
        return Organization(id="gym-1", name="Gym", stripe_connect_account_id="acct_gym")
    async def retrieve(**kwargs):
        assert kwargs == {"connected_account_id": "acct_gym", "dispute_id": "dp_1"}
        return {"status": "needs_response"}
    async def claim(*_args, **kwargs):
        assert kwargs["body"]["sha256"]
        return SimpleNamespace(claimed=True, record=record)
    async def upload(**kwargs):
        saved.update(kwargs)
        return {"id": "file_1", "filename": kwargs["filename"], "purpose": "dispute_evidence"}
    async def complete(_session, _record, *, code, body):
        assert (_record, code) == (record, 200)
        saved["cached"] = body
    async def audit(*_args, **kwargs):
        saved["audit"] = kwargs

    monkeypatch.setattr(finance.connect_stripe, "retrieve_dispute", retrieve)
    monkeypatch.setattr(finance.connect_stripe, "upload_dispute_evidence_file", upload)
    monkeypatch.setattr(finance.idempotency_service, "claim", claim)
    monkeypatch.setattr(finance.idempotency_service, "complete", complete)
    monkeypatch.setattr(finance, "record_audit", audit)

    class Uploaded:
        filename = r"C:\unsafe\proof.pdf"
        async def read(self, limit):
            assert limit == finance.DISPUTE_FILE_LIMIT + 1
            return b"%PDF-test evidence"

    result = await finance.upload_dispute_evidence_file(
        "dp_1", SimpleNamespace(headers={}, client=None), Uploaded(), "idem-file",
        TenantContext("actor", "gym-1", Role.OWNER), SimpleNamespace(get=get),
    )
    assert result == {"id": "file_1", "filename": "proof.pdf"}
    assert saved["connected_account_id"] == "acct_gym"
    assert saved["content"] == b"%PDF-test evidence"
    assert saved["audit"]["action"] == "finance.dispute_evidence_file_uploaded"


@pytest.mark.asyncio
async def test_dispute_file_upload_rejects_unknown_file_type_before_provider_call(monkeypatch):
    async def get(*_args):
        return Organization(id="gym-1", name="Gym", stripe_connect_account_id="acct_gym")
    async def retrieve(**_kwargs):
        return {"status": "needs_response"}
    async def should_not_upload(**_kwargs):
        raise AssertionError("Invalid file types must not be uploaded")
    monkeypatch.setattr(finance.connect_stripe, "retrieve_dispute", retrieve)
    monkeypatch.setattr(finance.connect_stripe, "upload_dispute_evidence_file", should_not_upload)

    class Uploaded:
        filename = "payload.exe"
        async def read(self, _limit):
            return b"MZ executable"

    with pytest.raises(HTTPException) as error:
        await finance.upload_dispute_evidence_file(
            "dp_1", SimpleNamespace(headers={}, client=None), Uploaded(), "idem-file",
            TenantContext("actor", "gym-1", Role.OWNER), SimpleNamespace(get=get),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_stripe_file_adapter_uses_dispute_purpose_and_connected_account(monkeypatch):
    calls = {}
    class Files:
        @staticmethod
        def create(**kwargs):
            calls["create"] = kwargs
            return SimpleNamespace(id="file_1", purpose="dispute_evidence", filename=kwargs["file"].name)
        @staticmethod
        def retrieve(file_id, **kwargs):
            calls["retrieve"] = (file_id, kwargs)
            return SimpleNamespace(id=file_id, purpose="dispute_evidence")

    client = object.__new__(stripe_connect.StripeConnect)
    client.live = True
    monkeypatch.setattr(stripe_connect, "_stripe", SimpleNamespace(File=Files))
    uploaded = await client.upload_dispute_evidence_file(
        connected_account_id="acct_gym", filename="proof.pdf", content=b"%PDF-test",
        idempotency_key="file-key",
    )
    assert uploaded == {"id": "file_1", "purpose": "dispute_evidence", "filename": "proof.pdf"}
    assert calls["create"]["purpose"] == "dispute_evidence"
    assert calls["create"]["stripe_account"] == "acct_gym"
    assert calls["create"]["idempotency_key"] == "file-key"
    assert calls["create"]["file"].read() == b"%PDF-test"
    assert await client.retrieve_dispute_evidence_file(connected_account_id="acct_gym", file_id="file_1") == {
        "id": "file_1", "purpose": "dispute_evidence",
    }
    assert calls["retrieve"] == ("file_1", {"stripe_account": "acct_gym"})
