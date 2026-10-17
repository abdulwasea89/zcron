"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import { z } from "zod";
import { AuthShell } from "@/components/AuthShell";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Plan = { id: string; name: string; public_description: string | null; price: number; renewal_total: number; joining_fee: number; currency: string; billing_type: string; auto_renew: boolean; featured: boolean; cycle_length: number | null; cycle_unit: string | null };
type PaymentMount = { mount: (node: HTMLElement) => void; destroy: () => void };
type StripeElements = { create: (kind: "payment") => PaymentMount; submit: () => Promise<{ error?: { message?: string } }> };
type StripeClient = {
  elements: (options: { clientSecret: string; appearance?: Record<string, unknown> }) => StripeElements;
  confirmPayment: (options: { elements: StripeElements; confirmParams: { return_url: string }; redirect: "if_required" }) => Promise<{ error?: { message?: string }; paymentIntent?: { id: string; status: string } }>;
};
type StripeFactory = (key: string, options: { stripeAccount: string }) => StripeClient;
function stripeFactory(): StripeFactory | undefined {
  return (window as unknown as { Stripe?: StripeFactory }).Stripe;
}

const credentialsSchema = z.object({ email: z.email(), password: z.string().min(12).regex(/[a-z]/).regex(/[A-Z]/).regex(/[0-9]/).regex(/[^A-Za-z0-9]/) });

function loadStripe(): Promise<void> {
  if (stripeFactory()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[data-stripe-js="true"]');
    if (existing) { existing.addEventListener("load", () => resolve(), { once: true }); existing.addEventListener("error", () => reject(new Error("Stripe.js failed to load.")), { once: true }); return; }
    const script = document.createElement("script"); script.src = "https://js.stripe.com/v3/"; script.async = true; script.dataset.stripeJs = "true";
    script.onload = () => resolve(); script.onerror = () => reject(new Error("Stripe.js failed to load.")); document.head.appendChild(script);
  });
}

