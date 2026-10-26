from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.api.v1.routes.receipts import review_queue
from app.core.constants import ReceiptStatus, Role
from app.models.membership import OrganizationMember
from app.models.receipt import ReceiptUpload
from app.models.user import User


@pytest.mark.asyncio
async def test_review_queue_supplies_names_without_private_directory_or_cross_tenant_data():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class AsyncFacade:
                async def execute(self, statement):
                    return db.execute(statement)

            db.add_all([
                User(id="user", email="member@test.com", full_name="Member Name", hashed_password="not-used"),
                User(id="foreign-user", email="foreign@test.com", full_name="Foreign Private Name", hashed_password="not-used"),
                OrganizationMember(id="member", organization_id="gym", user_id="user", display_name="Gym Name",
                                   health_notes="PRIVATE HEALTH", fixed_monthly_salary="123456.78"),
                OrganizationMember(id="foreign-member", organization_id="other", user_id="foreign-user"),
                ReceiptUpload(id="receipt", organization_id="gym", member_id="member", status=ReceiptStatus.PENDING_REVIEW),
                ReceiptUpload(id="foreign", organization_id="other", member_id="foreign-member", status=ReceiptStatus.PENDING_REVIEW),
                ReceiptUpload(id="invalid-link", organization_id="gym", member_id="foreign-member", status=ReceiptStatus.PENDING_REVIEW),
            ])
            db.commit()
            rows = await review_queue(ctx=SimpleNamespace(org_id="gym", role=Role.FRONT_DESK), session=AsyncFacade())
            assert {row.id for row in rows} == {"receipt", "invalid-link"}
            assert next(row for row in rows if row.id == "receipt").member_name == "Gym Name"
            assert next(row for row in rows if row.id == "invalid-link").member_name is None
            serialized = " ".join(row.model_dump_json() for row in rows)
            assert "PRIVATE HEALTH" not in serialized and "123456.78" not in serialized
            assert "Foreign Private Name" not in serialized
    finally:
        engine.dispose()
