"""Model registry.

Importing this package imports every table module so that
``SQLModel.metadata`` is fully populated (used by ``init_db`` and Alembic).
"""

from app.models.attendance import Attendance
from app.models.audit_log import AuditLog
from app.models.audit_chain_head import AuditChainHead
from app.models.cash import CashReconciliation
from app.models.campaign import Campaign, CampaignDelivery, CampaignPaymentAttribution
from app.models.celebration import MemberCelebration
from app.models.class_session import ClassBooking, ClassSession
from app.models.company import Company
from app.models.company_contract import CompanyContract
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.data_subject_request import DataSubjectRequest
from app.models.freeze_request import MembershipFreezeRequest
from app.models.membership_change_request import MembershipChangeRequest
from app.models.gamification import GymChallenge, MemberChallengeProgress, MemberStreak
from app.models.idempotency_key import IdempotencyKey
from app.models.inactivity_ladder import InactivityLadderProgress, InactivityLadderRung
from app.models.inbox import InboxConversation, InboxMessage
from app.models.inbox_channel import InboxChannelConnection
from app.models.invoice import Invoice
from app.models.gym_invoice import GymInvoice
from app.models.gym_form import GymForm, GymFormAcceptance
from app.models.lead import Lead, LeadBooking, LeadFollowUp
from app.models.member_trainer import MemberTrainer
from app.models.membership import OrganizationMember
from app.models.membership_reminder import MembershipReminder
from app.models.notification import Notification
from app.models.nps import NpsSurvey
from app.models.onboarding import OnboardingJourney, OnboardingMilestoneProgress
from app.models.organization import Organization
from app.models.operating_expense import OperatingExpense
from app.models.expense_receipt import ExpenseReceipt
from app.models.payment import Payment
from app.models.payment_refund import PaymentRefund
from app.models.payroll import PayAdvance, PayrollEntry, PayrollRun
from app.models.plan import MembershipPlan
from app.models.promotion import Promotion
from app.models.receipt import ReceiptUpload
from app.models.referral import Referral, ReferralCode, ReferralProgram, ReferralReward
from app.models.session import AuthSession
from app.models.signup_attempt import SignupAttempt
from app.models.staff import ScheduledShift, Shift, StaffInvite, Task
from app.models.trainer_session import TrainerSessionLog
from app.models.trainer_package import TrainerPackage
from app.models.trainer_availability import TrainerAvailability
from app.models.subscription import Subscription
from app.models.user import User
from app.models.verification import VerificationToken
from app.models.visitor import Locker, Visitor
from app.models.winback import WinBackAttempt

__all__ = [
    "CampaignPaymentAttribution",
    "PaymentRefund",
    "AuditLog",
    "AuditChainHead",
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
    "DataSubjectRequest",
    "MembershipFreezeRequest",
    "MembershipChangeRequest",
    "MembershipReminder",
    "GymChallenge",
    "IdempotencyKey",
    "InactivityLadderProgress",
    "InactivityLadderRung",
    "InboxConversation",
    "InboxMessage",
    "InboxChannelConnection",
    "Invoice",
    "GymInvoice",
    "GymForm",
    "GymFormAcceptance",
    "Lead",
    "LeadBooking",
    "LeadFollowUp",
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
    "OperatingExpense",
    "ExpenseReceipt",
    "OrganizationMember",
    "PayAdvance",
    "Payment",
    "Promotion",
    "PayrollEntry",
    "PayrollRun",
    "ReceiptUpload",
    "Referral",
    "ReferralCode",
    "ReferralProgram",
    "ReferralReward",
    "Shift",
    "ScheduledShift",
    "SignupAttempt",
    "StaffInvite",
    "Subscription",
    "Task",
    "TrainerSessionLog",
    "TrainerPackage",
    "TrainerAvailability",
    "User",
    "VerificationToken",
    "Visitor",
    "Locker",
    "WinBackAttempt",
    "MemberCreditAccount",
    "MemberCreditEntry",
]

from app.models.member_credit import MemberCreditAccount, MemberCreditEntry

from app.models.retail import RetailProduct, RetailStockMovement  # noqa: F401