export default function JoinWorkspacePage() {
  const { orgCode } = useParams<{ orgCode: string }>();
  const router = useRouter();
  const [stage, setStage] = useState<"email" | "verify" | "password" | "plan" | "payment" | "done">("email");
  const [workspace, setWorkspace] = useState<{ organization_name: string; accepting_signups: boolean } | null>(null);
  const [email, setEmail] = useState(""); const [code, setCode] = useState(""); const [password, setPassword] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]); const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [autoRenew, setAutoRenew] = useState(false);
  const [payment, setPayment] = useState<{ clientSecret: string; amount: number; currency: string } | null>(null);
  const [message, setMessage] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [paymentReady, setPaymentReady] = useState(false);
  const paymentHost = useRef<HTMLDivElement>(null); const stripeRef = useRef<StripeClient | null>(null); const elementsRef = useRef<StripeElements | null>(null); const paymentElementRef = useRef<PaymentMount | null>(null);

  useEffect(() => {
    let active = true;
    void api.post<{ organization_name: string; accepting_signups: boolean }>("/memberships/signup/start", { org_code: orgCode })
      .then((data) => { if (active) setWorkspace(data); })
      .catch((cause) => { if (active) setError(cause instanceof ApiError ? cause.message : "Could not open this gym’s signup page."); });
    return () => { active = false; };
  }, [orgCode]);

  useEffect(() => {
    if (!payment || !paymentHost.current) return;
    let active = true;
    void (async () => {
      try {
        const config = await api.get<{ publishable_key: string; connected_account_id: string }>("/memberships/me/payment-config");
        await loadStripe(); if (!active || !paymentHost.current) return;
        const Stripe = stripeFactory(); if (!Stripe) throw new Error("Stripe.js failed to initialize.");
        const stripe = Stripe(config.publishable_key, { stripeAccount: config.connected_account_id });
        const elements = stripe.elements({ clientSecret: payment.clientSecret, appearance: { theme: "night", variables: { colorPrimary: "#d18a36", colorBackground: "#211d19", colorText: "#f2ede3", colorDanger: "#df6b63", borderRadius: "8px" } } });
        const element = elements.create("payment"); element.mount(paymentHost.current);
        stripeRef.current = stripe; elementsRef.current = elements; paymentElementRef.current = element; setPaymentReady(true);
      } catch (cause) { if (active) setError(cause instanceof ApiError ? cause.message : (cause as Error).message); }
    })();
    return () => { active = false; paymentElementRef.current?.destroy(); paymentElementRef.current = null; elementsRef.current = null; stripeRef.current = null; setPaymentReady(false); };
  }, [payment]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search); const intentId = params.get("payment_intent");
    if (params.get("signup_payment") !== "1" || !intentId) return;
    let active = true;
    void api.post<{ status: string }>("/memberships/me/signup/confirm-payment", { payment_intent_id: intentId })
      .then((result) => { if (!active) return; if (result.status === "active") { setMessage("Payment confirmed. Your membership is active."); setStage("done"); } else { setMessage("Payment is processing. Your membership activates when Stripe confirms it."); void monitorPayment(intentId); } })
      .catch((cause) => { if (active) setError(cause instanceof ApiError ? cause.message : "Could not confirm the signup payment."); })
      .finally(() => { params.delete("signup_payment"); params.delete("payment_intent"); params.delete("payment_intent_client_secret"); params.delete("redirect_status"); window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`); });
    return () => { active = false; };
  }, []);

  async function monitorPayment(intentId: string) {
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
      try {
        const result = await api.post<{ status: string }>("/memberships/me/signup/confirm-payment", { payment_intent_id: intentId });
        if (result.status === "active") {
          setMessage("Payment confirmed. Your membership is active."); setStage("done"); router.push("/app"); return;
        }
      } catch { /* Payment can still be pending while Stripe settles the method. */ }
    }
    setMessage("Payment is still pending with Stripe. You can return here or sign in later; membership activates after confirmation.");
  }

  async function requestCode(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try { const parsed = z.email().safeParse(email.trim()); if (!parsed.success) throw new Error("Enter a valid email address."); await api.post("/memberships/signup/request-email", { org_code: orgCode, email: parsed.data }); setEmail(parsed.data); setMessage(`We sent a verification code to ${parsed.data}.`); setStage("verify"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not send a verification code."); } finally { setBusy(false); }
  }
  async function verifyEmail(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try { await api.post("/memberships/signup/verify-email", { org_code: orgCode, email, code: code.replace(/\s/g, "") }); setMessage("Email verified. Create your password to continue."); setStage("password"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not verify this code."); } finally { setBusy(false); }
  }
  async function createAccount(event: FormEvent) {
    event.preventDefault(); setError(""); setBusy(true);
    try {
      const parsed = credentialsSchema.safeParse({ email, password });
      if (!parsed.success) throw new Error("Use at least 12 characters with uppercase, lowercase, a number, and a symbol.");
      const created = await api.post<{ member_status: string }>("/memberships/signup/set-password", { org_code: orgCode, email, password });
      const login = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password, org_code: orgCode }) });
      const loginData = await login.json(); if (!login.ok) throw new Error(loginData.detail || "Account created. Sign in to continue.");
      if (created.member_status === "pending_approval") { setMessage("Your application is waiting for gym approval. Plan selection opens after approval."); setStage("done"); return; }
      setPlans(await api.get<Plan[]>(`/memberships/signup/plans?org_code=${encodeURIComponent(orgCode)}`)); setStage("plan"); setMessage("Choose a plan. Stripe will show payment methods supported for your location and this gym.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create your account."); } finally { setBusy(false); }
  }
  async function preparePayment(plan: Plan) {
    setBusy(true); setError("");
    try {
      const enableRenewal = autoRenew && plan.billing_type === "recurring" && plan.auto_renew && plan.price > 0;
      const result = await api.post<{ payment_required: boolean; client_secret?: string | null; amount: number; currency: string; status: string }>("/memberships/me/signup/payment-intent", { plan_id: plan.id, auto_renew: enableRenewal });
      setSelectedPlan(plan);
      if (!result.payment_required || !result.client_secret) { setMessage("Your membership is active."); setStage("done"); router.push("/app"); return; }
      setPayment({ clientSecret: result.client_secret, amount: result.amount, currency: result.currency }); setStage("payment"); setMessage("Select a secure method offered by Stripe for this gym and currency.");
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not prepare the secure payment."); } finally { setBusy(false); }
  }
  async function pay(event: FormEvent) {
    event.preventDefault(); if (!payment || !stripeRef.current || !elementsRef.current) return;
    setBusy(true); setError("");
    try {
      const submitted = await elementsRef.current.submit(); if (submitted.error) throw new Error(submitted.error.message || "Check your payment details.");
      const returnUrl = new URL(window.location.href); returnUrl.searchParams.set("signup_payment", "1");
      const result = await stripeRef.current.confirmPayment({ elements: elementsRef.current, confirmParams: { return_url: returnUrl.toString() }, redirect: "if_required" });
      if (result.error) throw new Error(result.error.message || "Stripe could not confirm this payment.");
      if (result.paymentIntent?.status === "succeeded") {
        const confirmed = await api.post<{ status: string }>("/memberships/me/signup/confirm-payment", { payment_intent_id: result.paymentIntent.id });
        if (confirmed.status === "active") { setMessage("Payment confirmed. Your membership is active."); setStage("done"); router.push("/app"); }
        else setMessage("Payment is processing. Your membership activates when Stripe confirms it.");
      } else if (result.paymentIntent?.status === "processing") {
        setMessage("Payment is processing. Your membership activates when Stripe confirms it.");
        void monitorPayment(result.paymentIntent.id);
      } else throw new Error("Stripe has not completed the payment. Review the selected method and try again.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Payment failed. Please try again."); } finally { setBusy(false); }
  }

  const title = stage === "done" ? "You’re all set" : stage === "plan" || stage === "payment" ? "Choose your membership" : "Join your gym";
  return <AuthShell eyebrow={workspace?.organization_name || "MEMBER SIGNUP"} title={title} description={stage === "plan" || stage === "payment" ? "Your membership and payment are handled securely." : "Create your member account and get started."} footer={<a href="/login" className="auth-link">Already have an account? Sign in</a>}>
    <div className="auth-form-card space-y-4">
      {!workspace && !error && <p className="text-sm text-muted-foreground">Loading gym details…</p>}
      {workspace && !workspace.accepting_signups && <Alert>This gym is not accepting new signups right now.</Alert>}
      {error && <Alert onDismiss={() => setError("")}>{error}</Alert>}
      {message && <p role="status" className="rounded-lg border border-[var(--border)] bg-background/50 px-3 py-2 text-sm text-muted-foreground">{message}</p>}
      {stage === "email" && <form onSubmit={requestCode} className="space-y-4"><Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /><Button type="submit" loading={busy} disabled={!workspace?.accepting_signups} className="w-full">Send verification code</Button></form>}
      {stage === "verify" && <form onSubmit={verifyEmail} className="space-y-4"><Input label="Email verification code" inputMode="numeric" autoComplete="one-time-code" required maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code from your email" /><Button type="submit" loading={busy} className="w-full">Verify email</Button><button type="button" className="w-full text-sm text-muted-foreground" onClick={() => setStage("email")}>Change email</button></form>}
      {stage === "password" && <form onSubmit={createAccount} className="space-y-4"><Input label="Verified email" type="email" value={email} readOnly /><Input label="Password" type="password" autoComplete="new-password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} hint="12+ characters with uppercase, lowercase, number, and symbol." /><Button type="submit" loading={busy} className="w-full">Create member account</Button></form>}
      {stage === "plan" && <div className="space-y-3">{plans.some((plan) => plan.billing_type === "recurring" && plan.auto_renew && plan.price > 0) && <label className="flex items-start gap-3 rounded-lg border border-[var(--border)] bg-background/40 p-3 text-sm"><input type="checkbox" checked={autoRenew} onChange={(event) => setAutoRenew(event.target.checked)} className="mt-1 accent-[var(--primary)]" /><span><span className="font-medium">Enable automatic renewal (optional)</span><span className="mt-1 block text-xs leading-5 text-muted-foreground">For a recurring plan you select, you authorize the gym to charge its renewal amount shown below each billing period until canceled. Stripe securely saves the method and collects any required direct-debit mandate.</span></span></label>}{plans.length === 0 && <p className="text-sm text-muted-foreground">No public plans are available. Contact the gym for help.</p>}{plans.map((plan) => <button type="button" key={plan.id} disabled={busy} onClick={() => void preparePayment(plan)} className="w-full rounded-xl border border-[var(--border)] bg-background/50 p-4 text-left transition hover:border-[var(--primary)] hover:bg-[var(--primary-light)] disabled:opacity-60"><span className="flex items-center justify-between gap-3"><span className="font-semibold">{plan.name}</span><span className="font-semibold tabular-nums">{new Intl.NumberFormat(undefined, { style: "currency", currency: plan.currency }).format(plan.price)}{plan.billing_type === "recurring" ? ` / ${plan.cycle_length ?? 1} ${plan.cycle_unit ?? "month"}` : ""}</span></span>{plan.billing_type === "recurring" && <span className="mt-1 block text-xs text-muted-foreground">Renews at {new Intl.NumberFormat(undefined, { style: "currency", currency: plan.currency }).format(plan.renewal_total)} per period. First-term discounts and joining fees do not repeat.</span>}{plan.public_description && <span className="mt-1 block text-sm text-muted-foreground">{plan.public_description}</span>}{plan.joining_fee > 0 && <span className="mt-2 block text-xs text-muted-foreground">One-time joining fee: {new Intl.NumberFormat(undefined, { style: "currency", currency: plan.currency }).format(plan.joining_fee)}</span>}{plan.featured && <span className="mt-2 inline-block text-xs font-medium text-[var(--primary)]">Popular</span>}</button>)}<Button variant="secondary" onClick={() => setStage("password")}>Back</Button></div>}
      {stage === "payment" && payment && <form onSubmit={pay} className="space-y-4"><div className="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3"><div><p className="font-medium">{selectedPlan?.name}</p><p className="mt-1 text-xs text-muted-foreground">Payment details go directly to Stripe.</p></div><strong className="tabular-nums">{new Intl.NumberFormat(undefined, { style: "currency", currency: payment.currency }).format(payment.amount)}</strong></div><div ref={paymentHost} className="min-h-12 rounded-lg border border-[var(--border)] bg-background p-3" /><p className="text-xs leading-5 text-muted-foreground">Available methods depend on your location, plan currency, and the gym’s Stripe settings. Membership activates only after payment confirmation.</p><Button type="submit" loading={busy} disabled={!paymentReady} className="w-full">Pay securely</Button></form>}
      {stage === "done" && <div className="space-y-4"><p className="text-sm">{message}</p><Button onClick={() => router.push("/app")} className="w-full">Continue to Acron</Button></div>}
    </div>
  </AuthShell>;
}
