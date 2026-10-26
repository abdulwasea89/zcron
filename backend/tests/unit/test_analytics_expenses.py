from decimal import Decimal

import pytest

from app.models.organization import Organization
from app.services.analytics_service import revenue_analytics


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return iter(self.rows)

    def all(self):
        return self.rows


@pytest.mark.asyncio
async def test_revenue_analytics_reports_non_voided_expenses_by_currency():
    class Session:
        def __init__(self):
            self.results = [Result([]), Result([]), Result([
                ("USD", Decimal("100.20")), ("PKR", Decimal("750.00")),
            ])]

        async def get(self, _model, _org_id):
            return Organization(id="org", name="Gym", org_code="GYM-1")

        async def execute(self, _statement):
            if len(self.results) == 1:
                assert "voided_at IS NULL" in str(_statement)
            return self.results.pop(0)

    result = await revenue_analytics(Session(), org_id="org")

    assert result["operating_expenses_by_currency"] == {
        "USD": "100.20", "PKR": "750.00",
    }


@pytest.mark.asyncio
async def test_revenue_currency_separation_excludes_costs_and_other_gyms():
    from datetime import datetime
    from sqlalchemy import create_engine
    from sqlmodel import Session, SQLModel
    from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus
    from app.models.payment import Payment
    from app.schemas.analytics import RevenueAnalytics

    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Organization(id='org', name='Gym', org_code='GYM-1', default_currency='USD'))
        for index, (org_id, currency, kind, amount, refund, status) in enumerate([
            ('org', 'USD', PaymentKind.MEMBER_FEE, 0.1, 0, PaymentStatus.SUCCEEDED),
            ('org', 'USD', PaymentKind.DAY_PASS, 0.2, 0, PaymentStatus.SUCCEEDED),
            ('org', 'USD', PaymentKind.MEMBER_FEE, 20, 5, PaymentStatus.PARTIALLY_REFUNDED),
            ('org', 'PKR', PaymentKind.MEMBER_FEE, 5000, 0, PaymentStatus.SUCCEEDED),
            ('other', 'USD', PaymentKind.MEMBER_FEE, 900, 0, PaymentStatus.SUCCEEDED),
            ('org', 'USD', PaymentKind.SAAS_SUBSCRIPTION, 100, 0, PaymentStatus.SUCCEEDED),
            ('org', 'USD', PaymentKind.TRAINER_PAYOUT, 200, 0, PaymentStatus.SUCCEEDED),
            ('org', 'USD', PaymentKind.MEMBER_FEE, 300, 0, PaymentStatus.FAILED),
            ('org', 'USD', PaymentKind.MEMBER_FEE, 10, 10, PaymentStatus.REFUNDED),
        ]):
            db.add(Payment(id=str(index), organization_id=org_id, currency=currency, kind=kind,
                           method=PaymentMethod.CASH, amount=amount, refunded_amount=refund,
                           status=status, paid_at=datetime(2026, 10, 1)))
        db.flush()

        class Facade:
            async def get(self, *args):
                return db.get(*args)

            async def execute(self, statement):
                return db.execute(statement)

        result = RevenueAnalytics.model_validate(await revenue_analytics(Facade(), org_id='org'))
        assert result.total_revenue == 15.30
        assert result.revenue_by_method == {'cash': 15.30}
        assert result.revenue_by_currency['USD'].total_revenue == '15.30'
        assert result.revenue_by_currency['PKR'].revenue_by_method == {'cash': '5000.00'}
    engine.dispose()
