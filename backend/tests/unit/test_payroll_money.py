from decimal import Decimal

from app.workers.payroll_runner import _money


def test_payroll_money_rounds_decimal_half_up_to_currency_cents():
    assert _money(Decimal("0.10") * Decimal("0.15")) == Decimal("0.02")
    assert _money(Decimal("1.004")) == Decimal("1.00")
    assert _money(Decimal("1.005")) == Decimal("1.01")
