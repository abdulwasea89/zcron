from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1.routes.staff import staff_performance
from app.core.constants import Role
from app.core.tenancy import TenantContext


@pytest.mark.asyncio
async def test_staff_performance_aggregates_only_recorded_activity():
    result_rows = iter([
        [("user-1", "Coach", "coach@example.com")],
        [("user-1", "task.completed", 2), ("user-1", "lead.first_contact_logged", 3)],
        [("user-1", 7.5)],
        [("user-1", "USD", Decimal("120.50"))],
    ])

    class Session:
        async def execute(self, _statement):
            return SimpleNamespace(all=lambda: next(result_rows))

    report = await staff_performance(
        days=30, ctx=TenantContext(user_id="owner", org_id="gym", role=Role.OWNER), session=Session(),
    )

    assert report == {
        "days": 30,
        "staff": [{
            "user_id": "user-1", "name": "Coach", "completed_tasks": 2,
            "lead_responses": 3, "shift_hours": 7.5, "cash_by_currency": {"USD": "120.50"},
        }],
    }
