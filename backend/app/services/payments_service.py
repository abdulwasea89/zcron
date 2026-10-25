"""Payment history & refunds (Sections 13, Stripe Connect refunds).

Lists payment history for the org or a member. Refunds are idempotent
(Security Rule #2), web-only and admin-gated (Security Rule #7), and routed
through the gym's Stripe Connect account — never the platform account
(Security Rule #3). Card refunds call Connect; cash/offline refunds are recorded
directly.
"""

from __future__ import annotations

from math import isfinite

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.constants import PaymentKind, PaymentMethod, PaymentStatus
from app.core.security import now_utc
from app.integrations.email import send_email_safe as send_email
from app.integrations.stripe_connect import connect_stripe
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.payment import Payment
from app.models.user import User
from app.services import idempotency_service
from app.services.audit_service import record_audit


async def list_payments(
    session: AsyncSession, *, org_id: str, member_id: str | None = None
) -> list[Payment]:
    stmt = select(Payment).where(Payment.organization_id == org_id)
    if member_id is not None:
        stmt = stmt.where(Payment.member_id == member_id)
    return list((await session.execute(stmt.order_by(Payment.created_at.desc()))).scalars())


async def refund(
    session: AsyncSession, *, org_id: str, payment_id: str, amount: float | None,
    reason: str | None, idempotency_key: str, actor_id: str,
) -> Payment:
    payment = await session.get(Payment, payment_id, with_for_update=True)
    if payment is None or payment.organization_id != org_id:
        raise HTTPException(status_code=404, detail="Payment not found.")

    # Claim BEFORE any state guard so a replay returns the cached (already
    # refunded) state instead of failing the "not refundable" check. Hash the
    # raw request input (not the computed amount) so replays match (Section 13.4).
    endpoint = "POST /payments/refund"
    claim = await idempotency_service.claim(
        session, key=idempotency_key, endpoint=endpoint,
        body={"payment_id": payment_id, "amount": amount},
        organization_id=org_id, user_id=actor_id,
    )
    if not claim.claimed:
        return payment  # replay -> current (already-refunded) state

    # This endpoint refunds member fees only — money that flowed through the
    # gym's Connect account. SaaS subscription and trainer-payout money never
    # touches Connect (Security Rule #3), so it can't be refunded here; SaaS
    # billing is managed via the platform subscription (upgrade/cancel).
    if payment.kind != PaymentKind.MEMBER_FEE:
        await idempotency_service.fail(session, claim.record, code=422,
                                       body='{"detail":"Only member payments can be refunded here."}')
        raise HTTPException(status_code=422,
                            detail="Only member payments can be refunded here. "
                                   "SaaS subscription charges are managed in billing settings.")

    if payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED}:
        await idempotency_service.fail(session, claim.record, code=409,
                                       body='{"detail":"Payment is not refundable."}')
        raise HTTPException(status_code=409, detail="Payment is not refundable.")

    # A portion already converted into member-wallet credit cannot also leave
    # the Connect account as a cash refund.
    vault_credited = payment.vault_credited_minor / 100
    refundable = round(max(0, payment.amount - payment.refunded_amount - vault_credited), 2)
    refund_amount = round(amount if amount is not None else refundable, 2)
    if not isfinite(refund_amount) or refund_amount <= 0 or refund_amount > refundable:
        await idempotency_service.fail(session, claim.record, code=422,
                                       body='{"detail":"Invalid refund amount."}')
        raise HTTPException(status_code=422, detail="Invalid refund amount.")

    # Card refunds go through the gym's Connect account.
    if payment.method == PaymentMethod.CARD:
        org = await session.get(Organization, org_id)
        if not org or not org.stripe_connect_account_id or not payment.stripe_charge_id:
            await idempotency_service.fail(session, claim.record, code=409,
                                           body='{"detail":"Cannot refund this card payment."}')
            raise HTTPException(status_code=409, detail="Cannot refund this card payment.")
        result = await connect_stripe.refund(
            connected_account_id=org.stripe_connect_account_id,
            charge_id=payment.stripe_charge_id,
            amount_cents=int(round(refund_amount * 100)),
            idempotency_key=idempotency_key,
        )
        if result.get("status") not in {"succeeded", "pending"}:
            await idempotency_service.fail(session, claim.record, code=402,
                                           body='{"detail":"Refund failed at Stripe."}')
            raise HTTPException(status_code=402, detail="Refund failed at Stripe.")

    from decimal import Decimal
    from app.services.refund_ledger_service import record_refund

    await record_refund(session, payment=payment, amount=Decimal(str(refund_amount)), source="admin", actor_id=actor_id)
    payment.refunded_amount = round(payment.refunded_amount + refund_amount, 2)
    payment.refunded_at = now_utc()
    payment.status = (
        PaymentStatus.REFUNDED if payment.refunded_amount + vault_credited >= payment.amount - 0.01
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    session.add(payment)
    if payment.subscription_id:
        from app.models.subscription import Subscription
        subscription = await session.get(Subscription, payment.subscription_id)
        if subscription is not None and subscription.prepaid_value_minor is not None:
            subscription.prepaid_value_minor = max(0, subscription.prepaid_value_minor - int(round(refund_amount * 100)))
            subscription.prepaid_value_at = now_utc()
            session.add(subscription)

    await record_audit(session, action="payment.refunded", organization_id=org_id, actor_user_id=actor_id,
                       entity_type="payment", entity_id=payment.id,
                       new_values={"refunded_amount": payment.refunded_amount}, metadata={"reason": reason})

    # Notify the member.
    if payment.member_id:
        member = await session.get(OrganizationMember, payment.member_id)
        user = await session.get(User, member.user_id) if member else None
        if user is not None:
            await send_email(user.email, "Refund processed",
                             f"A refund of {payment.currency} {refund_amount:.2f} was processed.")

    await idempotency_service.complete(session, claim.record, code=200,
                                       body=f'{{"refunded_amount": {payment.refunded_amount}}}')
    return payment
