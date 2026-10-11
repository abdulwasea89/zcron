"""Model registry.

Importing this package imports every table module so that
``SQLModel.metadata`` is fully populated (used by ``init_db`` and Alembic).
"""

from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.cash import CashReconciliation
from app.models.campaign import Campaign, CampaignDelivery
from app.models.celebration import MemberCelebration
from app.models.class_session import ClassBooking, ClassSession
from app.models.company import Company
from app.models.company_contract import CompanyContract
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.gamification import GymChallenge, MemberChallengeProgress, MemberStreak
from app.models.idempotency_key import IdempotencyKey
from app.models.inactivity_ladder import InactivityLadderProgress, InactivityLadderRung
from app.models.inbox import InboxConversation, InboxMessage
from app.models.invoice import Invoice
from app.models.lead import Lead, LeadBooking
from app.models.member_trainer import MemberTrainer
from app.models.membership import OrganizationMember
from app.models.notification import Notification
from app.models.nps import NpsSurvey
from app.models.onboarding import OnboardingJourney, OnboardingMilestoneProgress
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.payroll import PayAdvance, PayrollEntry, PayrollRun
from app.models.plan import MembershipPlan
from app.models.receipt import ReceiptUpload
from app.models.referral import Referral, ReferralCode, ReferralProgram, ReferralReward
from app.models.session import AuthSession
from app.models.signup_attempt import SignupAttempt
from app.models.staff import Shift, StaffInvite, Task
from app.models.subscription import Subscription
from app.models.user import User
from app.models.verification import VerificationToken
from app.models.visitor import Locker, Visitor
from app.models.winback import WinBackAttempt

__all__ = [
    "AuditLog",
    "Attendance",
    "AuthSession",
    "CashReconciliation",
    "Campaign",
    "CampaignDelivery",
    "ClassBooking",
    "ClassSession",
    "Company",
    "CompanyContract",
    "Conversation",
    "ConversationMessage",
    "GymChallenge",
    "IdempotencyKey",
    "InactivityLadderProgress",
    "InactivityLadderRung",
    "InboxConversation",
    "InboxMessage",
    "Invoice",
    "Lead",
    "LeadBooking",
    "MemberTrainer",
    "MemberChallengeProgress",
    "MemberStreak",
    "MembershipPlan",
    "MemberCelebration",
    "Notification",
    "NpsSurvey",
    "OnboardingJourney",
    "OnboardingMilestoneProgress",
    "Organization",
    "OrganizationMember",
    "PayAdvance",
    "Payment",
    "PayrollEntry",
    "PayrollRun",
    "ReceiptUpload",
    "Referral",
    "ReferralCode",
    "ReferralProgram",
    "ReferralReward",
    "Shift",
    "SignupAttempt",
    "StaffInvite",
    "Subscription",
    "Task",
    "User",
    "VerificationToken",
    "Visitor",
    "Locker",
    "WinBackAttempt",
]
