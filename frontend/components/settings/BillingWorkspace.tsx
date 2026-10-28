"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, EmptyState, Spinner } from "@/components/ui";
import { ListToolbar } from "@/components/ListToolbar";
import { ReadValue, Row, Section, SectionBody, SubHeading } from "@/components/settings/primitives";
import { api, ApiError } from "@/lib/api";
import { money, statusTone, titleCase } from "@/lib/format";
import type { InvoiceOut, SaasStatusOut } from "@/lib/types";

type VaultOut = { currency: string; available_credit: number; has_more: boolean; transactions: { id: string; amount: number; currency: string; created: number; description: string; type: string }[] };
type SubscriptionOut = { cancel_at_period_end: boolean; stripe_status: string | null; period_end: string | null; scheduled_tier: string | null };
type InvoicePageOut = { items: InvoiceOut[]; has_more: boolean };

export function BillingWorkspace({ embedded = false }: { embedded?: boolean }) {
  const [status, setStatus] = useState<SaasStatusOut | null>(null);
  const [invoices, setInvoices] = useState<InvoiceOut[] | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [portalBusy, setPortalBusy] = useState(false);
  const [invoiceSearch, setInvoiceSearch] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("all");
  const [invoiceHasMore, setInvoiceHasMore] = useState(false);
  const [invoiceBusy, setInvoiceBusy] = useState(false);
  const [vault, setVault] = useState<VaultOut | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionOut | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError("");
    try {
      const [s, inv] = await Promise.all([
        api.get<SaasStatusOut>("/saas-billing/status"),
        api.get<InvoicePageOut>("/saas-billing/invoices"),
      ]);
      setStatus(s);
      setInvoices(inv.items);
      setInvoiceHasMore(inv.has_more);
      const [v, sub] = await Promise.allSettled([
        api.get<VaultOut>("/saas-billing/vault"),
        api.get<SubscriptionOut>("/saas-billing/subscription"),
      ]);
      if (v.status === "fulfilled") setVault(v.value);
      if (sub.status === "fulfilled") setSubscription(sub.value);
    } catch (e) {
      setError((e as ApiError).message);
      setInvoices([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("session_id");
    if (params.get("billing") !== "success" || !sessionId) return;
    let active = true;
    void api.post("/saas-billing/confirm", { session_id: sessionId })
      .then(() => { if (active) { setError(""); setNotice("Your subscription is active and your Stripe credit was applied where available."); void load(); } })
      .catch((e) => { if (active) setError((e as ApiError).message); })
      .finally(() => { params.delete("billing"); params.delete("session_id"); window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`); });
    return () => { active = false; };
  }, []);

  async function changeTier(tier: "starter" | "pro") {
    setBusy(true); setError(""); setNotice("");
    try {
      const higher = tier === "pro";
      await api.post(`/saas-billing/${higher ? "upgrade" : "downgrade"}`, { tier }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice(`Your ${tier === "pro" ? "Pro" : "Starter"} plan is active. Stripe applied any prorated balance.`);
      await load();
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function cancelPlan(timing: "now" | "period_end") {
    const prompt = timing === "now"
      ? "Cancel now? Stripe will calculate any unused subscription value and keep eligible credit on your billing account."
      : "Schedule cancellation for the end of your paid period? Your dashboard remains available until then.";
    if (!window.confirm(prompt)) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.post<{ message: string }>("/saas-billing/cancel", { timing }, { "Idempotency-Key": crypto.randomUUID() });
      setNotice(result.message); await load();
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function resumePlan() {
    setBusy(true); setError("");
    try {
      const result = await api.post<{ message: string; checkout_url: string | null }>("/saas-billing/resume", {}, { "Idempotency-Key": crypto.randomUUID() });
      if (result.checkout_url) window.location.assign(result.checkout_url);
      else { setNotice(result.message); await load(); }
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  async function cancelScheduledDowngrade() {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api.post<{ message: string }>("/saas-billing/schedule/cancel", {}, { "Idempotency-Key": crypto.randomUUID() });
      setNotice(result.message); await load();
    } catch (e) { setError((e as ApiError).message); }
    finally { setBusy(false); }
  }

  const allInvoices = invoices ?? [];

  const invoiceTabs = [
    { value: "all", label: "All", count: allInvoices.length },
    ...Array.from(new Set(allInvoices.map((i) => i.status))).map((s) => ({
      value: s,
      label: titleCase(s),
      count: allInvoices.filter((i) => i.status === s).length,
    })),
  ];

  const invoiceQ = invoiceSearch.trim().toLowerCase();
  const filteredInvoices = allInvoices.filter((i) => {
    if (invoiceStatus !== "all" && i.status !== invoiceStatus) return false;
    if (!invoiceQ) return true;
    return i.status.toLowerCase().includes(invoiceQ) || new Date(i.created_at).toLocaleDateString().toLowerCase().includes(invoiceQ);
  });

  async function openPortal() {
    setError("");
    setPortalBusy(true);
    try {
      const result = await api.post<{ url: string }>("/saas-billing/portal", {});
      window.location.assign(result.url);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setPortalBusy(false);
    }
  }

  async function loadMoreInvoices() {
    if (!invoices?.length || invoiceBusy) return;
    setInvoiceBusy(true);
    try {
      const params = new URLSearchParams({ starting_after: invoices[invoices.length - 1].id });
      const page = await api.get<InvoicePageOut>(`/saas-billing/invoices?${params}`);
      setInvoices((current) => [...(current ?? []), ...page.items]);
      setInvoiceHasMore(page.has_more);
    } catch (e) {
      setError((e as ApiError).message || "Could not load older invoices.");
    } finally {
      setInvoiceBusy(false);
    }
  }

  const body = status && (
    <>
      <Row label="Manage billing" description="Update your payment method and billing details securely in Stripe.">
        <Button variant="secondary" loading={portalBusy} onClick={openPortal}>Open billing portal</Button>
      </Row>
      <Row label="Current tier" description="Your SaaS plan">
        <div className="flex items-center justify-end gap-2">
          <span className="text-sm font-medium text-foreground">{titleCase(status.saas_tier)}</span>
          <Badge tone={statusTone(status.saas_status)}>{titleCase(status.saas_status)}</Badge>
        </div>
      </Row>
      <Row label="Members" description="Active members against your seat cap">
        <ReadValue>
          {status.current_member_count}
          {status.member_cap !== null ? ` / ${status.member_cap}` : " / Unlimited"}
        </ReadValue>
      </Row>
      <Row label="Renews" description="Next billing date">
        <ReadValue>
          {status.current_period_end ? new Date(status.current_period_end).toLocaleDateString() : "—"}
        </ReadValue>
      </Row>

      {status.saas_status === "past_due" && (
        <Row
          label="Payment failed"
          description={
            status.retry_count > 0
              ? `Stripe has retried ${status.retry_count} time${status.retry_count === 1 ? "" : "s"}. Grace ends ${status.grace_until ? new Date(status.grace_until).toLocaleDateString() : "soon"}.`
              : "Update your card to resume normal service."
          }
        >
          <div className="flex justify-end">
            <Button variant="secondary" loading={portalBusy} onClick={openPortal}>Update card</Button>
          </div>
        </Row>
      )}
      {status.saas_status === "read_only" && (
        <Row label="Read-only mode" description="Write access is blocked until the subscription is renewed.">
          <div className="flex justify-end"><Badge tone="warning">Limited</Badge></div>
        </Row>
      )}
      {status.saas_status === "suspended" && (
        <Row label="Account suspended" description="Contact support to restore access.">
          <div className="flex justify-end"><Badge tone="danger">Suspended</Badge></div>
        </Row>
      )}
      {status.saas_status === "cancelled" && (
        <Row label="Subscription cancelled" description="Your workspace remains readable. Resume with your Stripe billing credit applied to the next invoice.">
          <div className="flex justify-end"><Button loading={busy} onClick={resumePlan}>Resume plan</Button></div>
        </Row>
      )}

      <div className="pt-4">
        <SubHeading>Subscription plan</SubHeading>
        <p className="mt-1 text-[12px] leading-5 text-muted-foreground">Upgrade immediately with Stripe proration, or move to a lower tier at the current billing period boundary.</p>
      </div>
      <div className="grid gap-3 py-2 sm:grid-cols-2">
        {([{ tier: "starter" as const, price: "$29", seats: "Up to 25 active members" }, { tier: "pro" as const, price: "$79", seats: "Up to 100 active members" }]).map((plan) => {
          const selected = status.saas_tier === plan.tier;
          return <div key={plan.tier} className={`border p-4 ${selected ? "border-brand/70 bg-brand/[0.05]" : "border-foreground/10"}`}>
            <div className="flex items-center justify-between"><strong>{titleCase(plan.tier)}</strong><span className="tabular-nums">{plan.price}<small className="text-muted-foreground"> / month</small></span></div>
            <p className="mt-1 text-xs text-muted-foreground">{plan.seats}</p>
            <div className="mt-3 flex justify-end">{selected ? <Badge tone="info">Current</Badge> : <Button variant="secondary" loading={busy} disabled={status.saas_status !== "active" || !!subscription?.scheduled_tier || !!subscription?.cancel_at_period_end} onClick={() => void changeTier(plan.tier)}>{plan.tier === "pro" ? "Upgrade now" : "Downgrade at renewal"}</Button>}</div>
          </div>;
        })}
      </div>
      {subscription?.scheduled_tier && <Row label="Scheduled plan change" description={`${titleCase(subscription.scheduled_tier)} starts ${subscription.period_end ? new Date(subscription.period_end).toLocaleDateString() : "at the next billing period"}. Your current tier stays active until then.`}>
        <Button variant="secondary" loading={busy} onClick={() => void cancelScheduledDowngrade()}>Keep current plan</Button>
      </Row>}
      <Row label="Credit vault" description="Stripe keeps eligible billing credit on this workspace and applies it to future invoices.">
        <ReadValue>{vault ? money(vault.available_credit / 100, vault.currency) : "Loading…"}</ReadValue>
      </Row>
      {vault?.transactions?.length ? <div className="border-y border-foreground/10 py-2">
        {vault.transactions.slice(0, 5).map((tx) => <div key={tx.id} className="flex justify-between gap-4 py-2 text-xs"><span className="text-muted-foreground">{tx.description} · {new Date(tx.created * 1000).toLocaleDateString()}</span><span className="tabular-nums">{money(tx.amount / 100, tx.currency)}</span></div>)}
      </div> : null}
      <Row label="Cancellation" description={subscription?.cancel_at_period_end ? `Scheduled for ${subscription.period_end ? new Date(subscription.period_end).toLocaleDateString() : "period end"}. You keep access through the paid period.` : "Cancel now with Stripe-calculated remaining credit, or keep access until the billing period ends."}>
        <div className="flex flex-wrap justify-end gap-2">{subscription?.cancel_at_period_end ? <Button variant="secondary" loading={busy} onClick={() => void resumePlan()}>Keep my plan</Button> : status.saas_status === "active" ? <><Button variant="secondary" loading={busy} onClick={() => void cancelPlan("period_end")}>Cancel at renewal</Button><Button variant="danger" loading={busy} onClick={() => void cancelPlan("now")}>Cancel now</Button></> : null}</div>
      </Row>

      <div className="py-4">
        <SubHeading>Invoices</SubHeading>
        <ListToolbar
          tabs={invoiceTabs}
          value={invoiceStatus}
          onChange={setInvoiceStatus}
          search={invoiceSearch}
          onSearch={setInvoiceSearch}
          searchPlaceholder="Search invoices…"
        />
        {/* Table surface: hairline border, square corners, flat background. */}
        <div className="mt-3 border border-foreground/10 bg-card">
          {invoices === null ? (
            <Spinner label="Loading invoices..." />
          ) : filteredInvoices.length === 0 ? (
            <EmptyState
              title="No invoices yet"
              hint={
                invoices.length === 0
                  ? "Your invoices will appear here."
                  : "No invoices match the current filter."
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left font-mono text-[10px] font-medium uppercase tracking-widest text-[var(--muted-foreground)]">
                  <tr className="border-b border-foreground/10">
                    <th className="px-5 py-3">Date</th>
                    <th className="px-5 py-3">Amount</th>
                    <th className="px-5 py-3">Status</th>
                    <th className="px-5 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-foreground/[0.06]">
                  {filteredInvoices.map((inv) => (
                    <tr key={inv.id} className="transition-colors hover:bg-[var(--background)]">
                      <td className="px-5 py-3.5">{new Date(inv.created_at).toLocaleDateString()}</td>
                      <td className="px-5 py-3.5 tabular-nums font-medium">{money(inv.amount, inv.currency)}</td>
                      <td className="px-5 py-3.5">
                        <Badge tone={statusTone(inv.status)}>{titleCase(inv.status)}</Badge>
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        {inv.source === "local" || inv.invoice_pdf_url ? <a
                          href={inv.source === "stripe" ? inv.invoice_pdf_url! : `/api/download/saas-billing/invoices/${inv.id}/pdf`}
                          download={inv.source === "local"}
                          target={inv.source === "stripe" ? "_blank" : undefined}
                          rel={inv.source === "stripe" ? "noopener noreferrer" : undefined}
                          className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--primary)] hover:underline"
                        >
                          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                          </svg>
                          PDF
                        </a> : <span className="text-xs text-muted-foreground">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {invoiceHasMore && <div className="flex justify-center pt-3"><Button variant="secondary" loading={invoiceBusy} onClick={() => void loadMoreInvoices()}>Load older invoices</Button></div>}
      </div>
    </>
  );

  if (embedded) {
    return (
      <>
        {error && <div className="mb-4"><Alert>{error}</Alert></div>}
        {notice && <div className="mb-4"><Alert tone="success">{notice}</Alert></div>}
        {status === null ? (
          <Spinner label="Loading billing info..." />
        ) : (
          <Section id="billing" title="Subscription" description="Your platform plan and invoices">
            {body}
          </Section>
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader title="Billing" subtitle="Your platform subscription & invoices" />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="success">{notice}</Alert></div>}
      {status === null ? (
        <Spinner label="Loading billing info..." />
      ) : (
        <SectionBody>{body}</SectionBody>
      )}
    </>
  );
}
