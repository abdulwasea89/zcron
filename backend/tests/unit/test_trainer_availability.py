from datetime import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes.staff import create_trainer_availability
from app.core.constants import Role
from app.schemas.staff import TrainerAvailabilityCreate


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class Session:
    def __init__(self, overlap=None):
        self.overlap = overlap
        self.added = []

    async def get(self, _model, _key):
        return SimpleNamespace(
            id="trainer-id", organization_id="org", role=Role.TRAINER, banned=False,
        )

    async def execute(self, _query):
        return Result(self.overlap)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_trainer_availability_rejects_overlap(monkeypatch):
    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.api.v1.routes.staff.record_audit", no_op)
    data = TrainerAvailabilityCreate(
        trainer_member_id="trainer-id", weekday=0,
        start_time=time(9), end_time=time(12),
    )
    context = SimpleNamespace(org_id="org", user_id="owner", role=Role.OWNER)

    saved_session = Session()
    saved = await create_trainer_availability(data, ctx=context, session=saved_session)
    assert saved.trainer_member_id == "trainer-id"
    assert len(saved_session.added) == 1

    with pytest.raises(HTTPException) as error:
        await create_trainer_availability(data, ctx=context, session=Session(overlap="existing"))
    assert error.value.status_code == 409
