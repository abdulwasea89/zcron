"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Input, Select, Spinner } from "@/components/ui";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { ApiError, api } from "@/lib/api";

type Campaign = { id: string; title: string; subject: string; body: string; channel: string; status: string; member_status: string | null; plan_id: string | null; min_days_since_last_visit: number | null; scheduled_at: string | null; sent_at: string | null; send_limit: number; sent_count: number; deliveries: number };
type CampaignOut = Omit<Campaign, "deliveries">;
type Preview = { count: number; sample: { member_id: string; name: string; email: string | null; phone: string | null; status: string }[] };
type Detail = Campaign & { deliveries: { member_id: string; member_name: string; status: string; channel: string; delivered_at: string | null; delivery_status: string | null; error: string | null }[] };
type Run = { targeted: number; sent: number; suppressed: number; failed: number };
const labels: Record<string, string> = { draft: "Draft", scheduled: "Scheduled", sending: "Sending", sent: "Sent", cancelled: "Cancelled" };
const channelLabel: Record<string, string> = { in_app: "In-app", email: "Email", both: "Email + in-app", sms: "SMS" };
const errorText = (error: unknown) => error instanceof ApiError ? error.message : "Could not load campaigns.";

export default function CampaignsPage() {
  const [rows, setRows] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [composer, setComposer] = useState(false);
  const [confirmSend, setConfirmSend] = useState(false);
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [channel, setChannel] = useState("in_app");
  const [status, setStatus] = useState("");
  const [inactiveDays, setInactiveDays] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");

  const loadRows = useCallback(async () => {
    const items = await api.get<Campaign[]>("/campaigns?limit=200");
    setRows(items);
    setSelectedId((current) => current || items[0]?.id || "");
  }, []);
  const refresh = useCallback(async () => {
    setError(""); setLoading(true);
    try { await loadRows(); }
    catch (cause) { setError(errorText(cause)); }
    finally { setLoading(false); }
  }, [loadRows]);
  useEffect(() => {
    let cancelled = false;
    api.get<Campaign[]>("/campaigns?limit=200").then((items) => {
      if (!cancelled) { setRows(items); setSelectedId(items[0]?.id || ""); }
    }).catch((cause: unknown) => { if (!cancelled) setError(errorText(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    Promise.all([
      api.get<Detail>(`/campaigns/${selectedId}?limit=100`),
      api.get<Preview>(`/campaigns/preview/${selectedId}?limit=8`).catch(() => null),
    ]).then(([campaign, audience]) => { if (!cancelled) { setDetail(campaign); setPreview(audience); } })
      .catch((cause: unknown) => { if (!cancelled) setError(errorText(cause)); });
    return () => { cancelled = true; };
  }, [selectedId]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      const schedule = scheduleAt ? new Date(scheduleAt) : null;
      if (schedule && schedule <= new Date()) throw new Error("Choose a future schedule time.");
      const created = await api.post<CampaignOut>("/campaigns", {
        title: title.trim(), subject: subject.trim(), body: body.trim(), channel,
        member_status: status || null, min_days_since_last_visit: inactiveDays ? Number(inactiveDays) : null,
        scheduled_at: schedule?.toISOString() ?? null, send_limit: 200,
      });
      setComposer(false); setTitle(""); setSubject(""); setBody(""); setStatus(""); setInactiveDays(""); setScheduleAt("");
      await loadRows(); setSelectedId(created.id); toast.success(created.scheduled_at ? "Campaign scheduled." : "Campaign draft saved.");
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not create campaign."); }
    finally { setBusy(false); }
  }
  async function refreshPreview() {
    if (!selectedId) return; setBusy(true);
    try { setPreview(await api.get<Preview>(`/campaigns/preview/${selectedId}?limit=8`)); }
    catch (cause) { toast.error(errorText(cause)); }
    finally { setBusy(false); }
  }
  async function send() {
    if (!selectedId) return; setBusy(true);
    try {
      const result = await api.post<Run>(`/campaigns/${selectedId}/send`);
      toast.success(`Finished: ${result.sent} sent, ${result.suppressed} suppressed, ${result.failed} failed.`);
      setConfirmSend(false); await loadRows();
      setDetail(await api.get<Detail>(`/campaigns/${selectedId}?limit=100`));
    } catch (cause) { toast.error(errorText(cause)); }
    finally { setBusy(false); }
  }
  async function cancel() {
    if (!selectedId) return; setBusy(true);
    try {
      await api.post(`/campaigns/${selectedId}/cancel`); toast.success("Campaign cancelled.");
      await loadRows(); setDetail(await api.get<Detail>(`/campaigns/${selectedId}?limit=100`));
    } catch (cause) { toast.error(errorText(cause)); }
    finally { setBusy(false); }
  }

  return <>
    <PageHeader title="Campaigns" subtitle="Send consent-aware updates to a member segment and review delivery outcomes." action={<Button onClick={() => setComposer((open) => !open)}>{composer ? "Close composer" : "New campaign"}</Button>} />
    {composer && <form onSubmit={create} className="mb-6 border border-[var(--border)] bg-card p-4 sm:p-5">
      <h2 className="text-sm font-semibold text-foreground">Create a campaign</h2>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">Saving creates a draft. Nothing is sent until you preview the audience and confirm. Members without consent for the chosen channel are excluded.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Input label="Campaign name" required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} />
        <Select label="Channel" value={channel} onChange={(e) => setChannel(e.target.value)}><option value="in_app">In-app</option><option value="email">Email</option><option value="both">Email + in-app</option><option value="sms">SMS (consenting members only)</option></Select>
        <Select label="Member status" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Active, grace, or frozen</option><option value="active">Active</option><option value="grace">Grace</option><option value="frozen">Frozen</option><option value="active,grace">Active or grace</option></Select>
        <Input label="Inactive for at least (days)" type="number" min={1} max={3650} value={inactiveDays} onChange={(e) => setInactiveDays(e.target.value)} />
        <Input label="Message title / email subject" required maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
        <Input label="Schedule for (optional)" type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} />
        <label className="text-xs font-medium text-muted-foreground sm:col-span-2">Message<textarea required maxLength={2000} rows={4} value={body} onChange={(e) => setBody(e.target.value)} className="mt-1.5 block w-full resize-y rounded-md border border-foreground/15 bg-background px-3 py-2 text-sm text-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20" /></label>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted-foreground">Maximum 200 recipients per run · consent checked at delivery time.</p><Button type="submit" loading={busy}>Save campaign</Button></div>
    </form>}
    {error && <div className="mb-4"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-2" onClick={() => void refresh()}>Try again</Button></div>}
    {loading ? <div className="flex justify-center border border-[var(--border)] bg-card p-10"><Spinner label="Loading campaigns…" /></div> : <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section className="border border-[var(--border)] bg-card"><header className="border-b border-[var(--border)] px-4 py-3"><h2 className="text-sm font-semibold text-foreground">Campaign history</h2><p className="mt-1 text-xs text-muted-foreground">{rows.length} saved</p></header>
        {rows.length ? <ul className="divide-y divide-[var(--border)]">{rows.map((item) => <li key={item.id}><button type="button" onClick={() => setSelectedId(item.id)} aria-pressed={selectedId === item.id} className={`w-full px-4 py-3 text-left hover:bg-foreground/[0.03] ${selectedId === item.id ? "bg-foreground/[0.04]" : ""}`}><span className="flex items-center justify-between gap-3"><span className="truncate text-sm font-medium text-foreground">{item.title}</span><Badge tone={item.status === "sent" ? "success" : item.status === "cancelled" ? "neutral" : "warning"}>{labels[item.status] ?? item.status}</Badge></span><span className="mt-1 block text-xs text-muted-foreground">{channelLabel[item.channel] ?? item.channel} · {item.deliveries} delivery records{item.sent_at ? ` · ${new Date(item.sent_at).toLocaleDateString()}` : ""}</span></button></li>)}</ul> : <p className="px-4 py-6 text-sm text-muted-foreground">No campaigns yet. Create a draft for opted-in members.</p>}
      </section>
      <section className="min-w-0 border border-[var(--border)] bg-card">{!detail ? <p className="p-6 text-sm text-muted-foreground">Choose a campaign to review its audience and delivery history.</p> : <>
        <header className="border-b border-[var(--border)] px-4 py-3"><div className="flex items-center gap-2"><h2 className="text-sm font-semibold text-foreground">{detail.title}</h2><Badge tone={detail.status === "sent" ? "success" : detail.status === "cancelled" ? "neutral" : "warning"}>{labels[detail.status] ?? detail.status}</Badge></div><p className="mt-1 text-xs text-muted-foreground">{channelLabel[detail.channel] ?? detail.channel} · up to {detail.send_limit} recipients</p></header>
        <div className="space-y-5 p-4"><div><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Message</p><p className="mt-1 text-sm font-medium text-foreground">{detail.subject}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{detail.body}</p></div>
          {detail.status === "draft" || detail.status === "scheduled" ? <div className="border-t border-[var(--border)] pt-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold text-foreground">Audience preview</h3><p className="mt-1 text-xs text-muted-foreground">{preview ? `${preview.count} eligible members match now` : "Refresh before sending to check recipients."}</p></div><Button variant="secondary" loading={busy} onClick={() => void refreshPreview()}>Preview audience</Button></div>
            {preview && <ul className="mt-3 divide-y divide-[var(--border)] border-y border-[var(--border)]">{preview.sample.map((member) => <li key={member.member_id} className="flex justify-between gap-3 py-2 text-xs"><span className="truncate font-medium text-foreground">{member.name}</span><span className="text-muted-foreground">{detail.channel === "sms" ? member.phone || "No phone" : member.email || member.status}</span></li>)}{preview.count > preview.sample.length && <li className="py-2 text-xs text-muted-foreground">and {preview.count - preview.sample.length} more</li>}</ul>}
            <div className="mt-4 flex justify-end gap-2">{detail.status === "scheduled" && <Button variant="secondary" loading={busy} onClick={() => void cancel()}>Cancel schedule</Button>}<Button disabled={!preview || preview.count === 0} loading={busy} onClick={() => setConfirmSend(true)}>Send campaign now</Button></div>
          </div> : <div className="border-t border-[var(--border)] pt-4"><h3 className="text-sm font-semibold text-foreground">Delivery outcomes</h3><div className="mt-3 grid grid-cols-2 gap-px bg-[var(--border)] sm:grid-cols-5">{[["Records", detail.deliveries.length], ["Sent", detail.deliveries.filter((r) => r.status === "sent").length], ["SMS delivered", detail.deliveries.filter((r) => r.delivery_status === "delivered").length], ["Suppressed", detail.deliveries.filter((r) => r.status === "suppressed").length], ["Failed", detail.deliveries.filter((r) => r.status === "failed").length]].map(([label, count]) => <div key={String(label)} className="bg-card px-3 py-2"><p className="text-[10px] text-muted-foreground">{label}</p><p className="mt-1 text-sm font-semibold tabular-nums text-foreground">{count}</p></div>)}</div>
            {!!detail.deliveries.length && <ul className="mt-3 max-h-64 divide-y divide-[var(--border)] overflow-y-auto border-y border-[var(--border)]">{detail.deliveries.map((delivery) => { const status = delivery.delivery_status || delivery.status; return <li key={delivery.member_id} className="flex items-start justify-between gap-3 py-2 text-xs"><span className="min-w-0"><span className="block truncate font-medium text-foreground">{delivery.member_name}</span>{status === "failed" && <span className="mt-0.5 block text-danger">{delivery.error || "Delivery failed. Check the channel configuration."}</span>}</span><Badge tone={status === "delivered" || status === "sent" ? "success" : status === "failed" ? "danger" : "neutral"}>{status.replaceAll("_", " ")}</Badge></li>; })}</ul>}</div>}
        </div>
      </>}</section>
    </div>}
    <AlertDialog open={confirmSend} onOpenChange={setConfirmSend}><AlertDialogContent><AlertDialogTitle>Send this campaign now?</AlertDialogTitle><AlertDialogDescription>This delivers “{detail?.subject}” to up to {Math.min(preview?.count ?? 0, detail?.send_limit ?? 200)} eligible members. Channel consent is checked again at delivery time.{detail?.channel === "sms" ? " Your Twilio account may charge for each accepted text." : ""}</AlertDialogDescription><AlertDialogFooter><AlertDialogCancel asChild><Button variant="secondary">Review again</Button></AlertDialogCancel><AlertDialogAction asChild><Button loading={busy} onClick={(event) => { event.preventDefault(); void send(); }}>Send campaign</Button></AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>;
}
