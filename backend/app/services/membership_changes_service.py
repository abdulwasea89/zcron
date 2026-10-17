"""Reviewed member plan changes, transfers, and cancellation saves."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import ConnectStatus, MemberStatus, PaymentKind, PaymentMethod, PaymentStatus, Role, SubscriptionStatus
from app.models.base import utcnow
from app.models.membership import OrganizationMember
from app.models.membership_change_request import MembershipChangeRequest
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.plan import MembershipPlan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.members_service import _freeze_member


async def _member_subscription(session: AsyncSession, org_id: str, member_id: str):
    member = await session.get(OrganizationMember, member_id)
    if member is None or member.organization_id != org_id or member.role != Role.MEMBER:
        raise HTTPException(status_code=404, detail="Member not found.")
    subscription = (await session.execute(select(Subscription).where(
        Subscription.organization_id == org_id,
        Subscription.member_id == member_id,
        Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE, SubscriptionStatus.FROZEN]),
    ).order_by(Subscription.started_at.desc()))).scalars().first()
    if subscription is None:
        raise HTTPException(status_code=409, detail="No current membership plan can be changed.")
    return member, subscription


async def create_request(session: AsyncSession, *, org_id: str, user_id: str, request_type: str,
                         target_plan_id: str | None, reason: str) -> MembershipChangeRequest:
    request_type = request_type.strip().lower()
    if request_type not in {"upgrade", "downgrade", "transfer", "cancel"}:
        raise HTTPException(status_code=422, detail="Choose an upgrade, downgrade, transfer, or cancellation.")
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    member, subscription = await _member_subscription(session, org_id, member.id)
    if request_type == "cancel":
        target_plan_id = None
    elif not target_plan_id:
        raise HTTPException(status_code=422, detail="Choose a target membership plan.")
    else:
        target = await session.get(MembershipPlan, target_plan_id)
        if target is None or target.organization_id != org_id or target.status.value != "published":
            raise HTTPException(status_code=404, detail="Available target plan not found.")
        if target.currency != subscription.currency:
            raise HTTPException(status_code=422, detail="Membership changes must use the current plan currency.")
        if request_type == "upgrade" and target.price <= subscription.price_snapshot:
            raise HTTPException(status_code=422, detail="An upgrade must cost more than the current plan.")
        if request_type == "downgrade" and target.price >= subscription.price_snapshot:
            raise HTTPException(status_code=422, detail="A downgrade must cost less than the current plan.")
    pending = (await session.execute(select(MembershipChangeRequest).where(
        MembershipChangeRequest.organization_id == org_id,
        MembershipChangeRequest.member_id == member.id,
        MembershipChangeRequest.status.in_(["pending", "offered"]),
    ))).scalars().first()
    if pending:
        raise HTTPException(status_code=409, detail="You already have a membership change awaiting a response.")
    request = MembershipChangeRequest(
        organization_id=org_id, member_id=member.id, subscription_id=subscription.id,
        request_type=request_type, target_plan_id=target_plan_id, reason=reason.strip(),
    )
    session.add(request)
    await session.flush()
    await record_audit(session, action="membership.change_requested", organization_id=org_id,
                       actor_user_id=user_id, entity_type="member", entity_id=member.id,
                       metadata={"request_id": request.id, "request_type": request_type,
                                 "target_plan_id": target_plan_id})
    return request


async def list_member_requests(session: AsyncSession, *, org_id: str, user_id: str):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return (await session.execute(select(MembershipChangeRequest).where(
        MembershipChangeRequest.organization_id == org_id,
        MembershipChangeRequest.member_id == member.id,
    ).order_by(MembershipChangeRequest.created_at.desc()))).scalars().all()


async def queue(session: AsyncSession, *, org_id: str, status: str = "pending"):
    if status not in {"pending", "offered", "payment_pending", "approved", "rejected", "withdrawn"}:
        raise HTTPException(status_code=422, detail="Invalid membership change status.")
    stmt = (select(MembershipChangeRequest, OrganizationMember, User, Subscription, MembershipPlan)
            .join(OrganizationMember, OrganizationMember.id == MembershipChangeRequest.member_id)
            .join(User, User.id == OrganizationMember.user_id)
            .join(Subscription, Subscription.id == MembershipChangeRequest.subscription_id)
            .join(MembershipPlan, MembershipPlan.id == Subscription.plan_id)
            .where(MembershipChangeRequest.organization_id == org_id,
                   MembershipChangeRequest.status == status)
            .order_by(MembershipChangeRequest.created_at))
    rows = (await session.execute(stmt)).all()
    result = []
    for request, member, user, _sub, current_plan in rows:
        target = await session.get(MembershipPlan, request.target_plan_id) if request.target_plan_id else None
        result.append((request, member, user, current_plan, target))
    return result


def _remaining_fraction(subscription: Subscription) -> float:
    end, start, now = subscription.current_period_end, subscription.started_at, utcnow()
    if not end or end <= now or end <= start:
        return 0.0
    return max(0.0, min(1.0, (end - now).total_seconds() / (end - start).total_seconds()))


def _apply_plan(subscription: Subscription, target: MembershipPlan) -> None:
    subscription.plan_id = target.id
    subscription.price_snapshot = target.price
    subscription.currency = target.currency
    subscription.classes_remaining = target.pack_size
    subscription.credits_allowance = target.included_credits
    subscription.scheduled_plan_id = None
    subscription.scheduled_plan_at = None


async def _refund_change_difference(session: AsyncSession, *, org_id: str,
                                    request: MembershipChangeRequest, subscription: Subscription,
                                    amount: float, actor_id: str) -> None:
    rows = (await session.execute(select(Payment).where(
        Payment.organization_id == org_id, Payment.subscription_id == subscription.id,
        Payment.kind == PaymentKind.MEMBER_FEE,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED]),
    ).order_by(Payment.paid_at.desc()))).scalars().all()
    remainder = round(amount, 2)
    for payment in rows:
        available = round(payment.amount - payment.refunded_amount, 2)
        value = min(remainder, available)
        if value <= 0:
            continue
        from app.services.payments_service import refund

        await refund(session, org_id=org_id, payment_id=payment.id, amount=value,
                     reason="Prorated membership plan downgrade", actor_id=actor_id,
                     idempotency_key=f"member-change-{request.id}-{payment.id}")
        await record_audit(session, action="membership.proration_refunded",
                           organization_id=org_id, actor_user_id=actor_id,
                           entity_type="payment", entity_id=payment.id,
                           metadata={"request_id": request.id, "amount": value})
        remainder = round(remainder - value, 2)
        if remainder <= 0.01:
            return
    if remainder > 0.01:
        raise HTTPException(status_code=409, detail="The prorated refund exceeds refundable member payments.")


async def decide(session: AsyncSession, *, org_id: str, request_id: str, actor_id: str,
                 approve: bool, offer_pause: bool, note: str | None,
                 offer_type: str | None = None, offer_plan_id: str | None = None,
                 offer_discount_percent: float | None = None, offer_discount_months: int | None = None,
                 effective_timing: str = "now"):
    request = await session.get(MembershipChangeRequest, request_id)
    if request is None or request.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Membership change request not found.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="This request has already been reviewed.")
    member, subscription = await _member_subscription(session, org_id, request.member_id)
    if offer_pause:
        if request.request_type != "cancel":
            raise HTTPException(status_code=422, detail="A pause save offer is available for cancellation requests.")
        offer_type = "pause"
    if offer_type:
        if request.request_type != "cancel" or offer_type not in {"pause", "alternate_plan", "discount"}:
            raise HTTPException(status_code=422, detail="Choose a valid cancellation save offer.")
        if offer_type == "alternate_plan":
            offer_plan = await session.get(MembershipPlan, offer_plan_id) if offer_plan_id else None
            if offer_plan is None or offer_plan.organization_id != org_id or offer_plan.status.value != "published":
                raise HTTPException(status_code=422, detail="Choose a published alternative plan.")
            if offer_plan.currency != subscription.currency or offer_plan.price > subscription.price_snapshot:
                raise HTTPException(status_code=422, detail="A save plan must use the current currency and cost no more than the current plan.")
            request.offer_plan_id = offer_plan.id
            request.save_offer = f"Switch to {offer_plan.name} at the end of your current paid period"
        elif offer_type == "discount":
            if offer_discount_percent is None or not 1 <= offer_discount_percent <= 100:
                raise HTTPException(status_code=422, detail="Choose a discount from 1% to 100%.")
            if offer_discount_months is None or not 1 <= offer_discount_months <= 12:
                raise HTTPException(status_code=422, detail="Choose a discount duration from 1 to 12 billing periods.")
            request.offer_discount_percent = offer_discount_percent
            request.offer_discount_months = offer_discount_months
            request.save_offer = f"{offer_discount_percent:g}% off for {offer_discount_months} billing period(s)"
        else:
            request.save_offer = "Pause membership instead of cancelling"
        request.offer_type = offer_type
        request.status = "offered"
    elif approve and request.request_type == "cancel":
        if (effective_timing != "now" and subscription.current_period_end
                and subscription.current_period_end > utcnow()):
            subscription.cancel_at_period_end = True
            request.effective_at = subscription.current_period_end
            request.decision_note = "Cancellation is scheduled for the end of the paid period."
        else:
            from app.services.member_vault_service import credit_unused
            await credit_unused(session, subscription, reference=f"cancel:{subscription.id}",
                                description="Unused membership value after cancellation")
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = utcnow()
            member.member_status = MemberStatus.CANCELLED
            from app.services.family_service import sync_family_status

            await sync_family_status(session, org_id, member.id, member.member_status)
        request.status = "approved"
    elif approve:
        target = await session.get(MembershipPlan, request.target_plan_id) if request.target_plan_id else None
        if target is None or target.organization_id != org_id or target.status.value != "published":
            raise HTTPException(status_code=409, detail="The requested plan is no longer available.")
        if effective_timing not in {"now", "period_end"}:
            raise HTTPException(status_code=422, detail="Choose immediate or period-end timing.")
        if target.currency != subscription.currency:
            raise HTTPException(status_code=422, detail="Membership changes must use the current plan currency.")
        if effective_timing == "period_end" and subscription.current_period_end and subscription.current_period_end > utcnow():
            subscription.scheduled_plan_id = target.id
            subscription.scheduled_plan_at = subscription.current_period_end
            request.effective_at = subscription.current_period_end
            request.decision_note = "Plan change is scheduled for the next billing period."
            request.status = "approved"
        elif target.price > subscription.price_snapshot:
            from app.services.member_vault_service import account, remaining_value, minor, post
            remaining = await remaining_value(session, subscription)
            wallet = await account(session, org_id, member.id, subscription.currency)
            total_due = minor(round((target.price - subscription.price_snapshot) * _remaining_fraction(subscription), 2))
            request.prepaid_before_minor = remaining
            request.vault_credit_minor = min(total_due, wallet.balance_minor)
            request.amount_due = max(0, total_due - request.vault_credit_minor) / 100
            request.status = "payment_pending" if request.amount_due > 0 else "approved"
            if request.status == "approved":
                if request.vault_credit_minor:
                    await post(session, org_id=org_id, member_id=member.id, currency=subscription.currency,
                               amount=-request.vault_credit_minor, reference=f"upgrade:{request.id}",
                               description=f"Vault credit for upgrade to {target.name}")
                _apply_plan(subscription, target)
                subscription.prepaid_value_minor = remaining + total_due
                subscription.prepaid_value_at = utcnow()
                session.add(subscription)
        elif target.price < subscription.price_snapshot:
            refund_amount = round((subscription.price_snapshot - target.price) * _remaining_fraction(subscription), 2)
            if refund_amount:
                from app.services.member_vault_service import credit_unused, minor
                await credit_unused(session, subscription, reference=f"downgrade:{request.id}",
                                    description=f"Unused value from downgrade to {target.name}",
                                    limit_minor=minor(refund_amount))
            _apply_plan(subscription, target)
            request.status = "approved"
        else:
            _apply_plan(subscription, target)
            request.status = "approved"
    else:
        request.status = "rejected"
    request.reviewed_by = actor_id
    request.reviewed_at = utcnow()
    request.decision_note = (note or "").strip() or None
    session.add_all([request, member, subscription])
    await record_audit(session, action=f"membership.change_{request.status}", organization_id=org_id,
                       actor_user_id=actor_id, entity_type="member", entity_id=member.id,
                       metadata={"request_id": request.id, "request_type": request.request_type,
                                 "target_plan_id": request.target_plan_id, "offer_pause": offer_pause})
    return request


async def start_upgrade_payment(session: AsyncSession, *, org_id: str, user_id: str,
                                request_id: str) -> dict:
    request = await session.get(MembershipChangeRequest, request_id)
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    if member is None or request is None or request.organization_id != org_id or request.member_id != member.id:
        raise HTTPException(status_code=404, detail="Membership change request not found.")
    if request.status != "payment_pending" or request.amount_due <= 0:
        raise HTTPException(status_code=409, detail="This request does not have a payment due.")
    payment = await session.get(Payment, request.payment_id) if request.payment_id else None
    if payment is not None and payment.status == PaymentStatus.SUCCEEDED:
        return {"payment_required": False, "payment_id": payment.id, "amount": payment.amount,
                "currency": payment.currency}
    target = await session.get(MembershipPlan, request.target_plan_id) if request.target_plan_id else None
    if target is None:
        raise HTTPException(status_code=409, detail="The requested plan is no longer available.")
    if payment is None:
        payment = Payment(
            organization_id=org_id, member_id=member.id, subscription_id=request.subscription_id,
            plan_id=target.id, kind=PaymentKind.MEMBER_FEE, method=PaymentMethod.CARD,
            status=PaymentStatus.PENDING, amount=request.amount_due,
            plan_price_amount=request.amount_due, currency=target.currency,
            idempotency_key=f"member-change-{request.id}",
            note="Prorated membership plan upgrade",
        )
        session.add(payment)
        await session.flush()
        request.payment_id = payment.id
        session.add(request)
    org = await session.get(Organization, org_id)
    if (org is None or org.stripe_connect_status != ConnectStatus.ACTIVE
            or not org.stripe_connect_account_id):
        raise HTTPException(status_code=409, detail="The gym has not enabled member payments.")
    from app.integrations.stripe_connect import connect_stripe

    try:
        result = await connect_stripe.create_member_intent(
            connected_account_id=org.stripe_connect_account_id,
            amount_cents=int(round(payment.amount * 100)), currency=payment.currency.lower(),
            idempotency_key=payment.idempotency_key or payment.id,
            description=f"Prorated membership upgrade — {target.name}",
            metadata={"purpose": "membership_plan_change", "request_id": request.id,
                      "member_id": member.id, "organization_id": org_id},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not start the Stripe payment.") from exc
    if result.amount != int(round(payment.amount * 100)) or result.currency.lower() != payment.currency.lower():
        raise HTTPException(status_code=502, detail="Stripe returned an unexpected payment amount.")
    payment.stripe_payment_intent_id = result.id
    if result.status == "succeeded":
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = utcnow()
        payment.stripe_charge_id = result.charge_id
        await _complete_upgrade(session, request=request, payment=payment, actor_id=user_id)
    session.add(payment)
    return {"payment_required": result.status != "succeeded", "payment_id": payment.id,
            "payment_intent_id": payment.stripe_payment_intent_id, "client_secret": result.client_secret,
            "amount": payment.amount, "currency": payment.currency}


async def _complete_upgrade(session: AsyncSession, *, request: MembershipChangeRequest,
                            payment: Payment, actor_id: str) -> None:
    if request.status == "approved":
        return
    subscription = await session.get(Subscription, request.subscription_id)
    target = await session.get(MembershipPlan, request.target_plan_id) if request.target_plan_id else None
    if subscription is None or target is None:
        raise HTTPException(status_code=409, detail="The subscription or target plan is no longer available.")
    if request.vault_credit_minor:
        from app.services.member_vault_service import post
        await post(session, org_id=request.organization_id, member_id=request.member_id,
                   currency=subscription.currency, amount=-request.vault_credit_minor,
                   reference=f"upgrade:{request.id}",
                   description=f"Vault credit for upgrade to {target.name}")
    _apply_plan(subscription, target)
    from app.services.member_vault_service import minor
    subscription.prepaid_value_minor = (request.prepaid_before_minor or 0) + minor(payment.amount) + request.vault_credit_minor
    subscription.prepaid_value_at = utcnow()
    request.status = "approved"
    request.reviewed_at = utcnow()
    request.decision_note = "Prorated upgrade payment completed."
    session.add_all([request, payment, subscription])
    await record_audit(session, action="membership.change_approved", organization_id=request.organization_id,
                       actor_user_id=actor_id, entity_type="member", entity_id=request.member_id,
                       metadata={"request_id": request.id, "payment_id": payment.id,
                                 "amount": payment.amount, "target_plan_id": target.id})


async def confirm_upgrade_payment(session: AsyncSession, *, org_id: str, user_id: str,
                                  request_id: str, payment_intent_id: str) -> MembershipChangeRequest:
    request = await session.get(MembershipChangeRequest, request_id)
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    payment = await session.get(Payment, request.payment_id) if request and request.payment_id else None
    if (member is None or request is None or payment is None or request.organization_id != org_id
            or request.member_id != member.id or payment.member_id != member.id):
        raise HTTPException(status_code=404, detail="Upgrade payment not found.")
    if payment.status == PaymentStatus.SUCCEEDED and request.status == "approved":
        return request
    if payment.stripe_payment_intent_id != payment_intent_id:
        raise HTTPException(status_code=422, detail="Payment intent does not match this request.")
    org = await session.get(Organization, org_id)
    if org is None or not org.stripe_connect_account_id:
        raise HTTPException(status_code=409, detail="Gym card payment account is unavailable.")
    from app.integrations.stripe_connect import connect_stripe

    try:
        result = await connect_stripe.inspect_member_intent(
            connected_account_id=org.stripe_connect_account_id, intent_id=payment_intent_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not verify the Stripe payment.") from exc
    if (result is None
            or result.amount != int(round(payment.amount * 100))
            or result.currency.lower() != payment.currency.lower()):
        raise HTTPException(status_code=402, detail="Stripe has not confirmed the prorated payment.")
    if result.status == "processing":
        # Redirect and bank-based methods can settle asynchronously. Keep the
        # request pending; the verified Connect webhook completes it on success.
        return request
    if result.status != "succeeded":
        raise HTTPException(status_code=402, detail="Stripe has not confirmed the prorated payment.")
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = utcnow()
    payment.note = "Prorated membership plan upgrade"
    payment.stripe_charge_id = result.charge_id
    payment.stripe_payment_method_type = result.payment_method_type
    await _complete_upgrade(session, request=request, payment=payment, actor_id=user_id)
    return request


async def respond_to_offer(session: AsyncSession, *, org_id: str, user_id: str,
                           request_id: str, accept: bool):
    member = (await session.execute(select(OrganizationMember).where(
        OrganizationMember.organization_id == org_id,
        OrganizationMember.user_id == user_id,
        OrganizationMember.role == Role.MEMBER,
    ))).scalar_one_or_none()
    request = await session.get(MembershipChangeRequest, request_id)
    if member is None or request is None or request.organization_id != org_id or request.member_id != member.id:
        raise HTTPException(status_code=404, detail="Membership change offer not found.")
    if request.status != "offered" or request.request_type != "cancel":
        raise HTTPException(status_code=409, detail="There is no cancellation save offer awaiting a response.")
    subscription = await session.get(Subscription, request.subscription_id)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Membership subscription not found.")
    if accept:
        if request.offer_type == "pause":
            if member.member_status not in {MemberStatus.ACTIVE, MemberStatus.GRACE}:
                raise HTTPException(status_code=409, detail="This membership cannot be paused right now.")
            await _freeze_member(session, member, frozen_until=None)
            request.decision_note = "Member accepted the pause offer."
        elif request.offer_type == "alternate_plan":
            plan = await session.get(MembershipPlan, request.offer_plan_id) if request.offer_plan_id else None
            if plan is None or plan.organization_id != org_id or plan.status.value != "published":
                raise HTTPException(status_code=409, detail="The offered plan is no longer available.")
            if not subscription.current_period_end or subscription.current_period_end <= utcnow():
                raise HTTPException(status_code=409, detail="The offer period ended; ask the gym for a new offer.")
            subscription.scheduled_plan_id = plan.id
            subscription.scheduled_plan_at = subscription.current_period_end
            subscription.cancel_at_period_end = False
            request.effective_at = subscription.current_period_end
            request.decision_note = "Member accepted the alternative plan for the next billing period."
        elif request.offer_type == "discount":
            plan = await session.get(MembershipPlan, subscription.plan_id)
            if plan is None or not request.offer_discount_percent or not request.offer_discount_months:
                raise HTTPException(status_code=409, detail="The discount offer is incomplete.")
            if not subscription.current_period_end or subscription.current_period_end <= utcnow():
                raise HTTPException(status_code=409, detail="The offer period ended; ask the gym for a new offer.")
            from app.services.plan_entitlements import subscription_terms

            expiry = subscription.current_period_end
            for _ in range(request.offer_discount_months):
                next_end, _credits = subscription_terms(plan, at=expiry)
                if next_end is None:
                    raise HTTPException(status_code=422, detail="Discount offers require a plan with a billing cycle.")
                expiry = next_end
            subscription.save_discount_percent = request.offer_discount_percent
            subscription.save_discount_expires_at = expiry
            subscription.cancel_at_period_end = False
            request.decision_note = f"Member accepted {request.offer_discount_percent:g}% off through {expiry.date().isoformat()}."
        else:
            raise HTTPException(status_code=409, detail="This save offer is no longer available.")
        request.status = "approved"
        action = "membership.save_offer_accepted"
    else:
        if subscription.current_period_end and subscription.current_period_end > utcnow():
            subscription.cancel_at_period_end = True
            request.effective_at = subscription.current_period_end
            request.decision_note = "Member declined the save offer; cancellation remains scheduled for the end of the paid period."
        else:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = utcnow()
            member.member_status = MemberStatus.CANCELLED
            from app.services.family_service import sync_family_status

            await sync_family_status(session, org_id, member.id, member.member_status)
            request.decision_note = "Member declined the save offer; membership cancelled."
        request.status = "approved"
        session.add(subscription)
        action = "membership.save_offer_declined"
    request.reviewed_by = None
    request.reviewed_at = utcnow()
    session.add_all([request, member, subscription])
    await record_audit(session, action=action, organization_id=org_id,
                       actor_user_id=user_id, entity_type="member", entity_id=member.id,
                       metadata={"request_id": request.id})
    return request
