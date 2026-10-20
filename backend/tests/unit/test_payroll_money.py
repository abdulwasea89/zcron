from decimal import Decimal

from app.schemas.payroll import PayrollRunOut
from app.workers.payroll_runner import _money


def test_payroll_money_rounds_decimal_half_up_to_currency_cents():
    assert _money(Decimal("0.10") * Decimal("0.15")) == Decimal("0.02")
    assert _money(Decimal("1.004")) == Decimal("1.00")
    assert _money(Decimal("1.005")) == Decimal("1.01")


def test_payroll_api_keeps_money_fields_as_json_numbers():
    run = PayrollRunOut(
        id="run",
        period_start="2026-01-01",
        period_end="2026-01-31",
        status="draft",
        total_gross=Decimal("1500.10"),
        total_deductions=Decimal("0.00"),
        total_net=Decimal("1500.10"),
    )

    assert run.model_dump(mode="json")["total_net"] == 1500.1
