"""Shared enums and domain constants used across models, schemas, and services.

These encode the vocabulary of the product plan: roles, statuses, billing types,
payment methods, etc. Keeping them in one place keeps the API contract and the
database in agreement.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """Tenant-scoped role of a user within one organization (Section 2)."""

    OWNER = "owner"
    MANAGER = "manager"
    TRAINER = "trainer"
    FRONT_DESK = "front_desk"
    MEMBER = "member"


# Roles considered "staff/admin" for capability checks.
STAFF_ROLES = {Role.OWNER, Role.MANAGER, Role.TRAINER, Role.FRONT_DESK}
ADMIN_ROLES = {Role.OWNER, Role.MANAGER}


class Gender(str, Enum):
    """Owner-provided gender at registration (Section 4.2)."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class SaasTier(str, Enum):
    """Platform subscription tier the gym owner pays for (Section 3.1)."""

    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SaasStatus(str, Enum):
    """Lifecycle state of the org's SaaS subscription (Section 3.2.4)."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"  # failed charge, retries in progress
    READ_ONLY = "read_only"  # grace ended (day 6)
    SUSPENDED = "suspended"  # day 30, members locked out
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class EnrollmentMode(str, Enum):
    """How members may join the org (Section 7.1)."""

    OPEN = "open"
    APPROVED = "approved"
    INVITE_ONLY = "invite_only"


class ConnectStatus(str, Enum):
    """Stripe Connect onboarding state for receiving member payments."""

    NONE = "none"
    PENDING = "pending"
    ACTIVE = "active"
    RESTRICTED = "restricted"


class MemberStatus(str, Enum):
    """Membership status of a member within an org (Section 9.3)."""

    PENDING_PAYMENT = "pending_payment"
    PENDING_APPROVAL = "pending_approval"
    PENDING_ACTIVATION = "pending_activation"  # CSV-imported, not yet claimed
    ACTIVE = "active"
    GRACE = "grace"
    EXPIRED = "expired"
    FROZEN = "frozen"
    CANCELLED = "cancelled"
    BANNED = "banned"


class PlanBillingType(str, Enum):
    """Membership plan billing model (Section 6.3)."""

    RECURRING = "recurring"
    ONE_TIME_PACK = "one_time_pack"
    DROP_IN = "drop_in"


class PlanVisibility(str, Enum):
    """Who can see/select a plan (Section 6.6)."""

    PUBLIC = "public"
    MEMBERS_ONLY = "members_only"
    INVITE_ONLY = "invite_only"


class PlanStatus(str, Enum):
    """Lifecycle of a membership plan (Section 6.7)."""

    DRAFT = "draft"
    PUBLISHED = "published"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TaxMode(str, Enum):
    INCLUSIVE = "inclusive"
    ADDED = "added"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    GRACE = "grace"
    EXPIRED = "expired"
    FROZEN = "frozen"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    CARD = "card"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    MOBILE_WALLET = "mobile_wallet"
    INVOICE = "invoice"  # office B2B: settled company invoice (no Stripe intent)


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentKind(str, Enum):
    """What the payment is for."""

    SAAS_SUBSCRIPTION = "saas_subscription"  # owner -> platform
    MEMBER_FEE = "member_fee"  # member -> gym (Connect)
    TRAINER_PAYOUT = "trainer_payout"  # gym -> trainer
    SPACE = "space"  # office: company -> space provider
    TUITION = "tuition"  # academy: guardian -> academy
    DAY_PASS = "day_pass"  # walk-in -> gym (front desk, #22)


class IdempotencyStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ReceiptStatus(str, Enum):
    """AI receipt pipeline outcome (Section 10)."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    AUTO_APPROVED = "auto_approved"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"  # admin-approved
    REJECTED = "rejected"
    REVERSED = "reversed"  # auto-approval reversed on audit


class PayrollStatus(str, Enum):
    DRAFT = "draft"
    LOCKED = "locked"
    FINALIZED = "finalized"
    PAID = "paid"


class PayoutMethod(str, Enum):
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    MOBILE_WALLET = "mobile_wallet"


class AdvanceStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REPAID = "repaid"


