from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.models.payment import Payment
from app.services.payments_service import list_payments


@pytest.mark.asyncio
async def test_payment_cutoff_normalizes_utc_and_uses_created_date_only_without_paid_date():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class AsyncFacade:
                async def execute(self, statement):
                    return db.execute(statement)

            db.add_all([
                Payment(id="boundary", organization_id="gym", member_id="member", amount=10,
                        paid_at=datetime(2026, 1, 1, 5), created_at=datetime(2026, 1, 1, 6)),
                Payment(id="fallback", organization_id="gym", member_id="member", amount=10,
                        paid_at=None, created_at=datetime(2026, 1, 1, 6)),
                Payment(id="old-paid", organization_id="gym", member_id="member", amount=10,
                        paid_at=datetime(2026, 1, 1, 4), created_at=datetime(2026, 1, 1, 7)),
                Payment(id="foreign", organization_id="another", member_id="member", amount=10,
                        paid_at=datetime(2026, 1, 1, 6)),
                Payment(id="other-member", organization_id="gym", member_id="other", amount=10,
                        paid_at=datetime(2026, 1, 1, 6)),
            ])
            db.commit()
            rows = await list_payments(AsyncFacade(), org_id="gym", member_id="member",
                                       since=datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=5))))
            assert {row.id for row in rows} == {"boundary", "fallback"}
    finally:
        engine.dispose()
