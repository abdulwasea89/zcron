"""Admin member directory & lifecycle management (Sections 8.3, 9.3, 7.6).

Admins (owner/manager) view the member directory, change member status
(ban/unban/freeze/cancel), work the approved-enrollment approval queue, and send
invite-only invitations tied to a single-use code. All actions are audited.
"""

from __future__ import annotations

import csv
import io
import secrets
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import (
    MemberStatus,
    NotificationKind,
    PaymentStatus,
    Role,
    SubscriptionStatus,
    VerificationPurpose,
)
from app.core.config import settings
from app.core.industry import MoneyMode, get_industry
from app.core.security import hash_password
from app.integrations.email import EmailDeliveryError, send_email, send_email_safe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.members import MemberProfileUpdate, PendingPaymentItem
from app.services import verification_service as verif
from app.services.audit_service import record_audit
from app.services.notifications_service import create_notification


async def directory(
    session: AsyncSession, *, org_id: str, status: MemberStatus | None = None,
    role: Role | None = None,
) -> list[tuple[OrganizationMember, User]]:
    stmt = (
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == org_id)
    )
    if status is not None:
        stmt = stmt.where(OrganizationMember.member_status == status)
    if role is not None:
        stmt = stmt.where(OrganizationMember.role == role)
    rows = (await session.execute(stmt.order_by(OrganizationMember.created_at))).all()
    return [(m, u) for m, u in rows]


async def _get_member(session: AsyncSession, org_id: str, member_id: str) -> OrganizationMember:
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found.")
    return member


async def update_member_profile(
    session: AsyncSession, *, org_id: str, member_id: str,
    data: MemberProfileUpdate, actor_id: str,
) -> OrganizationMember:
    member = await _get_member(session, org_id, member_id)
    changed: list[str] = []
    for field in data.model_fields_set:
        value = getattr(data, field)
        if getattr(member, field) != value:
            setattr(member, field, value)
            changed.append(field)
    if changed:
        session.add(member)
        # Profile fields may contain sensitive health information or ID metadata.
        # Record which fields changed, never their values.
        await record_audit(
            session, action="member.profile_updated", organization_id=org_id,
            actor_user_id=actor_id, entity_type="member", entity_id=member.id,
            metadata={"fields": sorted(changed)},
        )
    return member


def profile_summary(
    member: OrganizationMember, plan: MembershipPlan | None, *, include_private: bool = False,
) -> str:
    """Readable summary of current structured facts; no AI or health-note inference."""
    parts = [f"{member.member_status.value.replace('_', ' ').capitalize()} member"]
    if plan:
        parts.append(f"on {plan.name}")
    summary = " ".join(parts) + "."
    if member.goals:
        summary += f" Goal: {member.goals[:160]}{'…' if len(member.goals) > 160 else ''}."
    if member.emergency_contact:
        summary += " Emergency contact recorded."
    if include_private and member.health_notes:
        summary += " Private health notes recorded."
    return summary


async def change_status(
    session: AsyncSession, *, org_id: str, member_id: str, action: str, reason: str | None,
    actor_id: str,
) -> OrganizationMember:
    member = await _get_member(session, org_id, member_id)
    if member.role == Role.OWNER:
        raise HTTPException(status_code=403, detail="Cannot change the owner's status.")

    action = action.lower()
    if action == "ban":
        member.banned = True
        member.member_status = MemberStatus.BANNED
    elif action == "unban":
        member.banned = False
        member.member_status = MemberStatus.EXPIRED
    elif action == "freeze":
        member.member_status = MemberStatus.FROZEN
    elif action == "unfreeze":
        member.member_status = MemberStatus.ACTIVE
    elif action == "cancel":
        member.member_status = MemberStatus.CANCELLED
    else:
        raise HTTPException(status_code=422, detail="Invalid status action.")

    session.add(member)
    from app.services.family_service import sync_family_status

    await sync_family_status(session, org_id, member.id, member.member_status)
    await record_audit(session, action=f"member.{action}", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="member", entity_id=member.id, metadata={"reason": reason})
    return member


async def change_role(
    session: AsyncSession, *, org_id: str, member_id: str, new_role: str, actor_id: str, actor_role: Role
) -> OrganizationMember:
    member = await _get_member(session, org_id, member_id)
    if actor_role != Role.OWNER:
        raise HTTPException(status_code=403, detail="Only owners can change roles.")
    if member.role == Role.OWNER:
        raise HTTPException(status_code=403, detail="Cannot change the owner's role.")
    try:
        parsed = Role(new_role)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid role: {new_role}")
    if parsed not in {Role.MANAGER, Role.TRAINER, Role.FRONT_DESK, Role.MEMBER}:
        raise HTTPException(status_code=422, detail="Invalid role.")
    if parsed != Role.MEMBER:
        from app.services.family_service import family_members

        if member.family_owner_member_id or await family_members(session, org_id, member.id):
            raise HTTPException(status_code=409, detail="Remove family-plan links before changing this member's role.")
    old_role = member.role
    member.role = parsed
    session.add(member)
    await record_audit(session, action="member.role_changed", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="member", entity_id=member.id,
                       metadata={"old_role": old_role.value, "new_role": parsed.value})
    return member