class ShiftStatus(str, Enum):
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"


class GymStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    HALF_DAY = "half_day"


class BookingStatus(str, Enum):
    BOOKED = "booked"
    ATTENDED = "attended"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    WAITLISTED = "waitlisted"


class AttendanceMethod(str, Enum):
    """How a member's gym visit was captured (Section 1.3)."""

    MANUAL = "manual"  # staff searched the member and logged it
    QR = "qr"  # scanned the member's QR code
    APP = "app"  # member self-check-in from the app
    CARD = "card"  # card / RFID
    BIOMETRIC = "biometric"


class AttendanceSource(str, Enum):
    """Who or what created the visit row."""

    FRONT_DESK = "front_desk"  # staff logged it
    SELF = "self"  # member checked themselves in
    CLASS = "class"  # attendance recorded from a class booking
    SYSTEM = "system"  # automated / integration


class Channel(str, Enum):
    """A messaging channel a member can reach the gym on (Section 1.3, #20)."""

    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    INSTAGRAM = "instagram"
    MESSENGER = "messenger"
    LINE = "line"
    WECHAT = "wechat"
    TELEGRAM = "telegram"
    WEB_CHAT = "web_chat"
    PHONE = "phone"
    WALK_IN = "walk_in"
    OTHER = "other"


class LeadSource(str, Enum):
    """How a prospect entered the sales pipeline."""

    STAFF_ENTERED = "staff_entered"
    WEB_FORM = "web_form"
    PHONE = "phone"
    WALK_IN = "walk_in"
    REFERRAL = "referral"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    LINE = "line"
    WECHAT = "wechat"
    OTHER = "other"


class ConversationStatus(str, Enum):
    """Shared-inbox thread state."""

    OPEN = "open"
    PENDING = "pending"  # waiting on the customer
    SNOOZED = "snoozed"
    RESOLVED = "resolved"


class MessageDirection(str, Enum):
    INBOUND = "inbound"  # customer -> gym
    OUTBOUND = "outbound"  # gym -> customer


class SenderKind(str, Enum):
    """Who authored an inbox message."""

    CONTACT = "contact"  # the customer
    STAFF = "staff"  # a team member
    AI = "ai"  # an AI-drafted reply
    SYSTEM = "system"  # automation / delivery notices


class VisitorKind(str, Enum):
    """Why a non-member is at the desk (Section 1.3, #22)."""

    DAY_PASS = "day_pass"
    GUEST = "guest"  # guest of a member
    TRIAL = "trial"
    WALK_IN = "walk_in"
    OTHER = "other"


class LockerStatus(str, Enum):
    FREE = "free"
    OCCUPIED = "occupied"


