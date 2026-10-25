from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.expenses import ExpenseCreate, ExpenseVoid


def test_expense_schema_normalizes_text_and_currency():
    expense = ExpenseCreate(
        category="utilities", description="  Power bill ", vendor="  Grid Co ",
        amount="123.40", currency="usd", incurred_on="2026-10-25",
    )

    assert expense.description == "Power bill"
    assert expense.vendor == "Grid Co"
    assert expense.amount == Decimal("123.40")
    assert expense.currency == "USD"


@pytest.mark.parametrize("amount", ["0", "-1", "1.001", "1000000000000"])
def test_expense_schema_rejects_invalid_money(amount):
    with pytest.raises(ValidationError):
        ExpenseCreate(
            category="rent", description="Gym rent", amount=amount,
            incurred_on="2026-10-25",
        )


def test_expense_schema_rejects_blank_description_and_bad_currency():
    with pytest.raises(ValidationError):
        ExpenseCreate(category="rent", description="   ", amount="1.00", incurred_on="2026-10-25")
    with pytest.raises(ValidationError):
        ExpenseCreate(category="rent", description="Rent", amount="1.00", currency="USDX", incurred_on="2026-10-25")


def test_expense_void_requires_reason():
    with pytest.raises(ValidationError):
        ExpenseVoid(reason="  ")
