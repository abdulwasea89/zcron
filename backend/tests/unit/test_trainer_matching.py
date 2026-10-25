from datetime import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.core.constants import Role
from app.models.member_trainer import MemberTrainer
from app.models.membership import OrganizationMember
from app.models.trainer_availability import TrainerAvailability
from app.models.user import User
from app.services import member_trainers_service as trainers


@pytest.mark.asyncio
async def test_shortlist_matches_whole_window_ranks_load_and_excludes_unavailable_trainers():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            class AsyncFacade:
                async def get(self, *args, **kwargs):
                    return db.get(*args, **kwargs)

                async def execute(self, statement):
                    return db.execute(statement)

            session = AsyncFacade()
            db.add(OrganizationMember(id="member", organization_id="gym", user_id="member-user", role=Role.MEMBER))
            for key in ("free", "busy", "short", "foreign", "banned", "disabled", "wrongday"):
                org = "other" if key == "foreign" else "gym"
                db.add(User(id=f"user-{key}", email=f"{key}@test.com", full_name=key,
                            hashed_password="unused", is_active=key != "disabled"))
                db.add(OrganizationMember(id=key, organization_id=org, user_id=f"user-{key}",
                                          role=Role.TRAINER, banned=key == "banned"))
                db.add(TrainerAvailability(organization_id=org, trainer_member_id=key,
                                           weekday=1 if key == "wrongday" else 0,
                                           start_time=time(8), end_time=time(9) if key == "short" else time(12)))
            db.add_all([
                MemberTrainer(organization_id="gym", member_id="member", trainer_member_id="busy"),
                MemberTrainer(organization_id="gym", member_id="another", trainer_member_id="busy"),
                MemberTrainer(organization_id="other", member_id="elsewhere", trainer_member_id="free"),
                TrainerAvailability(organization_id="gym", trainer_member_id="free", weekday=0,
                                    start_time=time(7), end_time=time(11)),
            ])
            db.commit()
            matches = await trainers.matching_trainers(session, org_id="gym", member_id="member",
                                                        weekday=0, start_time=time(9), end_time=time(10))
            assert [match["trainer_member_id"] for match in matches] == ["free", "busy"]
            assert [match["assigned_clients"] for match in matches] == [0, 2]
            assert [match["already_assigned"] for match in matches] == [False, True]
            with pytest.raises(HTTPException) as error:
                await trainers.matching_trainers(session, org_id="other", member_id="member",
                                                 weekday=0, start_time=time(9), end_time=time(10))
            assert error.value.status_code == 404
            for key in ("banned", "disabled"):
                with pytest.raises(HTTPException) as error:
                    await trainers.assign(session, org_id="gym", member_id="member",
                                           trainer_member_id=key, actor_user_id="owner")
                assert error.value.status_code == 422
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_invalid_weekly_window_is_rejected_before_query():
    member = OrganizationMember(id="member", organization_id="gym", user_id="user", role=Role.MEMBER)

    async def get(*_args, **_kwargs):
        return member

    with pytest.raises(HTTPException) as error:
        await trainers.matching_trainers(SimpleNamespace(get=get), org_id="gym", member_id="member",
                                         weekday=0, start_time=time(10), end_time=time(9))
    assert error.value.status_code == 422