class VerificationPurpose(str, Enum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"
    MAGIC_LINK = "magic_link"
    MEMBER_INVITE = "member_invite"
    MEMBER_ACTIVATION = "member_activation"


class NotificationKind(str, Enum):
    """In-app alert category (per-user notifications feed)."""

    APPROVAL = "approval"  # signup/application awaiting decision
    RECEIPT = "receipt"  # receipt pipeline outcome (member)
    RECEIPT_REVIEW = "receipt_review"  # receipt awaiting admin review (owner/staff)
    PAYMENT = "payment"  # payment recorded / refund
    TASK = "task"  # task assigned
    MEMBERSHIP = "membership"  # membership expiry / grace / activation
    CASH = "cash"  # reconciliation / discrepancy alerts
    ONBOARDING = "onboarding"  # 90-day new-member journey (#32)
    CELEBRATION = "celebration"  # birthday / anniversary / milestone (#36)
    WINBACK = "win_back"  # lapsed-member win-back (#36)
    NPS = "nps"  # day-7/30/90 Net Promoter surveys (#37)
    CHALLENGE = "challenge"  # challenge completion (#38)
    STREAK = "streak"  # visit-streak milestone (#38)
    CAMPAIGN = "campaign"  # segmented marketing campaign (#39)
    SYSTEM = "system"  # platform / misc


class OnboardingStatus(str, Enum):
    """Lifecycle of a member's 90-day onboarding journey (#32)."""

    ACTIVE = "active"  # journey running
    PAUSED = "paused"  # member frozen / admin paused
    COMPLETED = "completed"  # reached day 90
    OPTED_OUT = "opted_out"  # cancelled membership mid-journey


class MilestoneStatus(str, Enum):
    """Per-member state of one onboarding milestone."""

    PENDING = "pending"  # surfaced to the member/staff, not yet done
    COMPLETED = "completed"  # member or staff closed it
    SKIPPED = "skipped"  # member skipped it


class LadderStatus(str, Enum):
    """Per-member state of one inactivity-ladder rung (#35)."""

    FIRED = "fired"  # the intervention was dispatched
    COMPLETED = "completed"  # staff closed the follow-up
    SKIPPED = "skipped"  # staff dismissed it


class CelebrationKind(str, Enum):
    """A loyalty moment we acknowledge for a member (#36)."""

    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    VISITS = "visits"


class WinBackStatus(str, Enum):
    """State of one win-back outreach to a lapsed member (#36)."""

    CONTACTED = "contacted"  # offer sent, awaiting response
    RECOVERED = "recovered"  # member reactivated
    LOST = "lost"  # gave up / manually closed


class NpsMilestone(str, Enum):
    """An NPS touchpoint during the first 90 days of membership (#37)."""

    DAY_7 = "day_7"
    DAY_30 = "day_30"
    DAY_90 = "day_90"


class NpsStatus(str, Enum):
    """Lifecycle of one NPS survey (#37)."""

    SENT = "sent"  # delivered, awaiting the member's response
    RESPONDED = "responded"  # member answered (score + optional comment)
    SKIPPED = "skipped"  # never delivered (backfill/off-window/non-active)


class ChallengeGoalType(str, Enum):
    """What a challenge counts toward (#38)."""

    VISITS = "visits"  # any check-in within the challenge window
    CLASSES = "classes"  # class check-ins only
    STREAK = "streak"  # consecutive active-day streak >= target


class ChallengeStatus(str, Enum):
    """Lifecycle of an org-defined challenge (#38)."""

    DRAFT = "draft"  # created, not yet visible to members
    PUBLISHED = "published"  # live; progress counts toward it
    PAUSED = "paused"  # hidden temporarily; progress frozen
    COMPLETED = "completed"  # window elapsed / target met
    ARCHIVED = "archived"  # old, hidden


class ChallengeProgressStatus(str, Enum):
    """Per-member state inside one challenge (#38)."""

    ACTIVE = "active"  # running, not yet completed
    COMPLETED = "completed"  # goal reached (fires once)


class CampaignChannel(str, Enum):
    """Outbound channel for a segmented campaign (#39)."""

    IN_APP = "in_app"  # in-app notification only
    EMAIL = "email"  # email only
    BOTH = "both"  # in-app notification + email


class CampaignStatus(str, Enum):
    """Lifecycle of an org-defined campaign (#39)."""

    DRAFT = "draft"  # composed, not yet sent
    SCHEDULED = "scheduled"  # scheduled_at set, awaiting worker
    SENDING = "sending"  # worker is fanning out (idempotent, resumable)
    SENT = "sent"  # finished; delivery rows hold per-member outcome
    CANCELLED = "cancelled"  # stopped before going out


class CampaignDeliveryStatus(str, Enum):
    """Per-member outcome of one campaign (#39)."""

    PENDING = "pending"  # queued but not yet delivered
    SENT = "sent"  # notification/email accepted
    FAILED = "failed"  # delivery error (logged, campaign continues)
    SUPPRESSED = "suppressed"  # skipped: no email opt-in / already delivered


# SaaS tier -> member cap (None = unlimited). Mirrors Section 3.1.
TIER_MEMBER_CAP: dict[SaasTier, int | None] = {
    SaasTier.STARTER: 25,
    SaasTier.PRO: 100,
    SaasTier.ENTERPRISE: None,
}

TIER_PRICE_USD: dict[SaasTier, int | None] = {
    SaasTier.STARTER: 29,
    SaasTier.PRO: 79,
    SaasTier.ENTERPRISE: None,  # custom
}