async def update_email(
    session: AsyncSession, *, org_id: str, member_id: str, new_email: str, actor_id: str
) -> OrganizationMember:
    member = await _get_member(session, org_id, member_id)
    user = await session.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.email = new_email.lower().strip()
    session.add(user)
    await record_audit(session, action="member.email_updated", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="member", entity_id=member.id,
                       metadata={"new_email": new_email})
    return member


# ------------------------------------------------------- approval queue
async def approval_queue(session: AsyncSession, *, org_id: str) -> list[tuple[OrganizationMember, User]]:
    return await directory(session, org_id=org_id, status=MemberStatus.PENDING_APPROVAL)


async def decide_approval(
    session: AsyncSession, *, org_id: str, member_id: str, approve: bool, reason: str | None,
    actor_id: str,
) -> OrganizationMember:
    """Approve -> member proceeds to payment; reject -> notified with reason (Section 8.3)."""

    member = await _get_member(session, org_id, member_id)
    if member.member_status != MemberStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="Member is not awaiting approval.")
    user = await session.get(User, member.user_id)

    if approve:
        member.member_status = MemberStatus.PENDING_PAYMENT
        if user is not None:
            await send_email_safe(user.email, "Application approved",
                                  "Your application was approved. You can now proceed to payment.")
    else:
        member.member_status = MemberStatus.CANCELLED
        if user is not None:
            await send_email_safe(user.email, "Application declined",
                                  f"Your application was declined. Reason: {reason or 'not specified'}.")
    session.add(member)

    # In-app alert for the applicant mirrors the email (Section 8.3).
    if user is not None:
        await create_notification(
            session, org_id=org_id, recipient_user_id=user.id, category=NotificationKind.APPROVAL,
            title="Application approved" if approve else "Application declined",
            body=("Your application was approved. You can now proceed to payment."
                  if approve else
                  f"Your application was declined. Reason: {reason or 'not specified'}."),
            data={"member_id": member.id, "approve": approve},
        )
    await record_audit(session, action=f"member.approval_{'approved' if approve else 'rejected'}",
                       organization_id=org_id, actor_user_id=actor_id, entity_type="member",
                       entity_id=member.id, metadata={"reason": reason})
    return member


# ------------------------------------------------------- invite-only invite
async def _send_invite_email(
    email: str, org_name: str, code: str, *, org_code: str | None = None
) -> bool:
    """Send an invite email. Returns True only if a real provider accepted it.

    The invite email IS the deliverable — if the provider rejects it (e.g. an
    unverified Resend sender domain), the caller must learn that instead of the
    UI falsely reporting "invite sent". The return value is the *actual* send
    outcome, not a config check, so the API never claims delivery it cannot
    prove (stub mode -> False -> the code is returned for manual sharing).
    """

    body = f"You've been invited to join {org_name}. Use this code to join:\n\n{code}"
    if org_code is not None:
        # Office invite-only redemption is entered as org code + email + code (no
        # public signup step), so all three must appear in the email. The web
        # link pre-fills them, which is the path least likely to fail on a phone.
        redeem = f"{settings.frontend_url.rstrip('/')}/redeem/member"
        body = (
            f"You've been invited to join {org_name} as a seat-holder.\n\n"
            f"Activate your seat here:\n{redeem}"
            f"?org_code={org_code}&email={quote(email)}&code={quote(code)}\n\n"
            f"Or open the Acron app, choose \"Redeem invite\", then enter:\n\n"
            f"Organization code: {org_code}\nEmail: {email}\nInvite code: {code}"
        )
    try:
        return await send_email(email, f"You're invited to {org_name}", body)
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not deliver the invite email: {exc}",
        ) from exc


def _is_b2b_office(org: Organization) -> bool:
    """True when the org is an office vertical (money settles by B2B invoice)."""
    try:
        return get_industry(org.industry or "gym").money == MoneyMode.B2B_INVOICE
    except (KeyError, ValueError):
        return False


