"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

type LapsedMember = {
  member_id: string;
  name: string | null;
  status: string;
  last_visit_at: string | null;
  days_since_last_visit: number | null;
  win_back_status: string | null;
  contacted_at: string | null;
  can_contact: boolean;
  email_opt_in: boolean;
  in_app_opt_in: boolean;
};
type WinBackSummary = {
  lapsed: number;
  contacted: number;
  recovered: number;
  recovery_rate: number;
  recovered_revenue: number;
};
type Celebration = { member_id: string; name: string | null; kind: string; on: string; days_away: number; detail: string | null };
type RecentCelebration = { member_id: string; name: string | null; kind: string; key: string; title: string; sent_at: string };
type CampaignResult = { targeted: number; sent: number };

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : "—";
}

export function RetentionWinBackPanel() {
  const [members, setMembers] = useState<LapsedMember[]>([]);
  const [summary, setSummary] = useState<WinBackSummary | null>(null);
  const [upcoming, setUpcoming] = useState<Celebration[]>([]);
  const [recent, setRecent] = useState<RecentCelebration[]>([]);
  const [offer, setOffer] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const eligible = members.filter((member) => member.can_contact).length;

  const fetchData = useCallback(() => Promise.all([
        api.get<LapsedMember[]>("/win-back/lapsed"),
        api.get<WinBackSummary>("/win-back/summary"),
        api.get<Celebration[]>("/celebrations/upcoming?days=30"),
        api.get<RecentCelebration[]>("/celebrations/recent?limit=8"),
      ]), []);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [lapsed, totals, celebrations, history] = await fetchData();
      setMembers(lapsed);
      setSummary(totals);
      setUpcoming(celebrations);
      setRecent(history);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load win-back activity.");
    } finally {
      setLoading(false);
    }
  }, [fetchData]);

  useEffect(() => {
    let cancelled = false;
    fetchData().then(([lapsed, totals, celebrations, history]) => {
      if (cancelled) return;
      setMembers(lapsed);
      setSummary(totals);
      setUpcoming(celebrations);
      setRecent(history);
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof ApiError ? cause.message : "Could not load win-back activity.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchData]);

  async function runCampaign() {
    if (!eligible || !window.confirm(`Send a win-back message to ${eligible} lapsed member${eligible === 1 ? "" : "s"} who opted in?`)) return;
    setBusy(true);
    try {
      const result = await api.post<CampaignResult>("/win-back/campaign", {
        offer_text: offer.trim() || null,
        cooldown_days: 30,
        limit: 200,
      });
      if (result.sent) toast.success(`Sent to ${result.sent} of ${result.targeted} eligible members.`);
      else toast.error("No messages were delivered. Check channel setup and try again.");
      await load();
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : "Could not send win-back messages.");
    } finally {
      setBusy(false);
    }
  }

  async function closeAttempt(member: LapsedMember) {
    setBusy(true);
    try {
      await api.post(`/win-back/members/${encodeURIComponent(member.member_id)}/lost`, {});
      toast.success("Win-back attempt closed.");
      await load();
    } catch (cause) {
      toast.error(cause instanceof ApiError ? cause.message : "Could not close this attempt.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div className="flex justify-center border border-[var(--border)] bg-card p-10"><Spinner label="Loading win-back and celebrations…" /></div>;
  if (error) return <div role="alert" className="border border-[var(--border)] bg-card p-5"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-3" onClick={() => { setLoading(true); void load(); }}>Try again</Button></div>;

  return <div className="space-y-6">
    <section className="border border-[var(--border)] bg-card">
      <header className="border-b border-[var(--border)] px-4 py-3 sm:px-5"><h2 className="text-sm font-semibold text-foreground">Win-back</h2><p className="mt-1 text-xs text-muted-foreground">Re-engage lapsed members only through channels they opted into.</p></header>
      <div className="grid grid-cols-2 gap-px border-b border-[var(--border)] bg-[var(--border)] sm:grid-cols-4">
        {[["Lapsed", summary?.lapsed ?? 0], ["Contacted", summary?.contacted ?? 0], ["Recovered", summary?.recovered ?? 0], ["Recovered revenue", (summary?.recovered_revenue ?? 0).toLocaleString()]].map(([label, value]) => <div key={String(label)} className="bg-card px-4 py-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{value}</p></div>)}
      </div>
      <div className="space-y-3 p-4 sm:p-5">
        <label className="block text-xs font-medium text-foreground">Optional offer message
          <textarea value={offer} onChange={(event) => setOffer(event.target.value)} maxLength={1000} rows={3} placeholder="Leave blank to use the standard win-back message." className="mt-1.5 block w-full resize-y border border-[var(--border)] bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-brand" />
        </label>
        <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted-foreground">{eligible} eligible · consented members outside the 30-day cooldown</p><Button disabled={busy || eligible === 0} loading={busy} onClick={() => void runCampaign()}>Send win-back</Button></div>
      </div>
      {members.length ? <ul className="divide-y divide-[var(--border)] border-t border-[var(--border)]">{members.map((member) => <li key={member.member_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <div className="min-w-0"><a href={`/app/members?member=${encodeURIComponent(member.member_id)}`} className="text-sm font-medium text-foreground underline-offset-4 hover:underline">{member.name || "Member"}</a><p className="mt-1 text-xs text-muted-foreground">Last visit {member.days_since_last_visit == null ? "not recorded" : `${member.days_since_last_visit} days ago`} · Last contacted {dateLabel(member.contacted_at)}</p><div className="mt-1 flex flex-wrap gap-1.5">{member.email_opt_in && <Badge tone="neutral">Email opted in</Badge>}{member.in_app_opt_in && <Badge tone="neutral">In-app opted in</Badge>}{member.can_contact ? <Badge tone="success">Eligible</Badge> : <Badge tone="neutral">No consent or cooling down</Badge>}</div></div>
        {member.win_back_status === "contacted" && <Button variant="secondary" disabled={busy} onClick={() => void closeAttempt(member)}>Close attempt</Button>}
      </li>)}</ul> : <p className="border-t border-[var(--border)] px-4 py-5 text-sm text-muted-foreground sm:px-5">No lapsed members right now.</p>}
    </section>

    <section className="grid gap-6 lg:grid-cols-2">
      <div className="border border-[var(--border)] bg-card"><header className="border-b border-[var(--border)] px-4 py-3 sm:px-5"><h2 className="text-sm font-semibold text-foreground">Coming up</h2><p className="mt-1 text-xs text-muted-foreground">Birthdays and membership anniversaries in the next 30 days.</p></header>
        {upcoming.length ? <ul className="divide-y divide-[var(--border)]">{upcoming.map((item) => <li key={`${item.member_id}:${item.kind}:${item.on}`} className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5"><div><p className="text-sm font-medium text-foreground">{item.name || "Member"}</p><p className="text-xs capitalize text-muted-foreground">{item.kind.replaceAll("_", " ")}{item.detail ? ` · ${item.detail}` : ""}</p></div><p className="shrink-0 text-right text-xs text-muted-foreground">{item.days_away === 0 ? "Today" : `In ${item.days_away} days`}<br />{dateLabel(item.on)}</p></li>)}</ul> : <p className="px-4 py-5 text-sm text-muted-foreground sm:px-5">No celebrations in the next 30 days.</p>}
      </div>
      <div className="border border-[var(--border)] bg-card"><header className="border-b border-[var(--border)] px-4 py-3 sm:px-5"><h2 className="text-sm font-semibold text-foreground">Recently celebrated</h2><p className="mt-1 text-xs text-muted-foreground">Birthdays, anniversaries and visit milestones.</p></header>
        {recent.length ? <ul className="divide-y divide-[var(--border)]">{recent.map((item) => <li key={`${item.member_id}:${item.kind}:${item.key}`} className="flex items-center justify-between gap-3 px-4 py-3 sm:px-5"><div><p className="text-sm font-medium text-foreground">{item.title}</p><p className="text-xs text-muted-foreground">{item.name || "Member"} · {item.kind.replaceAll("_", " ")}</p></div><time className="shrink-0 text-xs text-muted-foreground">{dateLabel(item.sent_at)}</time></li>)}</ul> : <p className="px-4 py-5 text-sm text-muted-foreground sm:px-5">No celebrations have been sent yet.</p>}
      </div>
    </section>
  </div>;
}
