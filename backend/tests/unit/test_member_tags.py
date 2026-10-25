from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.routes import members
from app.models.membership import OrganizationMember
from app.schemas.members import MemberTagsUpdate


def test_tags_are_trimmed_normalized_and_deduplicated():
    assert MemberTagsUpdate(tags=[" Morning ", "morning", "FAMILY"]).tags == ["family", "morning"]
    assert MemberTagsUpdate(tags=[]).tags == []


@pytest.mark.parametrize("tags", [[""], ["  "], ["x" * 33], ["a\nb"], [str(i) for i in range(21)]])
def test_tags_reject_invalid_or_unbounded_values(tags):
    with pytest.raises(ValidationError):
        MemberTagsUpdate(tags=tags)


@pytest.mark.asyncio
async def test_member_tags_cannot_modify_another_tenant(monkeypatch):
    foreign = OrganizationMember(organization_id="other", user_id="member")

    async def get(*_args):
        return foreign

    with pytest.raises(HTTPException) as error:
        await members.update_member_tags(
            foreign.id, MemberTagsUpdate(tags=["family"]),
            ctx=SimpleNamespace(org_id="org", user_id="owner"),
            session=SimpleNamespace(get=get),
        )
    assert error.value.status_code == 404
    assert foreign.tags == []


@pytest.mark.asyncio
async def test_member_tag_changes_are_saved_and_audited(monkeypatch):
    member = OrganizationMember(organization_id="org", user_id="member")
    audits = []
    saved = []

    async def get(*_args):
        return member

    async def record(*_args, **kwargs):
        audits.append(kwargs)

    monkeypatch.setattr(members, "record_audit", record)
    session = SimpleNamespace(get=get, add=saved.append)
    ctx = SimpleNamespace(org_id="org", user_id="owner")
    result = await members.update_member_tags(member.id, MemberTagsUpdate(tags=["family"]), ctx, session)
    assert result.tags == member.tags == ["family"]
    assert saved == [member] and audits[0]["action"] == "member.tags_updated"
    await members.update_member_tags(member.id, MemberTagsUpdate(tags=["family"]), ctx, session)
    assert len(audits) == 1
