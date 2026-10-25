from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.routes.data_subject_requests import export_member_data
from app.core.constants import Role


@pytest.mark.asyncio
async def test_front_desk_is_denied_member_data_export_before_database_access():
    request = SimpleNamespace(headers={})
    context = SimpleNamespace(role=Role.FRONT_DESK)

    with pytest.raises(HTTPException) as error:
        await export_member_data("member-id", request, ctx=context, session=object())

    assert error.value.status_code == 403
