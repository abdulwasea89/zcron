from datetime import timedelta

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.core.constants import IdempotencyStatus
from app.core.security import now_utc
from app.models.idempotency_key import IdempotencyKey
from app.workers.payment_reconciliation import reconcile_stuck


async def test_stale_payment_claims_are_reported_without_inventing_outcomes():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        older = now_utc() - timedelta(hours=1)
        records = [
            IdempotencyKey(key="cash", endpoint="cash.log", organization_id="gym", created_at=older),
            IdempotencyKey(key="card", endpoint="POST /memberships/pay", organization_id="gym", created_at=older),
            IdempotencyKey(key="other-work", endpoint="privacy.data_request.create", organization_id="gym", created_at=older),
            IdempotencyKey(key="other-gym", endpoint="cash.log", organization_id="other", created_at=older),
        ]
        db.add_all(records)
        db.flush()

        class SessionFacade:
            async def execute(self, statement):
                return db.execute(statement)

        result = await reconcile_stuck(SessionFacade(), org_id="gym")
        assert result == {"checked": 2, "resolved_succeeded": 0, "resolved_failed": 0, "unresolved": 2}
        assert all(record.status == IdempotencyStatus.IN_PROGRESS and record.response_body is None for record in records)
    engine.dispose()
