from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import stripe

from app.api.v1.routes import saas_billing
from app.core.constants import Role, SaasStatus
from app.core.tenancy import TenantContext
from app.services import webhook_service


@pytest.mark.asyncio
async def test_invoice_history_uses_workspace_customer_and_stripe_cursor(monkeypatch):
    calls = []

    async def stripe_call(method, **kwargs):
        calls.append((method, kwargs))
        return {"has_more": True, "data": [{
            "id": "in_recent", "total": 7900, "currency": "usd", "status": "paid",
            "created": 1_800_000_000, "invoice_pdf": "https://stripe.test/invoice.pdf",
        }]}

    monkeypatch.setattr(saas_billing.platform_stripe, "live", True)
    monkeypatch.setattr(saas_billing.workspace, "stripe_call", stripe_call)
    page = await saas_billing.invoices(
        starting_after="in_older", ctx=TenantContext("owner", "org", Role.OWNER),
        org=SimpleNamespace(id="org", stripe_customer_id="cus_workspace"), session=None,
    )

    assert calls == [(stripe.Invoice.list, {
        "customer": "cus_workspace", "limit": 100, "starting_after": "in_older",
    })]
    assert page.has_more is True
    assert page.items[0].model_dump() == {
        "id": "in_recent", "amount": 79.0, "currency": "USD", "status": "paid",
        "created_at": page.items[0].created_at, "source": "stripe",
        "invoice_pdf_url": "https://stripe.test/invoice.pdf",
    }


@pytest.mark.asyncio
async def test_paid_invoice_uses_stripe_period_end(monkeypatch):
    period_end = 1_800_000_000
    org = SimpleNamespace(
        id="org", stripe_subscription_id="sub_workspace", saas_status=SaasStatus.ACTIVE,
        saas_grace_until=None, saas_retry_count=2, saas_state_changed_at=None,
        saas_current_period_end=None,
    )
    monkeypatch.setattr(webhook_service, "_org_by_customer", AsyncMock(return_value=org))
    monkeypatch.setattr(webhook_service, "record_audit", AsyncMock())
    session = SimpleNamespace(add=lambda _row: None)

    result = await webhook_service.handle_platform_event(session, {
        "type": "invoice.payment_succeeded",
        "data": {"object": {
            "customer": "cus_workspace", "subscription": "sub_workspace",
            "lines": {"data": [{"period": {"start": 1_797_408_000, "end": period_end}}]},
        }},
    })

    assert result == {"handled": "invoice.payment_succeeded"}
    assert org.saas_current_period_end == datetime.fromtimestamp(period_end, timezone.utc).replace(tzinfo=None)
