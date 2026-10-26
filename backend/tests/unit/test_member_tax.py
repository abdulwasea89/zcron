from datetime import timedelta
from types import SimpleNamespace
import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.core.constants import TaxMode
from app.core.security import now_utc
from app.db.session import _upgrade_sqlite_late_migration_columns
from app.models.plan import MembershipPlan
from app.models.promotion import Promotion
from app.models.subscription import Subscription
from app.schemas.plans import PlanCreate, PlanUpdate
from app.services.pricing_service import quote_member_payment, tax_totals
from app.services.recurring_billing_service import _renewal_amount_cents
from app.utils.pdf import render_receipt_pdf


@pytest.mark.parametrize('mode,subtotal,rate,total,tax', [
    (TaxMode.INCLUSIVE, 11000, .10, 11000, 1000),
    (TaxMode.ADDED, 10000, .10, 11000, 1000),
    (TaxMode.INCLUSIVE, 9999, .20, 9999, 1667),
    (TaxMode.INCLUSIVE, 0, .20, 0, 0),
    (TaxMode.ADDED, 5, .10, 6, 1),
    (TaxMode.INCLUSIVE, 10000, 0, 10000, 0),
])
def test_tax_totals_keep_inclusive_tax_inside_price(mode, subtotal, rate, total, tax):
    assert tax_totals(subtotal, rate, mode) == (total, tax)


@pytest.mark.parametrize('rate', [-.1, 1.1, float('nan'), float('inf')])
def test_invalid_rates_are_rejected_by_api_and_legacy_calculations(rate):
    for schema in (PlanCreate, PlanUpdate):
        with pytest.raises(ValidationError):
            schema(name='Gym plan', tax_rate=rate)
    with pytest.raises(HTTPException) as error:
        tax_totals(1000, rate, TaxMode.INCLUSIVE)
    assert error.value.status_code == 422


@pytest.mark.parametrize('field', ['price', 'joining_fee'])
def test_plan_money_must_be_finite(field):
    with pytest.raises(ValidationError):
        PlanCreate(name='Plan', **{field: float('inf')})


@pytest.mark.parametrize('field', ['price', 'joining_fee', 'tax_mode', 'tax_rate'])
def test_patch_cannot_clear_required_pricing_but_can_omit_it(field):
    assert field not in PlanUpdate(name='Renamed').model_dump(exclude_unset=True)
    with pytest.raises(ValidationError):
        PlanUpdate(**{field: None})


@pytest.mark.parametrize('mode,total', [(TaxMode.INCLUSIVE, 99), (TaxMode.ADDED, 108.90)])
async def test_quote_discounts_joining_fees_and_inclusive_tax_use_one_breakdown(mode, total):
    plan = MembershipPlan(id='plan', organization_id='gym', name='Plan', price=110,
                          joining_fee=11, tax_mode=mode, tax_rate=.10)
    promo = Promotion(organization_id='gym', code='SAVE20', discount_type='percent', discount_value=20)
    class Session:
        def __init__(self):
            self.calls = 0

        async def execute(self, statement):
            self.calls += 1
            return SimpleNamespace(first=lambda: None, scalar_one_or_none=lambda: promo)
    quote = await quote_member_payment(Session(), org_id='gym', member_id='member', plan=plan, promo_code='SAVE20')
    assert quote.total == total
    assert quote.tax_included == (mode == TaxMode.INCLUSIVE)
    assert quote.tax_amount == (9 if mode == TaxMode.INCLUSIVE else 9.90)
    assert quote.joining_fee == 11 and quote.discount_amount == 22


def test_renewal_preserves_snapshot_price_and_discount_with_tax():
    sub = Subscription(organization_id='gym', member_id='member', plan_id='plan', price_snapshot=110,
                       save_discount_percent=10, save_discount_expires_at=now_utc() + timedelta(days=1))
    plan = MembershipPlan(organization_id='gym', name='Changed price', price=999, tax_rate=.10)
    assert _renewal_amount_cents(sub, plan) == (9900, 900)
    plan.tax_mode = TaxMode.ADDED
    assert _renewal_amount_cents(sub, plan) == (10890, 990)


def test_receipt_labels_tax_as_included_without_changing_total():
    pdf = render_receipt_pdf(gym_name='Gym', gym_address=None, receipt_no='123', paid_at='today',
        member_name='Member', member_email='m@example.com', plan_name='Plan', amount=110,
        currency='USD', method='Cash', logged_by='Owner', plan_price=110, tax=10, tax_included=True)
    assert b'Tax \\(included\\)' in pdf
    assert b'110.00' in pdf


def test_tax_snapshot_migration_preserves_existing_payments():
    migration = importlib.import_module('app.db.migrations.versions.k3f4g5h6i7j8_payment_tax_included')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE payments (id VARCHAR PRIMARY KEY, tax_amount FLOAT)')
        connection.exec_driver_sql("INSERT INTO payments (id,tax_amount) VALUES ('old',12.5)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.exec_driver_sql('SELECT tax_included, tax_amount FROM payments').one() == (0, 12.5)
        _upgrade_sqlite_late_migration_columns(connection)
        _upgrade_sqlite_late_migration_columns(connection)
    engine.dispose()
