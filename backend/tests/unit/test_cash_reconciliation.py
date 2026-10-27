from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.core.constants import PaymentMethod, PaymentStatus
from app.db.session import _upgrade_sqlite_late_migration_columns
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund
from app.schemas.cash import ReconciliationRequest
from app.services import cash_service


class AsyncFacade:
    def __init__(self, session):
        self.session = session

    async def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    def add(self, row):
        self.session.add(row)


async def test_cash_total_uses_local_day_currency_and_dated_refunds(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(cash_service, "record_audit", AsyncMock())
    with Session(engine) as db:
        db.add(Organization(id="gym", name="Gym", org_code="GYM", timezone="America/New_York", default_currency="USD"))
        def payment(key, org, amount, currency, paid, status=PaymentStatus.SUCCEEDED, **kwargs):
            return Payment(id=key, organization_id=org, method=PaymentMethod.CASH,
                           amount=amount, currency=currency, paid_at=paid, status=status, **kwargs)
        db.add_all([
            payment("in", "gym", 100, "USD", datetime(2026, 3, 8, 5), PaymentStatus.PARTIALLY_REFUNDED),
            payment("before", "gym", 25, "USD", datetime(2026, 3, 8, 4, 59)),
            payment("end", "gym", 20, "USD", datetime(2026, 3, 9, 4)),
            payment("euro", "gym", 900, "EUR", datetime(2026, 3, 8, 6)),
            payment("foreign", "other", 500, "USD", datetime(2026, 3, 8, 6)),
            payment("old", "gym", 50, "USD", datetime(2026, 3, 7, 6), PaymentStatus.REFUNDED),
            payment("legacy", "gym", 30, "USD", datetime(2026, 3, 7, 6), PaymentStatus.PARTIALLY_REFUNDED,
                    refunded_amount=7, refunded_at=datetime(2026, 3, 8, 7)),
        ])
        db.add_all([
            PaymentRefund(organization_id="gym", payment_id="in", currency="USD", amount=Decimal("15.00"), occurred_at=datetime(2026, 3, 8, 7), source="admin"),
            PaymentRefund(organization_id="gym", payment_id="old", currency="USD", amount=Decimal("10.00"), occurred_at=datetime(2026, 3, 8, 8), source="admin"),
        ])
        db.flush()
        session = AsyncFacade(db)
        assert await cash_service._system_cash_total(session, org_id="gym", business_date=date(2026, 3, 8)) == 68
        assert await cash_service._system_cash_total(session, org_id="gym", business_date=date(2026, 3, 8), currency="EUR") == 900
        reconciliation, _ = await cash_service.reconcile(
            session, org_id="gym", business_date=date(2026, 3, 8), counted_total=100,
            opening_float=32, performed_by="staff", notes=None,
        )
        assert (reconciliation.currency, reconciliation.system_total, reconciliation.discrepancy) == ("USD", 68, 0)
    engine.dispose()


async def test_one_cent_difference_is_audited_as_discrepancy(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    audit = AsyncMock()
    monkeypatch.setattr(cash_service, "record_audit", audit)
    monkeypatch.setattr(cash_service, "_maybe_alert_owner", AsyncMock(return_value=False))
    with Session(engine) as db:
        db.add(Organization(id="gym", name="Gym", org_code="GYM"))
        db.flush()
        result, _ = await cash_service.reconcile(AsyncFacade(db), org_id="gym", business_date=date(2026, 3, 8),
                                                 counted_total=0.01, performed_by="staff", notes=None)
        assert result.discrepancy == 0.01
        assert audit.await_args.kwargs["action"] == "cash.reconciliation_discrepancy"
    engine.dispose()


def test_currency_is_normalized_and_validated():
    assert ReconciliationRequest(business_date=date(2026, 3, 8), counted_total=0, currency=" pkr ").currency == "PKR"
    with pytest.raises(ValidationError):
        ReconciliationRequest(business_date=date(2026, 3, 8), counted_total=0, currency="US$ ")


@pytest.mark.parametrize("count", [-1, float("inf"), float("nan"), 1.001])
@pytest.mark.parametrize("field", ["counted_total", "opening_float"])
def test_invalid_cash_counts_are_rejected(count, field):
    with pytest.raises(ValidationError):
        ReconciliationRequest(business_date=date(2026, 3, 8), **{field: count, **({} if field == "counted_total" else {"counted_total": 10})})


def test_currency_migration_preserves_old_reconciliations(monkeypatch):
    migration = import_module("app.db.migrations.versions.c2d3e4f5a6b7_cash_reconciliation_currency")
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE cash_reconciliations (id VARCHAR PRIMARY KEY, system_total FLOAT)")
        connection.exec_driver_sql("INSERT INTO cash_reconciliations VALUES ('old', 42.0)")
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert connection.exec_driver_sql("SELECT system_total, currency, opening_float FROM cash_reconciliations").one() == (42.0, None, 0)
        _upgrade_sqlite_late_migration_columns(connection)
    engine.dispose()
