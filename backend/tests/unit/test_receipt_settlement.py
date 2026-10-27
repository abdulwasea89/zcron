from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.core.constants import ReceiptStatus, TaxMode
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.services import audit_service, family_service, receipts_service, referrals_service


class AsyncFacade:
    def __init__(self, db):
        self.db = db

    async def get(self, *args, **kwargs):
        return self.db.get(*args, **kwargs)

    async def execute(self, statement):
        return self.db.execute(statement)

    async def flush(self):
        self.db.flush()

    def add(self, row):
        self.db.add(row)


async def test_receipt_approval_requires_matching_settlement_and_records_quote(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(receipts_service, "_notify", AsyncMock())
    monkeypatch.setattr(receipts_service.events, "receipt_processed", AsyncMock())
    monkeypatch.setattr(audit_service, "record_audit", AsyncMock())
    monkeypatch.setattr(family_service, "sync_family_status", AsyncMock())
    monkeypatch.setattr(referrals_service, "qualify_referral_for_member", AsyncMock())
    with Session(engine) as db:
        db.add_all([
            Organization(id="gym", name="Gym", org_code="GYM"),
            OrganizationMember(id="member", organization_id="gym", user_id="user"),
            MembershipPlan(id="plan", organization_id="gym", name="Plan", price=100, joining_fee=10,
                           tax_mode=TaxMode.ADDED, tax_rate=0.1, currency="USD"),
            ReceiptUpload(id="receipt", organization_id="gym", member_id="member", plan_id="plan",
                          status=ReceiptStatus.PENDING_REVIEW),
        ])
        db.flush()
        session = AsyncFacade(db)
        for amount in (None, 100, 121.001):
            with pytest.raises(HTTPException) as error:
                await receipts_service.review(session, org_id="gym", receipt_id="receipt", action="approve",
                    reason=None, reviewer_user_id="staff", settlement_confirmed=True, verified_amount=amount)
            assert error.value.status_code == 422
            assert db.get(ReceiptUpload, "receipt").payment_id is None
        receipt = await receipts_service.review(session, org_id="gym", receipt_id="receipt", action="approve",
            reason=None, reviewer_user_id="staff", settlement_confirmed=True, verified_amount=121)
        payment = db.get(Payment, receipt.payment_id)
        assert receipt.status == ReceiptStatus.APPROVED
        assert (payment.amount, payment.plan_price_amount, payment.joining_fee_amount, payment.tax_amount) == (121, 100, 10, 11)
    engine.dispose()
