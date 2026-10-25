"use client";

import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";

type Performance = {
  accepted_recipients: number; attributed_payments: number; attributed_members: number;
  net_revenue_by_currency: Record<string, string>; estimated_cost: string | null;
  cost_currency: string; estimated_roi_percent: string | null; attribution_basis: string;
  payments: { id: string; member_id: string; currency: string; net_amount: string }[];
  payments_truncated: boolean;
};

export function CampaignPerformance({ campaignId }: { campaignId: string }) {
  const [data, setData] = useState<Performance | null>(null);
  const [paymentId, setPaymentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.get<Performance>(`/campaigns/${campaignId}/performance`)
      .then((value) => { if (active) setData(value); })
      .catch((cause) => { if (active) setError((cause as ApiError).message || "Could not load campaign results."); });
    return () => { active = false; };
  }, [campaignId]);
  async function change(id: string, remove = false) {
    setBusy(true); setError("");
    try {
      if (remove) await api.del(`/campaigns/${campaignId}/payments/${encodeURIComponent(id)}`);
      else await api.post(`/campaigns/${campaignId}/payments`, { payment_id: id });
      setData(await api.get<Performance>(`/campaigns/${campaignId}/performance`));
      setPaymentId(""); toast.success(remove ? "Payment link removed." : "Payment linked to this campaign.");
    } catch (cause) { setError((cause as ApiError).message || "Could not update attribution."); }
    finally { setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void change(paymentId.trim()); }
  return <section className="space-y-3 border-t border-border pt-4" aria-label="Campaign cost and conversions">
    <h3 className="text-sm font-semibold">Cost and attributed payments</h3>
    {error && <Alert>{error}</Alert>}
    {data && <>
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <div><dt className="text-xs text-muted-foreground">Accepted recipients</dt><dd>{data.accepted_recipients}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Attributed members</dt><dd>{data.attributed_members}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Estimated cost</dt><dd>{data.estimated_cost === null ? "Not provided" : money(Number(data.estimated_cost), data.cost_currency)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Estimated ROI ({data.cost_currency})</dt><dd>{data.estimated_roi_percent === null ? "Not available" : `${data.estimated_roi_percent}%`}</dd></div>
      </dl>
      {Object.entries(data.net_revenue_by_currency).map(([currency, amount]) => <p key={currency} className="text-sm">Attributed net revenue: {money(Number(amount), currency)}</p>)}
      <p className="text-xs leading-5 text-muted-foreground">{data.attribution_basis}</p>
      {data.payments.length > 0 && <ul className="divide-y divide-border">{data.payments.map((payment) => <li key={payment.id} className="flex items-center justify-between gap-2 py-2 text-xs"><span className="min-w-0 truncate">{payment.id} · {money(Number(payment.net_amount), payment.currency)}</span><Button type="button" variant="ghost" disabled={busy} onClick={() => void change(payment.id, true)}>Remove link</Button></li>)}</ul>}
      {data.payments_truncated && <p className="text-xs text-muted-foreground">Showing the latest 100 linked payments; totals include all {data.attributed_payments}.</p>}
    </>}
    <form onSubmit={submit} className="space-y-2">
      <Input label="Attribute a payment" required maxLength={128} value={paymentId} onChange={(event) => setPaymentId(event.target.value)} placeholder="Payment ID copied from Payments" />
      <p className="text-xs text-muted-foreground">Choose a payment made by a recipient after the campaign message. One payment can be linked to one campaign. This records staff attribution; it does not prove the campaign caused the sale.</p>
      <Button type="submit" variant="secondary" disabled={busy || !paymentId.trim()}>Link payment</Button>
    </form>
  </section>;
}
