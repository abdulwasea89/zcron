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
