"use client";

import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { Row, ReadValue, Section } from "@/components/settings/primitives";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";
import type { OrganizationOut, ProfileOut } from "@/lib/types";
import { MfaCard } from "./MfaCard";

type StripePaymentElement = { mount: (element: HTMLElement) => void; destroy: () => void };
type StripeElements = {
  create: (kind: "payment") => StripePaymentElement;
  submit: () => Promise<{ error?: { message?: string } }>;
};
type StripeInstance = {
  elements: (options: { clientSecret: string; appearance?: Record<string, unknown> }) => StripeElements;
  confirmPayment: (options: { elements: StripeElements; confirmParams: { return_url: string }; redirect: "if_required" }) => Promise<{ error?: { message?: string }; paymentIntent?: { id: string; status: string } }>;
  confirmSetup: (options: { elements: StripeElements; confirmParams: { return_url: string }; redirect: "if_required" }) => Promise<{ error?: { message?: string }; setupIntent?: { id: string; status: string } }>;
};
declare global { interface Window { Stripe?: (key: string, options: { stripeAccount: string }) => StripeInstance } }

function loadStripeScript(): Promise<void> {
  if (window.Stripe) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const current = document.querySelector<HTMLScriptElement>('script[data-stripe-js="true"]');
    if (current) { current.addEventListener("load", () => resolve(), { once: true }); current.addEventListener("error", () => { current.remove(); reject(new Error("Stripe.js did not load.")); }, { once: true }); return; }
    const script = document.createElement("script");
    script.src = "https://js.stripe.com/v3/"; script.async = true; script.dataset.stripeJs = "true";
    script.onload = () => resolve(); script.onerror = () => { script.remove(); reject(new Error("Stripe.js did not load.")); };
    document.head.appendChild(script);
  });
}

/* The profile fields are shared: the standalone /app/account page owns and
   saves them itself, while the settings dialog stages them under its single
   global Save bar. Keeping one field implementation is what stops the two
   surfaces from drifting. */
export interface AccountFieldsValue {
  full_name: string;
  phone: string;
  address: string;
  city: string;
  occupation: string;
  education: string;
  emergency_contact: string;
}

export const emptyAccountFields: AccountFieldsValue = {
  full_name: "",
  phone: "",
  address: "",
  city: "",
  occupation: "",
  education: "",
  emergency_contact: "",
};

export function AccountFields({
  value,
  onChange,
  profile,
}: {
  value: AccountFieldsValue;
  onChange: (patch: Partial<AccountFieldsValue>) => void;
  profile: ProfileOut | null;
}) {
  return (
    <>
      <Row label="Email" description="Email cannot be changed here">
        <ReadValue>{profile?.email ?? "—"}</ReadValue>
      </Row>
      <Row label="Full name" description="Your display name across the platform">
        <Input size="sm" value={value.full_name} onChange={(e) => onChange({ full_name: e.target.value })} placeholder="Your name" />
      </Row>
      <Row label="Phone" description="Used for account recovery and alerts">
        <Input size="sm" value={value.phone} onChange={(e) => onChange({ phone: e.target.value })} placeholder="+1 555-0123" />
      </Row>
      <Row label="Address" description="Your street address">
        <Input size="sm" value={value.address} onChange={(e) => onChange({ address: e.target.value })} placeholder="Street address" />
      </Row>
      <Row label="City" description="Your city">
        <Input size="sm" value={value.city} onChange={(e) => onChange({ city: e.target.value })} placeholder="City" />
      </Row>
      <Row label="Occupation" description="What you do">
        <Input size="sm" value={value.occupation} onChange={(e) => onChange({ occupation: e.target.value })} placeholder="e.g. Personal trainer" />
      </Row>
      <Row label="Education" description="Your highest qualification">
        <Input size="sm" value={value.education} onChange={(e) => onChange({ education: e.target.value })} placeholder="e.g. Bachelor's degree" />
      </Row>
      <Row label="Emergency contact" description="Who to reach in an emergency">
        <Input size="sm" value={value.emergency_contact} onChange={(e) => onChange({ emergency_contact: e.target.value })} placeholder="Name & phone" />
      </Row>
      {profile?.gender && (
        <Row label="Gender" description="Set during onboarding">
          <ReadValue>{profile.gender}</ReadValue>
        </Row>
      )}
      {profile?.date_of_birth && (
        <Row label="Date of birth" description="Set during onboarding">
          <ReadValue>{profile.date_of_birth}</ReadValue>
        </Row>
      )}
    </>
  );
}