async def invite_member(
    session: AsyncSession, *, org_id: str, email: str, actor_id: str,
    company_id: str | None = None,
) -> tuple[OrganizationMember, str, bool]:
    """Create a pending member + single-use invite code tied to the email (Section 8.4).

    Returns ``(member, code, email_delivered)``. For office orgs ``company_id``
    binds the seat-holder to a tenant company and the invite email carries the org
    code, because office onboarding is invite-only (no public join-with-code + pay).
    """

    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    office = _is_b2b_office(org)

    user = (
        await session.execute(select(User).where(User.email == email.lower()))
    ).scalar_one_or_none()
    if user is not None:
        existing = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Already a member of this org.")

    if user is None:
        # Create a shell user; password set when they claim the invite.
        user = User(email=email.lower(), hashed_password=hash_password(secrets.token_urlsafe(16)),
                    email_verified=False)
        session.add(user)
        await session.flush()

    member = OrganizationMember(
        organization_id=org_id, user_id=user.id, role=Role.MEMBER,
        member_status=MemberStatus.PENDING_ACTIVATION,
        company_id=company_id if office else None,
    )
    session.add(member)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Lost the check-then-insert race (concurrent invite/signup): the unique
        # (org, user) constraint caught it. Surface the same 409 the guard would.
        await session.rollback()
        raise HTTPException(status_code=409, detail="Already a member of this org.") from exc

    code = await verif.issue_link_token(
        session, email=email, purpose=VerificationPurpose.MEMBER_INVITE,
        organization_id=org_id, user_id=user.id,
    )
    delivered = await _send_invite_email(
        email, org.name, code, org_code=org.org_code if office else None
    )
    await record_audit(session, action="member.invited", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="member", entity_id=member.id,
                       metadata={"company_id": company_id, "office": office,
                                 "email_delivered": delivered})
    return member, code, delivered


async def resend_invite(
    session: AsyncSession, *, org_id: str, member_id: str, actor_id: str
) -> tuple[OrganizationMember, str, bool]:
    """Re-send the invite email for a pending member (Section 8.4).

    Returns (member, code, email_delivered). The caller exposes the code only
    when delivery did not actually happen."""

    member = await _get_member(session, org_id, member_id)
    if member.member_status not in (MemberStatus.PENDING_ACTIVATION, MemberStatus.EXPIRED,
                                     MemberStatus.CANCELLED):
        raise HTTPException(status_code=422, detail="Member is not in a resendable state.")

    user = await session.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    code = await verif.issue_link_token(
        session, email=user.email, purpose=VerificationPurpose.MEMBER_INVITE,
        organization_id=org_id, user_id=user.id,
    )
    delivered = await _send_invite_email(
        user.email, org.name, code, org_code=org.org_code if _is_b2b_office(org) else None
    )
    await record_audit(session, action="member.invite_resent", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="member", entity_id=member.id,
                       metadata={"email_delivered": delivered})
    return member, code, delivered


