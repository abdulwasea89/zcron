import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.constants import PaymentMethod, ReceiptStatus
from app.models.receipt import ReceiptUpload
from app.schemas.cash import CashPaymentLog
from app.services.receipts_service import review


@pytest.mark.parametrize("method", [PaymentMethod.CARD, PaymentMethod.INVOICE])
def test_offline_payment_rejects_online_and_invoice_methods(method):
    with pytest.raises(ValidationError):
        CashPaymentLog(member_id="member", plan_id="plan", amount=10, method=method)


@pytest.mark.parametrize("amount", [-1, math.nan, math.inf])
def test_offline_payment_rejects_invalid_amounts(amount):
    with pytest.raises(ValidationError):
        CashPaymentLog(member_id="member", plan_id="plan", amount=amount)


@pytest.mark.parametrize("method", [PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER, PaymentMethod.MOBILE_WALLET])
def test_offline_payment_accepts_supported_methods(method):
    assert CashPaymentLog(member_id="member", plan_id="plan", amount=0, method=method).method == method


async def test_already_reviewed_receipt_cannot_be_approved_again():
    receipt = SimpleNamespace(organization_id="gym", status=ReceiptStatus.APPROVED)
    session = SimpleNamespace(get=AsyncMock(return_value=receipt))
    with pytest.raises(HTTPException) as error:
        await review(session, org_id="gym", receipt_id="receipt", action="approve",
                     reason=None, reviewer_user_id="staff", settlement_confirmed=True)
    assert error.value.status_code == 409
    session.get.assert_awaited_once_with(ReceiptUpload, "receipt", with_for_update=True, populate_existing=True)
