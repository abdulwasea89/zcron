from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.constants import Role
from app.models.membership import OrganizationMember
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.schemas.cash import CashPaymentLog
from app.services import cash_service as cash


def test_family_shares_sum_without_binary_float_rounding():
    data = CashPaymentLog(member_id="holder", plan_id="plan", amount=0.3,
                          payer_shares=[{"member_id": "holder", "amount": "0.10"}, {"member_id": "dependent", "amount": "0.20"}])
    assert sum(share.amount for share in data.payer_shares) == Decimal("0.30")


@pytest.mark.parametrize("shares", [
    [{"member_id": "holder", "amount": "0.10"}],
    [{"member_id": "holder", "amount": "0.10"}, {"member_id": "holder", "amount": "0.20"}],
    [{"member_id": "holder", "amount": "-0.10"}, {"member_id": "dependent", "amount": "0.40"}],
    [{"member_id": "holder", "amount": "0.101"}, {"member_id": "dependent", "amount": "0.199"}],
    [{"member_id": "holder", "amount": "NaN"}],
])
def test_family_shares_reject_wrong_totals_duplicates_and_invalid_money(shares):
    with pytest.raises(ValidationError):
        CashPaymentLog(member_id="holder", plan_id="plan", amount=0.3, payer_shares=shares)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", [False, True])
async def test_family_payment_creates_one_payment_and_subscription_or_rejects_foreign_payer(monkeypatch, foreign):
    holder = OrganizationMember(id="holder", organization_id="org", user_id="holder-user", role=Role.MEMBER)
    dependent = OrganizationMember(id="dependent", organization_id="other" if foreign else "org", user_id="dependent-user", role=Role.MEMBER, family_owner_member_id=holder.id)
    plan = MembershipPlan(id="plan", organization_id="org", name="Family", price=100, audience="family")
    saved = []

    class Session:
        async def get(self, model, key):
            return {"holder": holder, "dependent": dependent, "plan": plan}.get(key)

        def add(self, item):
            saved.append(item)

        async def flush(self):
            pass

    async def quote(*_args, **_kwargs):
        return SimpleNamespace(total=100, tax_amount=0, plan_price=100, joining_fee=0, discount_amount=0, promo_code=None)

    async def noop(*_args, **_kwargs):
        pass

    monkeypatch.setattr(cash, "quote_member_payment", quote)
    for name in ("send_email", "send_push", "record_audit", "create_notification"):
        monkeypatch.setattr(cash, name, noop)
    monkeypatch.setattr(cash.events, "payment_recorded", noop)
    monkeypatch.setattr(cash.events, "membership_changed", noop)
    from app.services import family_service, referrals_service, onboarding_service, winback_service
    monkeypatch.setattr(family_service, "sync_family_status", noop)
    monkeypatch.setattr(referrals_service, "qualify_referral_for_member", noop)
    monkeypatch.setattr(onboarding_service, "start_journey", noop)
    monkeypatch.setattr(winback_service, "mark_recovered", noop)
    data = CashPaymentLog(member_id=holder.id, plan_id=plan.id, amount=100,
                          payer_shares=[{"member_id": holder.id, "amount": "40.00"}, {"member_id": dependent.id, "amount": "60.00"}])
    if foreign:
        with pytest.raises(HTTPException) as error:
            await cash.log_cash_payment(Session(), org_id="org", data=data, staff_user_id="staff")
        assert error.value.status_code == 422 and saved == []
    else:
        payment, _member, _url = await cash.log_cash_payment(Session(), org_id="org", data=data, staff_user_id="staff")
        assert payment.amount == 100
        assert payment.payer_contributions == [{"member_id": "holder", "amount": "40.00"}, {"member_id": "dependent", "amount": "60.00"}]
        assert len({item.id for item in saved if isinstance(item, Payment)}) == 1
        assert len([item for item in saved if isinstance(item, Subscription)]) == 1