# ------------------------------------------------------- CSV bulk import
async def bulk_import_csv(
    session: AsyncSession, *, org_id: str, csv_bytes: bytes, actor_id: str
) -> dict:
    """Import members from a CSV (Section 9.9, web-only owner action).

    Expected columns (header row, case-insensitive): ``email`` (required),
    ``full_name``, ``phone``. Each row creates a shell user (if new) + a
    ``pending_activation`` membership, then emails an activation code. Existing
    members of this org are skipped. Returns a per-row summary.
    """

    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=422, detail="CSV is empty or missing a header row.")
    # Normalise headers to lowercase for tolerant matching.
    field_map = {(name or "").strip().lower(): name for name in reader.fieldnames}
    if "email" not in field_map:
        raise HTTPException(status_code=422, detail="CSV must have an 'email' column.")

    created = 0
    skipped = 0
    errors: list[dict] = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        email = (row.get(field_map["email"]) or "").strip().lower()
        if not email or "@" not in email:
            errors.append({"row": i, "error": "invalid or missing email"})
            continue
        full_name = (row.get(field_map.get("full_name", "")) or "").strip() or None
        phone = (row.get(field_map.get("phone", "")) or "").strip() or None

        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is not None:
            existing = (
                await session.execute(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == org_id,
                        OrganizationMember.user_id == user.id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                continue
        else:
            user = User(email=email, full_name=full_name,
                        hashed_password=hash_password(secrets.token_urlsafe(16)),
                        email_verified=False)
            session.add(user)
            await session.flush()

        member = OrganizationMember(
            organization_id=org_id, user_id=user.id, role=Role.MEMBER,
            member_status=MemberStatus.PENDING_ACTIVATION, phone=phone,
        )
        session.add(member)
        try:
            # Savepoint so a duplicate insert (lost race against invite/signup)
            # skips this row without aborting the rest of the import.
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            skipped += 1
            continue
        code = await verif.issue_link_token(
            session, email=email, purpose=VerificationPurpose.MEMBER_ACTIVATION,
            organization_id=org_id, user_id=user.id,
        )
        # Best-effort per row: a bad recipient / provider reject must not abort
        # the whole import. Track undelivered rows so the caller can report them.
        delivered = await send_email_safe(
            email, f"Activate your {org.name} membership",
            f"Your membership at {org.name} is ready. Use this code to activate "
            f"and set your password: {code}")
        if not delivered:
            errors.append({"row": i, "error": "member created but activation email not delivered"})
        created += 1

    await record_audit(session, action="member.bulk_imported", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="organization", entity_id=org_id,
                       metadata={"created": created, "skipped": skipped, "errors": len(errors)})
    return {"created": created, "skipped": skipped, "errors": errors}


async def delete_member(
    session: AsyncSession, *, org_id: str, member_id: str, actor_user_id: str, actor_role: Role,
) -> None:
    if actor_role != Role.OWNER:
        raise HTTPException(status_code=403, detail="Only the owner can delete a member.")
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Member not found.")
    if member.role == Role.OWNER:
        raise HTTPException(status_code=422, detail="Cannot delete the owner.")
    if member.user_id == actor_user_id:
        raise HTTPException(status_code=422, detail="Cannot delete yourself.")
    from app.services.family_service import family_members, set_family_member

    for dependent in await family_members(session, org_id, member.id):
        await set_family_member(
            session, org_id=org_id, owner_id=member.id,
            dependent_id=dependent.id, attach=False, actor_id=actor_user_id,
        )
    await record_audit(session, action="member.deleted", organization_id=org_id, actor_user_id=actor_user_id,
                       entity_type="member", entity_id=member.id,
                       metadata={"deleted_user_id": member.user_id, "deleted_role": member.role.value})
    await session.delete(member)


# ------------------------------------------------------- member detail
async def member_detail(
    session: AsyncSession, *, org_id: str, member_id: str,
) -> dict:
    """Aggregate a member's detail for the web member profile page.

    Returns the member + user, their latest subscription (joined with the plan),
    full payment history, and derived pending payments (Section 9.3):
      - ``first_payment``  — member is pending_payment; the plan isn't chosen
        until payment, so the amount is unknown.
      - ``renewal``        — latest subscription is grace/expired: the snapshot
        price is still owed.
      - ``pending_attempt`` / ``failed_attempt`` — payment rows not yet settled.
    """

    member = await _get_member(session, org_id, member_id)
    user = await session.get(User, member.user_id)

    subscription = (
        await session.execute(
            select(Subscription)
            .where(
                Subscription.organization_id == org_id,
                Subscription.member_id == member.id,
            )
            .order_by(Subscription.created_at.desc())
        )
    ).scalars().first()
    if member.family_owner_member_id:
        from app.services.family_service import covered_subscription

        subscription = await covered_subscription(session, org_id, member)
    plan = None
    if subscription is not None:
        plan = await session.get(MembershipPlan, subscription.plan_id)

    payments = (
        await session.execute(
            select(Payment)
            .where(
                Payment.organization_id == org_id,
                Payment.member_id == member.id,
            )
            .order_by(Payment.created_at.desc())
        )
    ).scalars().all()

    pending: list[PendingPaymentItem] = []

    if member.member_status == MemberStatus.PENDING_PAYMENT:
        pending.append(PendingPaymentItem(
            kind="first_payment",
            label="First membership payment — awaiting payment",
            amount=None,
        ))

    if subscription is not None and subscription.status in {
        SubscriptionStatus.GRACE, SubscriptionStatus.EXPIRED,
    }:
        pending.append(PendingPaymentItem(
            kind="renewal",
            label=f"Renewal due — {plan.name if plan else 'membership plan'}",
            amount=subscription.price_snapshot,
            currency=subscription.currency,
            due_at=subscription.current_period_end,
            payment_id=subscription.id,
        ))

    for p in payments:
        if p.status == PaymentStatus.FAILED:
            pending.append(PendingPaymentItem(
                kind="failed_attempt",
                label="Failed payment attempt",
                amount=p.amount,
                currency=p.currency,
                due_at=p.created_at,
                payment_id=p.id,
            ))
        elif p.status == PaymentStatus.PENDING:
            pending.append(PendingPaymentItem(
                kind="pending_attempt",
                label="Payment pending settlement",
                amount=p.amount,
                currency=p.currency,
                due_at=p.created_at,
                payment_id=p.id,
            ))

    return {
        "member": member,
        "user": user,
        "subscription": subscription,
        "plan": plan,
        "payments": list(payments),
        "pending_payments": pending,
    }