export default function AccountPage() {
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [org, setOrg] = useState<OrganizationOut | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [fields, setFields] = useState<AccountFieldsValue>(emptyAccountFields);
  const [memberRole, setMemberRole] = useState(false);
  const [memberStatus, setMemberStatus] = useState<string | null>(null);
  const [vault, setVault] = useState<{ currency: string; available_credit: number; transactions: { id: string; amount: number; description: string; created_at: string }[] }[]>([]);
  const [resumePlans, setResumePlans] = useState<{ id: string; name: string; price: number; currency: string; billing_type: string; cycle_length: number | null; cycle_unit: string | null; included_credits: number | null }[]>([]);
  const [currentMemberPlan, setCurrentMemberPlan] = useState<{ id: string; name: string; price: number; currency: string } | null>(null);
  const [memberChangeRequests, setMemberChangeRequests] = useState<{ id: string; request_type: string; target_plan_id: string | null; status: string; reason: string; amount_due: number; save_offer: string | null; decision_note: string | null }[]>([]);
  const [changeReason, setChangeReason] = useState("");
  const [membershipBusy, setMembershipBusy] = useState(false);
  const [paymentFlow, setPaymentFlow] = useState<{ requestId: string; clientSecret: string; amount: number; currency: string } | null>(null);
  const [paymentReady, setPaymentReady] = useState(false);
  const [recurringBilling, setRecurringBilling] = useState<{ eligible: boolean; active: boolean; cancel_at_period_end: boolean; has_payment_method: boolean; payment_method_type: string | null; status: string | null; next_renewal_at: string | null; renewal_amount: number | null; currency: string | null; cycle_length: number | null; cycle_unit: string | null } | null>(null);
  const [recurringSetup, setRecurringSetup] = useState<{ clientSecret: string } | null>(null);
  const [recurringSetupReady, setRecurringSetupReady] = useState(false);
  const paymentMountRef = useRef<HTMLDivElement>(null);
  const stripeRef = useRef<StripeInstance | null>(null);
  const elementsRef = useRef<StripeElements | null>(null);
  const paymentElementRef = useRef<StripePaymentElement | null>(null);
  const recurringSetupMountRef = useRef<HTMLDivElement>(null);
  const recurringSetupStripeRef = useRef<StripeInstance | null>(null);
  const recurringSetupElementsRef = useRef<StripeElements | null>(null);
  const recurringSetupElementRef = useRef<StripePaymentElement | null>(null);

  async function load() {
    setError("");
    try {
      const [p, o, me] = await Promise.all([
        api.get<ProfileOut>("/auth/me/profile"),
        api.get<OrganizationOut>("/organizations/me"),
        api.get<{ role?: string; member_status?: string | null }>("/auth/me"),
      ]);
      setProfile(p);
      setOrg(o);
      const isMember = me.role === "member";
      setMemberRole(isMember);
      setMemberStatus(me.member_status ?? null);
      if (isMember) {
        const [wallet, options, requests, billing] = await Promise.all([
          api.get<{ currency: string; available_credit: number; transactions: { id: string; amount: number; description: string; created_at: string }[] }[]>("/memberships/me/vault"),
          api.get<{ current_plan: typeof currentMemberPlan; plans: { id: string; name: string; price: number; currency: string; billing_type: string; cycle_length: number | null; cycle_unit: string | null; included_credits: number | null }[] }>("/memberships/me/change-options"),
          api.get<typeof memberChangeRequests>("/memberships/me/change-requests"),
          api.get<typeof recurringBilling>("/memberships/me/recurring-billing"),
        ]);
        setVault(wallet);
        setResumePlans(options.plans.filter((plan) => plan.billing_type === "recurring" && plan.price > 0 && plan.included_credits == null));
        setCurrentMemberPlan(options.current_plan);
        setMemberChangeRequests(requests);
        setRecurringBilling(billing);
      }
      setFields({
        full_name: p.full_name ?? "",
        phone: p.phone ?? "",
        address: p.address ?? "",
        city: p.city ?? "",
        occupation: p.occupation ?? "",
        education: p.education ?? "",
        emergency_contact: p.emergency_contact ?? "",
      });
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  useEffect(() => {
    if (!paymentFlow) return;
    let active = true;
    void (async () => {
      try {
        const config = await api.get<{ publishable_key: string; connected_account_id: string }>("/memberships/me/payment-config");
        await loadStripeScript();
        if (!active || !paymentMountRef.current || !window.Stripe) return;
        const stripe = window.Stripe(config.publishable_key, { stripeAccount: config.connected_account_id });
        const elements = stripe.elements({
          clientSecret: paymentFlow.clientSecret,
          appearance: { theme: "night", variables: { colorPrimary: "#d18a36", colorBackground: "#211d19", colorText: "#f2ede3", colorDanger: "#df6b63", borderRadius: "8px" } },
        });
        const paymentElement = elements.create("payment");
        paymentElement.mount(paymentMountRef.current);
        stripeRef.current = stripe; elementsRef.current = elements;
        paymentElementRef.current = paymentElement; setPaymentReady(true);
      } catch (e) { if (active) setError((e as ApiError).message || (e as Error).message); }
    })();
    return () => { active = false; paymentElementRef.current?.destroy(); paymentElementRef.current = null; elementsRef.current = null; stripeRef.current = null; setPaymentReady(false); };
  }, [paymentFlow]);

  useEffect(() => {
    if (!recurringSetup || !recurringSetupMountRef.current) return;
    let active = true;
    void (async () => {
      try {
        const config = await api.get<{ publishable_key: string; connected_account_id: string }>("/memberships/me/payment-config");
        await loadStripeScript();
        if (!active || !recurringSetupMountRef.current || !window.Stripe) return;
        const stripe = window.Stripe(config.publishable_key, { stripeAccount: config.connected_account_id });
        const elements = stripe.elements({ clientSecret: recurringSetup.clientSecret, appearance: { theme: "night", variables: { colorPrimary: "#d18a36", colorBackground: "#211d19", colorText: "#f2ede3", colorDanger: "#df6b63", borderRadius: "8px" } } });
        const element = elements.create("payment"); element.mount(recurringSetupMountRef.current);
        recurringSetupStripeRef.current = stripe; recurringSetupElementsRef.current = elements;
        recurringSetupElementRef.current = element; setRecurringSetupReady(true);
      } catch (cause) { if (active) setError((cause as ApiError).message || (cause as Error).message); }
    })();
    return () => { active = false; recurringSetupElementRef.current?.destroy(); recurringSetupElementRef.current = null; recurringSetupElementsRef.current = null; recurringSetupStripeRef.current = null; setRecurringSetupReady(false); };
  }, [recurringSetup]);

  async function finishRecurringSetup(setupIntentId: string) {
    const result = await api.post<{ retry_scheduled: boolean }>("/memberships/me/recurring-billing/confirm", { setup_intent_id: setupIntentId });
    setNotice(result.retry_scheduled
      ? "Payment method saved. Stripe will retry the overdue renewal on the next billing sweep."
      : "Recurring billing is enabled. Your saved payment method is ready for future renewals.");
    setRecurringSetup(null);
    setRecurringBilling(await api.get<typeof recurringBilling>("/memberships/me/recurring-billing"));
  }

  async function startRecurringSetup() {
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      const result = await api.post<{ client_secret: string }>("/memberships/me/recurring-billing/setup-intent", { consent: true });
      setRecurringSetup({ clientSecret: result.client_secret });
    } catch (cause) { setError((cause as ApiError).message || "Could not set up recurring billing."); }
    finally { setMembershipBusy(false); }
  }

  async function submitRecurringSetup() {
    const stripe = recurringSetupStripeRef.current; const elements = recurringSetupElementsRef.current;
    if (!stripe || !elements) return;
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      const submitted = await elements.submit();
      if (submitted.error) throw new Error(submitted.error.message || "Check the payment details.");
      const returnUrl = new URL(window.location.href); returnUrl.searchParams.set("recurring_setup", "1");
      const result = await stripe.confirmSetup({ elements, confirmParams: { return_url: returnUrl.toString() }, redirect: "if_required" });
      if (result.error) throw new Error(result.error.message || "Stripe could not save this payment method.");
      if (result.setupIntent?.status === "succeeded") await finishRecurringSetup(result.setupIntent.id);
      else setNotice("Payment-method setup is processing. We’ll enable renewals after Stripe confirms it.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the payment method."); }
    finally { setMembershipBusy(false); }
  }

  async function saveProfile() {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await api.patch("/auth/me/profile", {
        full_name: fields.full_name || null,
        phone: fields.phone || null,
        address: fields.address || null,
        city: fields.city || null,
        occupation: fields.occupation || null,
        education: fields.education || null,
        emergency_contact: fields.emergency_contact || null,
      });
      setNotice("Profile updated.");
      load();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  async function cancelMembership() {
    if (!window.confirm("Cancel at the end of your paid period? Your account stays available and eligible unused value will be added to your member vault.")) return;
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      await api.post("/memberships/me/cancel", { timing: "period_end" }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice("Cancellation scheduled. Your membership remains available until the paid period ends.");
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function requestCancellationOptions() {
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      await api.post("/memberships/me/change-requests", {
        request_type: "cancel", reason: changeReason.trim() || "Please review my cancellation and any available alternative.",
      }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice("Your cancellation request was sent to the gym. You can review and accept any pause or save offer here.");
      setChangeReason("");
      setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function resumeMembership(planId: string) {
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      const result = await api.post<{ message: string }>("/memberships/me/resume", { plan_id: planId }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice(result.message);
      setVault(await api.get<typeof vault>("/memberships/me/vault"));
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function requestPlanChange(plan: { id: string; name: string; price: number }) {
    if (!currentMemberPlan) return;
    setMembershipBusy(true); setError(""); setNotice("");
    const requestType = plan.price > currentMemberPlan.price ? "upgrade" : plan.price < currentMemberPlan.price ? "downgrade" : "transfer";
    try {
      await api.post("/memberships/me/change-requests", {
        request_type: requestType, target_plan_id: plan.id,
        reason: changeReason.trim() || `Request to change to ${plan.name}.`,
      }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice(`Your ${requestType} request was sent to the gym for review.`);
      setChangeReason("");
      setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function respondToSaveOffer(requestId: string, accept: boolean) {
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      await api.post(`/memberships/me/change-requests/${requestId}/offer-response?accept=${accept}`, undefined,
        { "Idempotency-Key": crypto.randomUUID() });
      setNotice(accept ? "The gym's save offer has been accepted." : "The cancellation will continue at the paid period end.");
      setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function startUpgradePayment(requestId: string) {
    setMembershipBusy(true); setError("");
    try {
      const result = await api.post<{ payment_required: boolean; client_secret: string | null; amount: number; currency: string }>(`/memberships/me/change-requests/${requestId}/payment-intent`);
      if (!result.payment_required || !result.client_secret) {
        setNotice("The approved plan change is complete.");
        setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
      } else setPaymentFlow({ requestId, clientSecret: result.client_secret, amount: result.amount, currency: result.currency });
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  async function confirmUpgradePayment() {
    if (!paymentFlow || !stripeRef.current || !elementsRef.current) return;
    setMembershipBusy(true); setError(""); setNotice("");
    try {
      const submitted = await elementsRef.current.submit();
      if (submitted.error) throw new Error(submitted.error.message || "Check the payment details and try again.");
      const returnUrl = new URL(window.location.href);
      returnUrl.searchParams.set("membership_change", paymentFlow.requestId);
      const confirmation = await stripeRef.current.confirmPayment({
        elements: elementsRef.current,
        confirmParams: { return_url: returnUrl.toString() },
        redirect: "if_required",
      });
      if (confirmation.error) throw new Error(confirmation.error.message || "Stripe could not confirm the payment.");
      if (confirmation.paymentIntent?.status === "succeeded") {
        await api.post(`/memberships/me/change-requests/${paymentFlow.requestId}/confirm-payment`, { payment_intent_id: confirmation.paymentIntent.id });
        setNotice("Payment confirmed. Your upgraded membership is active.");
      } else {
        setNotice("Payment submitted. Your membership will update after the payment provider confirms it.");
      }
      paymentElementRef.current?.destroy(); paymentElementRef.current = null;
      elementsRef.current = null; stripeRef.current = null; setPaymentFlow(null);
      setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
      const options = await api.get<{ current_plan: typeof currentMemberPlan; plans: typeof resumePlans }>("/memberships/me/change-options");
      setCurrentMemberPlan(options.current_plan);
    } catch (e) { setError((e as ApiError).message); }
    finally { setMembershipBusy(false); }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestId = params.get("membership_change");
    const paymentIntentId = params.get("payment_intent");
    if (!requestId || !paymentIntentId) return;
    let active = true;
    void (async () => {
      setMembershipBusy(true); setError("");
      try {
        const confirmed = await api.post<{ status?: string }>(`/memberships/me/change-requests/${requestId}/confirm-payment`, { payment_intent_id: paymentIntentId });
        if (!active) return;
        setNotice(confirmed.status === "payment_pending"
          ? "Payment is processing. Your membership updates when Stripe confirms it."
          : "Payment confirmed. Your upgraded membership is active.");
        setMemberChangeRequests(await api.get<typeof memberChangeRequests>("/memberships/me/change-requests"));
        const options = await api.get<{ current_plan: typeof currentMemberPlan; plans: typeof resumePlans }>("/memberships/me/change-options");
        setCurrentMemberPlan(options.current_plan);
      } catch (e) {
        if (active) setError((e as ApiError).message || "The payment is still processing. Membership updates after confirmation.");
      } finally {
        params.delete("membership_change"); params.delete("payment_intent");
        params.delete("payment_intent_client_secret"); params.delete("redirect_status");
        window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
        if (active) setMembershipBusy(false);
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const setupIntentId = params.get("setup_intent");
    if (params.get("recurring_setup") !== "1" || !setupIntentId) return;
    let active = true;
    void finishRecurringSetup(setupIntentId).catch((cause) => {
      if (active) setError((cause as ApiError).message || "Could not confirm recurring payment setup.");
    }).finally(() => {
      params.delete("recurring_setup"); params.delete("setup_intent"); params.delete("setup_intent_client_secret"); params.delete("redirect_status");
      window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
    });
    return () => { active = false; };
  }, []);

  if (profile === null && !error) return <Spinner label="Loading profile..." />;

  return (
    <>
      <PageHeader title="Account" subtitle="Manage your personal information" />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4 animate-slide-down"><Alert tone="success">{notice}</Alert></div>}

      <Section id="profile" title="Profile" description="Your personal details">
        <AccountFields
          value={fields}
          onChange={(patch) => setFields((v) => ({ ...v, ...patch }))}
          profile={profile}
        />
        <Row label="Password" description="We'll email you a link to choose a new one">
          <a
            href="/forgot-password"
            className="block text-sm font-medium text-brand hover:underline sm:text-right"
          >
            Reset password
          </a>
        </Row>
      </Section>

      {memberRole && <div className="mt-8">
        <Section id="member-vault" title="Membership & vault" description="Manage your membership and keep eligible unused value available for a future plan.">
          <Row label="Membership status" description="Current status shown on your member account.">
            <ReadValue>{currentMemberPlan ? `${currentMemberPlan.name} · ${titleCase(memberStatus || "active")}` : titleCase(memberStatus || "no active plan")}</ReadValue>
          </Row>
          {vault.length === 0 && <Row label="Member vault" description="Your gym-specific credit appears here when available."><ReadValue>No credit yet</ReadValue></Row>}
          {vault.map((wallet) => <Row key={wallet.currency} label={`${wallet.currency} vault`} description="Credit is stored by your gym and can fund eligible recurring plans.">
            <ReadValue>{new Intl.NumberFormat(undefined, { style: "currency", currency: wallet.currency }).format(wallet.available_credit / 100)}</ReadValue>
          </Row>)}
          {recurringBilling?.eligible && <Row label="Automatic renewal" description={`Renewal amount: ${recurringBilling.renewal_amount != null && recurringBilling.currency ? new Intl.NumberFormat(undefined, { style: "currency", currency: recurringBilling.currency }).format(recurringBilling.renewal_amount) : "see plan"}${recurringBilling.cycle_unit ? ` every ${recurringBilling.cycle_length ?? 1} ${recurringBilling.cycle_unit}${recurringBilling.cycle_length === 1 ? "" : "s"}` : ""}. Joining fees and first-term discounts do not repeat. Canceling stops the next renewal and preserves paid access through the period end.`}>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <ReadValue>{recurringBilling.cancel_at_period_end ? "Ends after paid period" : recurringBilling.status === "grace" ? (recurringBilling.has_payment_method ? "Renewal retry scheduled" : "Needs payment method") : recurringBilling.active && recurringBilling.has_payment_method ? `On${recurringBilling.payment_method_type ? ` · ${titleCase(recurringBilling.payment_method_type)}` : ""}` : "Off"}</ReadValue>
              <Button variant="secondary" loading={membershipBusy} onClick={() => void startRecurringSetup()}>{recurringBilling.has_payment_method ? "Update method" : "Set up renewals"}</Button>
            </div>
          </Row>}
          {recurringSetup && <div className="space-y-3 border border-foreground/10 p-4"><p className="text-sm font-medium">Authorize future renewals</p><p className="text-xs leading-5 text-muted-foreground">You authorize the gym to charge {recurringBilling?.renewal_amount != null && recurringBilling.currency ? new Intl.NumberFormat(undefined, { style: "currency", currency: recurringBilling.currency }).format(recurringBilling.renewal_amount) : "the recurring plan amount"} each billing period until canceled. Joining fees and first-term discounts do not repeat. Stripe securely collects any required direct-debit mandate.</p><div ref={recurringSetupMountRef} className="min-h-10 rounded border border-foreground/15 bg-background p-3" /><div className="flex justify-end gap-2"><Button variant="secondary" onClick={() => setRecurringSetup(null)}>Cancel</Button><Button loading={membershipBusy} disabled={!recurringSetupReady} onClick={() => void submitRecurringSetup()}>Save payment method</Button></div></div>}
          {!currentMemberPlan && resumePlans.length > 0 && <div className="space-y-2 py-3">{resumePlans.map((plan) => { const hasCredit = (vault.find((wallet) => wallet.currency.toLowerCase() === plan.currency.toLowerCase())?.available_credit ?? 0) > 0; return <div key={plan.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-foreground/10 py-2 text-sm"><span>{plan.name} · {new Intl.NumberFormat(undefined, { style: "currency", currency: plan.currency }).format(plan.price)} / {plan.cycle_length ?? 1} {plan.cycle_unit ?? "month"}</span><Button variant="secondary" loading={membershipBusy} disabled={!hasCredit} onClick={() => void resumeMembership(plan.id)}>{hasCredit ? "Continue with vault" : "No matching credit"}</Button></div>; })}</div>}
          {currentMemberPlan && resumePlans.length > 0 && <div className="space-y-3 border-t border-foreground/10 py-4">
            <div><p className="text-sm font-medium">Request a plan change</p><p className="mt-1 text-xs text-muted-foreground">The gym reviews changes. Any upgrade payment is prorated and only collected after approval.</p></div>
            <Input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} placeholder="Optional note for the gym" maxLength={500} />
            {resumePlans.map((plan) => <div key={`request-${plan.id}`} className="flex flex-wrap items-center justify-between gap-3 border-b border-foreground/10 py-2 text-sm"><span>{plan.name} · {new Intl.NumberFormat(undefined, { style: "currency", currency: plan.currency }).format(plan.price)} / {plan.cycle_length ?? 1} {plan.cycle_unit ?? "month"}</span><Button variant="secondary" loading={membershipBusy} onClick={() => void requestPlanChange(plan)}>Request {plan.price > currentMemberPlan.price ? "upgrade" : plan.price < currentMemberPlan.price ? "downgrade" : "transfer"}</Button></div>)}
          </div>}
          {memberChangeRequests.length > 0 && <div className="border-t border-foreground/10 py-3"><p className="mb-2 text-sm font-medium">Plan change history</p>{memberChangeRequests.slice(0, 5).map((request) => <div key={request.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-foreground/[0.06] py-2 text-xs"><span>{request.request_type} · {request.status}{request.amount_due > 0 ? ` · payment due ${new Intl.NumberFormat(undefined, { style: "currency", currency: currentMemberPlan?.currency || "USD" }).format(request.amount_due)}` : ""}</span><span className="text-muted-foreground">{request.save_offer || request.decision_note || request.reason}</span>{request.status === "payment_pending" && <Button variant="secondary" loading={membershipBusy} onClick={() => void startUpgradePayment(request.id)}>Continue to payment</Button>}{request.status === "offered" && <div className="flex gap-2"><Button variant="secondary" loading={membershipBusy} onClick={() => void respondToSaveOffer(request.id, true)}>Accept offer</Button><Button variant="danger" loading={membershipBusy} onClick={() => void respondToSaveOffer(request.id, false)}>Continue cancellation</Button></div>}</div>)}</div>}
          {paymentFlow && <div className="mt-3 space-y-3 border border-foreground/10 p-4"><p className="text-sm font-medium">Secure payment · {new Intl.NumberFormat(undefined, { style: "currency", currency: paymentFlow.currency }).format(paymentFlow.amount)}</p><p className="text-xs text-muted-foreground">Stripe shows the payment methods available for your location and this gym’s account. Payment details go directly to Stripe.</p><div ref={paymentMountRef} className="min-h-10 rounded border border-foreground/15 bg-background p-3" /><div className="flex justify-end"><Button loading={membershipBusy} disabled={!paymentReady} onClick={() => void confirmUpgradePayment()}>Continue securely</Button></div></div>}
          <Row label="Cancel membership" description="Cancel at the paid period end. Your profile and dashboard remain accessible.">
            <div className="flex flex-wrap justify-end gap-2"><Button variant="secondary" loading={membershipBusy} onClick={() => void requestCancellationOptions()}>Ask about a pause or offer</Button><Button variant="danger" loading={membershipBusy} onClick={() => void cancelMembership()}>Schedule cancellation</Button></div>
          </Row>
          {vault.some((wallet) => wallet.transactions.length > 0) && <div className="border-t border-foreground/10 py-2">{vault.flatMap((wallet) => wallet.transactions.slice(0, 5).map((entry) => <div key={entry.id} className="flex justify-between gap-4 py-2 text-xs"><span className="text-muted-foreground">{entry.description} · {new Date(entry.created_at).toLocaleDateString()}</span><span className="tabular-nums">{new Intl.NumberFormat(undefined, { style: "currency", currency: wallet.currency }).format(entry.amount / 100)}</span></div>))}</div>}
        </Section>
      </div>}

      <div className="mt-8">
        <Section id="security" title="Security" description="Protect your account">
          <MfaCard mfaRequired={org?.mfa_required ?? false} />
        </Section>
      </div>

      <div className="mt-6 flex justify-end">
        <Button onClick={saveProfile} loading={loading}>Save changes</Button>
      </div>
    </>
  );
}
