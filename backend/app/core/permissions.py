"""Role capability matrix and permission checks (Section 2 of the plan).

The matrix is the single source of truth for "who can do what". Route handlers
call ``require_capability`` (via a dependency) instead of hard-coding role lists.
"""

from __future__ import annotations

from enum import Enum

from app.core.constants import Role
from app.core.industry import IndustryKind, normalize_industry


class Capability(str, Enum):
    REGISTER_GYM = "register_gym"
    CREATE_EDIT_PLANS = "create_edit_plans"
    ARCHIVE_PLANS = "archive_plans"
    APPROVE_CASH_RECEIPTS = "approve_cash_receipts"
    PROCESS_REFUNDS = "process_refunds"
    INVITE_MEMBERS = "invite_members"
    RUN_PAYROLL = "run_payroll"
    TOGGLE_GYM_STATUS = "toggle_gym_status"
    ASSIGN_TASKS = "assign_tasks"
    LOG_CASH_PAYMENT = "log_cash_payment"
    UPLOAD_RECEIPT = "upload_receipt"
    BOOK_CLASSES = "book_classes"
    CHECK_IN_SHIFT = "check_in_shift"
    VIEW_REVENUE_ANALYTICS = "view_revenue_analytics"
    MANAGE_EXPENSES = "manage_expenses"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_MEMBERS = "manage_members"
    ASSIGN_TRAINERS = "assign_trainers"
    VIEW_ASSIGNED_MEMBERS = "view_assigned_members"
    VIEW_AUDIT_LOG = "view_audit_log"
    VIEW_PLANS = "view_plans"
    USE_ASSISTANT = "use_assistant"          # AI assistant over org data

    # ---- Multi-industry capabilities (office/academy, Phase 0) ----
    MANAGE_COMPANIES = "manage_companies"    # office: tenant companies & contracts
    ISSUE_INVOICES = "issue_invoices"        # office: draft/send/settle invoices
    MANAGE_COURSES = "manage_courses"        # academy: courses & batches
    ENROLL_STUDENTS = "enroll_students"      # academy: register students into batches
    TAKE_ATTENDANCE = "take_attendance"      # gym: log member visits; academy: per-lesson attendance
    BOOK_SPACE = "book_space"                # office: book desks/meeting rooms

    # ---- Shared team inbox (Section 1.3, #20) ----
    VIEW_INBOX = "view_inbox"                # read the shared conversation inbox
    MANAGE_INBOX = "manage_inbox"            # reply, assign, change status
    MANAGE_VISITORS = "manage_visitors"      # walk-ins, day passes, guest log, lockers

    # ---- Retention / churn (#33, #34) ----
    VIEW_RETENTION = "view_retention"        # attendance-drop + churn-risk roster

    # ---- Marketing (#39) ----
    RUN_CAMPAIGNS = "run_campaigns"          # compose and send segmented campaigns


# Capability -> set of roles allowed. Mirrors the Section 2 table.
_MATRIX: dict[Capability, set[Role]] = {
    Capability.REGISTER_GYM: {Role.OWNER},
    Capability.CREATE_EDIT_PLANS: {Role.OWNER, Role.MANAGER},
    Capability.ARCHIVE_PLANS: {Role.OWNER, Role.MANAGER},  # manager = confirm only
    Capability.APPROVE_CASH_RECEIPTS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.PROCESS_REFUNDS: {Role.OWNER, Role.MANAGER},  # manager limited
    Capability.INVITE_MEMBERS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.RUN_PAYROLL: {Role.OWNER},
    Capability.TOGGLE_GYM_STATUS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.ASSIGN_TASKS: {Role.OWNER, Role.MANAGER, Role.TRAINER},  # trainer=self
    Capability.LOG_CASH_PAYMENT: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.TAKE_ATTENDANCE: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.UPLOAD_RECEIPT: {Role.MEMBER},
    Capability.BOOK_CLASSES: {Role.MEMBER},
    Capability.CHECK_IN_SHIFT: {Role.TRAINER, Role.FRONT_DESK, Role.MANAGER},
    Capability.VIEW_REVENUE_ANALYTICS: {Role.OWNER, Role.MANAGER},
    Capability.MANAGE_EXPENSES: {Role.OWNER, Role.MANAGER},
    Capability.MANAGE_SETTINGS: {Role.OWNER},
    Capability.MANAGE_MEMBERS: {Role.OWNER, Role.MANAGER},
    Capability.ASSIGN_TRAINERS: {Role.OWNER, Role.MANAGER},
    Capability.VIEW_ASSIGNED_MEMBERS: {Role.OWNER, Role.MANAGER, Role.TRAINER},
    Capability.VIEW_AUDIT_LOG: {Role.OWNER, Role.MANAGER},
    Capability.VIEW_PLANS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    # The assistant sees revenue, payroll-adjacent metrics and member counts, so
    # it stays with the roles that can already read analytics.
    Capability.USE_ASSISTANT: {Role.OWNER, Role.MANAGER},
    Capability.VIEW_INBOX: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.MANAGE_INBOX: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.MANAGE_VISITORS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    Capability.VIEW_RETENTION: {Role.OWNER, Role.MANAGER},
    Capability.RUN_CAMPAIGNS: {Role.OWNER, Role.MANAGER},
}

# Per-industry deltas over the base matrix (multi-industry Phase 0). The gym
# industry has no entry: gym behavior is exactly the base matrix. Office/academy
# extend shared capabilities and add their vertical-only ones.
_INDUSTRY_MATRIX: dict[IndustryKind, dict[Capability, set[Role]]] = {
    IndustryKind.OFFICE: {
        Capability.MANAGE_COMPANIES: {Role.OWNER, Role.MANAGER},
        Capability.ISSUE_INVOICES: {Role.OWNER, Role.MANAGER},
        Capability.BOOK_SPACE: {Role.MEMBER},
        Capability.MANAGE_MEMBERS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
        Capability.VIEW_PLANS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    },
    IndustryKind.ACADEMY: {
        Capability.MANAGE_COURSES: {Role.OWNER, Role.MANAGER},
        Capability.ENROLL_STUDENTS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
        Capability.TAKE_ATTENDANCE: {Role.OWNER, Role.MANAGER, Role.TRAINER},
        Capability.MANAGE_MEMBERS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
        Capability.VIEW_PLANS: {Role.OWNER, Role.MANAGER, Role.FRONT_DESK},
    },
}


def role_has(role: Role, capability: Capability, industry: str | IndustryKind | None = None) -> bool:
    """Whether ``role`` holds ``capability``.

    When ``industry`` is supplied the vertical's capability overrides apply on
    top of the shared base matrix (office/academy). Without industry (or for
    ``gym``) this is exactly the classic gym matrix.
    """

    if industry is not None:
        try:
            overrides = _INDUSTRY_MATRIX.get(normalize_industry(industry), {})
            if capability in overrides:
                return role in overrides[capability]
        except (KeyError, ValueError):
            pass  # unknown industry -> fall back to the base matrix
    return role in _MATRIX.get(capability, set())
