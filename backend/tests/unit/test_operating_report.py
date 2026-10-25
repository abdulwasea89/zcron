from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlmodel import SQLModel

from app.api.v1.routes.finance import operating_report, operating_totals
from app.core.constants import PaymentStatus, Role
from app.core.tenancy import TenantContext
from app.models.operating_expense import OperatingExpense
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund


def test_operating_totals_keep_currencies_and_expense_categories_separate():
    report = operating_totals([("USD", Decimal("0.30"), 0), ("EUR", 100, 10)],
                              [("USD", Decimal("0.10"), 0)], [],
                              [("USD", "rent", 2026, 1, Decimal("0.10"))])
    assert report["USD"]["operating_cash_surplus"] == "0.10"
    assert report["EUR"]["gross_receipts"] == "100.00"
    assert report["USD"]["expense_categories"] == {"rent": "0.10"}
    assert report["USD"]["monthly_expenses"] == {"2026-01": "0.10"}


@pytest.mark.asyncio
async def test_operating_report_dates_refunds_independently_and_filters_other_tenants():
    engine = create_engine("sqlite://")
    try:
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            org = Organization(id="org", name="Gym", org_code="REPORT-GYM", timezone="UTC")
            payment = Payment(id="payment", organization_id="org", amount=200, tax_amount=20,
                              status=PaymentStatus.PARTIALLY_REFUNDED, refunded_amount=50,
                              paid_at=datetime(2026, 1, 10), refunded_at=datetime(2026, 2, 10))
            session.add_all([org, payment,
                Payment(organization_id="other", amount=9999, paid_at=datetime(2026, 1, 10), status=PaymentStatus.SUCCEEDED),
                PaymentRefund(organization_id="org", payment_id=payment.id, amount=Decimal("50.00"), currency="USD", occurred_at=datetime(2026, 2, 10), source="admin"),
                OperatingExpense(organization_id="org", category="rent", description="Rent", amount=Decimal("100.00"), currency="USD", incurred_on=date(2026, 1, 1), created_by="owner"),
            ])
            session.commit()

            class AsyncFacade:
                async def get(self, model, key):
                    return session.get(model, key)

                async def execute(self, statement):
                    return session.execute(statement)

            ctx = TenantContext("owner", "org", Role.OWNER)
            january = await operating_report(date(2026, 1, 1), date(2026, 1, 31), ctx, AsyncFacade())
            february = await operating_report(date(2026, 2, 1), date(2026, 2, 28), ctx, AsyncFacade())
            assert january["by_currency"]["USD"]["gross_receipts"] == "200.00"
            assert january["by_currency"]["USD"]["refunds"] == "0.00"
            assert january["by_currency"]["USD"]["operating_cash_surplus"] == "100.00"
            assert february["by_currency"]["USD"]["refunds"] == "50.00"
            assert february["by_currency"]["USD"]["gross_receipts"] == "0.00"
    finally:
        engine.dispose()
