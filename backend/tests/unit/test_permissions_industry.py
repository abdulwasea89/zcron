"""Per-industry capability overrides (Phase 0).

The gym industry has no override entry, so its matrix is byte-for-byte the base
matrix. Office/academy unlock vertical capabilities and may widen shared ones.
"""

from __future__ import annotations

import pytest

from app.core.constants import Role
from app.core.permissions import Capability, role_has


@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.MANAGER, Role.TRAINER, Role.FRONT_DESK, Role.MEMBER],
)
def test_gym_matches_base_matrix_for_every_role(role):
    # gym -> base matrix (no overrides) for both vertical and shared caps.
    assert role_has(role, Capability.MANAGE_MEMBERS, industry="gym") == (
        role in {Role.OWNER, Role.MANAGER}
    )
    assert role_has(role, Capability.VIEW_REVENUE_ANALYTICS, industry="gym") == (
        role in {Role.OWNER, Role.MANAGER}
    )
    assert role_has(role, Capability.MANAGE_EXPENSES, industry="gym") == (
        role in {Role.OWNER, Role.MANAGER}
    )


def test_vertical_capabilities_denied_for_gym():
    assert role_has(Role.MANAGER, Capability.MANAGE_COMPANIES, industry="gym") is False
    assert role_has(Role.MANAGER, Capability.MANAGE_COURSES, industry="gym") is False
    assert role_has(Role.MEMBER, Capability.BOOK_SPACE, industry="gym") is False
    assert role_has(Role.TRAINER, Capability.TAKE_ATTENDANCE, industry="gym") is False


def test_office_unlocks_companies_invoices_space_booking():
    for role in [Role.OWNER, Role.MANAGER]:
        assert role_has(role, Capability.MANAGE_COMPANIES, industry="office") is True
        assert role_has(role, Capability.ISSUE_INVOICES, industry="office") is True
    # Seat-holders (members) book space; front-desk cannot manage companies.
    assert role_has(Role.MEMBER, Capability.BOOK_SPACE, industry="office") is True
    assert role_has(Role.FRONT_DESK, Capability.MANAGE_COMPANIES, industry="office") is False
    assert role_has(Role.MEMBER, Capability.MANAGE_COMPANIES, industry="office") is False


def test_academy_unlocks_courses_enroll_attendance():
    for role in [Role.OWNER, Role.MANAGER]:
        assert role_has(role, Capability.MANAGE_COURSES, industry="academy") is True
        assert role_has(role, Capability.TAKE_ATTENDANCE, industry="academy") is True
    assert role_has(Role.TRAINER, Capability.TAKE_ATTENDANCE, industry="academy") is True
    assert role_has(Role.FRONT_DESK, Capability.ENROLL_STUDENTS, industry="academy") is True
    # Shared capability widened: registrar helps manage students.
    assert role_has(Role.FRONT_DESK, Capability.MANAGE_MEMBERS, industry="academy") is True
    # Vertical-only caps stay off for academy-role combos that shouldn't have them.
    assert role_has(Role.MEMBER, Capability.TAKE_ATTENDANCE, industry="academy") is False


def test_vertical_caps_do_not_leak_across_industries():
    # A vertical capability only exists where its industry override grants it.
    assert role_has(Role.MEMBER, Capability.BOOK_SPACE, industry="academy") is False
    assert role_has(Role.MEMBER, Capability.TAKE_ATTENDANCE, industry="office") is False
    assert role_has(Role.TRAINER, Capability.MANAGE_COURSES, industry="gym") is False


def test_base_grants_fall_through_in_verticals():
    # Shared base grants (BOOK_CLASSES, UPLOAD_RECEIPT) survive inside verticals.
    assert role_has(Role.MEMBER, Capability.BOOK_CLASSES, industry="academy") is True
    assert role_has(Role.MEMBER, Capability.BOOK_CLASSES, industry="office") is True
    assert role_has(Role.MEMBER, Capability.UPLOAD_RECEIPT, industry="office") is True


def test_shared_payroll_scope_unchanged():
    # Base grants still apply inside verticals unless overridden.
    assert role_has(Role.OWNER, Capability.RUN_PAYROLL, industry="office") is True
    assert role_has(Role.MANAGER, Capability.RUN_PAYROLL, industry="academy") is False


def test_no_industry_uses_base_matrix():
    assert role_has(Role.MEMBER, Capability.BOOK_CLASSES) is True
    assert role_has(Role.OWNER, Capability.RUN_PAYROLL) is True
    assert role_has(Role.FRONT_DESK, Capability.MANAGE_COMPANIES) is False
