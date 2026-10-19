"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert, Badge, Button, Input, Spinner } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { ApiError, api } from "@/lib/api";

type Rung = {
  day: number; code: string; name: string; member_action: string | null; staff_action: string | null;
  is_active: boolean; due: boolean; fired_at: string | null; status: "fired" | "completed" | "skipped" | null; channel: string | null;
};
type LadderMember = { member_id: string; name: string | null; status: string; days_inactive: number | null; rungs: Rung[] };
type RungConfig = Omit<Rung, "due" | "fired_at" | "status" | "channel"> & { email_subject: string | null; email_body: string | null };
type Filter = "follow_up" | "all" | "upcoming";
type RungDraft = Pick<RungConfig, "member_action" | "staff_action" | "email_subject" | "email_body" | "is_active">;

const errorText = (cause: unknown) => cause instanceof ApiError ? cause.message : "Could not load the inactivity ladder.";
const dateTime = (value: string | null) => value ? new Date(value).toLocaleString() : "";

function Metric({ label, value, warning = false }: { label: string; value: number; warning?: boolean }) {
  return <div className="border border-[var(--border)] bg-card px-4 py-4 sm:px-5"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className={`mt-1 text-2xl font-semibold tabular-nums ${warning ? "text-warning" : "text-foreground"}`}>{value}</p></div>;
}

export function InactivityLadderPanel() {
  const user = useCurrentUser();
  const isOwner = user?.role === "owner";
  const [members, setMembers] = useState<LadderMember[]>([]);
  const [config, setConfig] = useState<RungConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("follow_up");
  const [query, setQuery] = useState("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [editing, setEditing] = useState<RungConfig | null>(null);
  const [draft, setDraft] = useState<RungDraft | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [nextMembers, nextConfig] = await Promise.all([
        api.get<LadderMember[]>("/inactivity-ladder/roster"),
        api.get<RungConfig[]>("/inactivity-ladder/config"),
      ]);
      setMembers(nextMembers);
      setConfig(nextConfig);
    } catch (cause) { setError(errorText(cause)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  const getPending = (member: LadderMember) => member.rungs.filter((rung) => rung.due && rung.status === "fired" && !!rung.staff_action);
  const openCount = members.reduce((count, member) => count + getPending(member).length, 0);
  const followUpCount = members.filter((member) => getPending(member).length > 0).length;
  const inactiveLongEnough = members.filter((member) => (member.days_inactive ?? 0) >= 10).length;
  const upcomingCount = members.filter((member) => !getPending(member).length && member.rungs.some((rung) => rung.is_active && !rung.due)).length;

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return members.filter((member) => {
      const pending = member.rungs.some((rung) => rung.due && rung.status === "fired" && !!rung.staff_action);
      const upcoming = member.rungs.some((rung) => rung.is_active && !rung.due);
      const matchesFilter = filter === "all" || (filter === "follow_up" ? pending : !pending && upcoming);
      return matchesFilter && (!needle || (member.name ?? "Member").toLocaleLowerCase().includes(needle));
    });
  }, [filter, members, query]);

  async function closeRung(member: LadderMember, rung: Rung, skip: boolean) {
    const key = `${member.member_id}:${rung.day}`;
    setBusyKey(key);
    try {
      const updated = await api.post<LadderMember>(`/inactivity-ladder/members/${member.member_id}/rungs/${rung.day}/complete${skip ? "?skip=true" : ""}`);
      setMembers((current) => current.map((item) => item.member_id === member.member_id ? updated : item));
      toast.success(skip ? "Follow-up skipped." : "Follow-up marked complete.");
    } catch (cause) { toast.error(errorText(cause)); }
    finally { setBusyKey(null); }
  }

  function editRung(rung: RungConfig) {
    setEditing(rung);
    setDraft({ member_action: rung.member_action, staff_action: rung.staff_action, email_subject: rung.email_subject, email_body: rung.email_body, is_active: rung.is_active });
  }

  async function saveRung() {
    if (!editing || !draft) return;
    setSaving(true);
    try {
      await api.patch<RungConfig>(`/inactivity-ladder/config/${editing.day}`, draft);
      setEditing(null);
      setDraft(null);
      toast.success(`Day ${editing.day} step updated.`);
      await load();
    } catch (cause) { toast.error(errorText(cause)); }
    finally { setSaving(false); }
  }

  const filters: { key: Filter; label: string; count: number }[] = [
    { key: "follow_up", label: "Needs follow-up", count: followUpCount },
    { key: "all", label: "All active members", count: members.length },
    { key: "upcoming", label: "Not due yet", count: upcomingCount },
  ];
  const fields = [
    ["member_action", "Member outreach"], ["staff_action", "Staff follow-up"],
    ["email_subject", "Email subject"], ["email_body", "Message text"],
  ] as const;

  return <>
    <section aria-label="Inactivity overview" className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Metric label="Open staff follow-ups" value={openCount} warning={openCount > 0} />
      <Metric label="Members to contact" value={followUpCount} warning={followUpCount > 0} />
      <Metric label="Inactive 10+ days" value={inactiveLongEnough} />
      <Metric label="Active members monitored" value={members.length} />
    </section>

    <section className="mb-6 border border-[var(--border)] bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-3 sm:px-5">
        <div><h2 className="text-sm font-semibold text-foreground">Outreach schedule</h2><p className="mt-1 text-xs text-muted-foreground">A member visit resets the inactivity clock. Frozen members are excluded.</p></div>
        {isOwner && <Button variant="secondary" disabled={!config.length} onClick={() => config[0] && editRung(config[0])}>Configure steps</Button>}
      </div>
      <ol className="grid divide-y divide-[var(--border)] sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-4">
        {config.map((rung) => <li key={rung.day} className="min-w-0 p-4">
          <div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Day {rung.day}</p><p className="mt-1 text-sm font-medium text-foreground">{rung.name}</p></div><Badge tone={rung.is_active ? "success" : "neutral"}>{rung.is_active ? "Active" : "Off"}</Badge></div>
          <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">{rung.staff_action || rung.member_action || "No outreach action set"}</p>
          {isOwner && <button type="button" onClick={() => editRung(rung)} className="mt-3 text-xs font-medium text-brand hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">Edit step</button>}
        </li>)}
        {!config.length && !loading && <li className="p-5 text-sm text-muted-foreground">No inactivity steps are configured yet.</li>}
      </ol>
    </section>

    <section className="border border-[var(--border)] bg-card">
      <div className="flex flex-col gap-4 border-b border-[var(--border)] p-4 sm:p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-sm font-semibold text-foreground">Member follow-ups</h2><p className="mt-1 text-xs text-muted-foreground">The scheduled ladder sends member outreach. Record the staff follow-up here.</p></div><label className="w-full sm:max-w-xs"><span className="sr-only">Search members</span><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search member name" /></label></div>
        <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Filter inactivity roster">{filters.map((item) => <button key={item.key} type="button" role="tab" aria-selected={filter === item.key} onClick={() => setFilter(item.key)} className={`min-h-9 shrink-0 border px-3 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${filter === item.key ? "border-brand bg-brand text-brand-foreground" : "border-[var(--border)] text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground"}`}>{item.label}<span className="ml-1.5 tabular-nums opacity-75">{item.count}</span></button>)}</div>
      </div>
      {loading ? <div className="flex justify-center p-10"><Spinner label="Loading inactivity ladder…" /></div>
        : error ? <div className="p-6" role="alert"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-3" onClick={() => { setLoading(true); void load(); }}>Try again</Button></div>
        : visible.length === 0 ? <div className="p-10 text-center"><h3 className="text-sm font-semibold text-foreground">{members.length ? "No members in this view" : "No active members to monitor"}</h3><p className="mx-auto mt-1 max-w-md text-sm leading-6 text-muted-foreground">{members.length ? "Try another filter or search. Follow-ups appear once a scheduled rung has fired." : "Active and grace-period members will appear here. Frozen or ended memberships are excluded."}</p></div>
        : <ul className="divide-y divide-[var(--border)]">{visible.map((member) => {
          const pending = getPending(member);
          const day = member.days_inactive ?? 0;
          const progress = Math.min(100, Math.round(day / Math.max(config.at(-1)?.day ?? 21, 1) * 100));
          return <li key={member.member_id} className="p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><a href={`/app/members?member=${encodeURIComponent(member.member_id)}`} className="text-sm font-semibold text-foreground underline-offset-4 hover:underline">{member.name || "Member"}</a><div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="capitalize">{member.status.replaceAll("_", " ")}</span><span aria-hidden="true">·</span><span>{day} {day === 1 ? "day" : "days"} since last visit</span></div></div>{pending.length ? <Badge tone="warning">{pending.length} follow-up{pending.length === 1 ? "" : "s"} open</Badge> : <Badge tone="neutral">{day === 0 ? "Visited today" : "No action due"}</Badge>}</div>
            <div className="mt-4 h-1.5 overflow-hidden bg-foreground/[0.07]" role="img" aria-label={`${progress}% through inactivity schedule`}><div className="h-full bg-warning transition-[width] duration-300" style={{ width: `${progress}%` }} /></div>
            <ol className="mt-4 grid gap-3 lg:grid-cols-2">{member.rungs.filter((rung) => rung.is_active).map((rung) => {
              const actionPending = rung.due && rung.status === "fired" && !!rung.staff_action;
              const complete = rung.status === "completed";
              const skipped = rung.status === "skipped";
              return <li key={rung.day} className={`border px-3 py-3 ${actionPending ? "border-warning/40 bg-warning-bg/40" : "border-[var(--border)]"}`}>
                <div className="flex flex-wrap items-center justify-between gap-2"><div className="flex items-center gap-2"><span className="text-xs font-semibold text-foreground">Day {rung.day} · {rung.name}</span><Badge tone={complete ? "success" : skipped ? "neutral" : actionPending ? "warning" : "neutral"}>{complete ? "Done" : skipped ? "Skipped" : actionPending ? "Staff follow-up" : rung.status === "fired" ? "Sent" : rung.due ? "Due · not sent" : "Upcoming"}</Badge></div>{rung.status === "fired" && <span className="text-[10px] text-muted-foreground">Sent {dateTime(rung.fired_at)}</span>}</div>
                {rung.member_action && <p className="mt-2 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Member:</span> {rung.member_action}</p>}
                {rung.staff_action && <p className="mt-1 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Staff:</span> {rung.staff_action}</p>}
                {!rung.member_action && !rung.staff_action && <p className="mt-2 text-xs text-muted-foreground">No action configured</p>}
                {rung.channel && <p className="mt-1 text-[10px] text-muted-foreground">Delivered via {rung.channel.replaceAll("+", ", ")}</p>}
                {actionPending && <div className="mt-3 flex flex-wrap justify-end gap-2"><Button variant="ghost" disabled={busyKey === `${member.member_id}:${rung.day}`} onClick={() => void closeRung(member, rung, true)}>Skip</Button><Button variant="secondary" loading={busyKey === `${member.member_id}:${rung.day}`} onClick={() => void closeRung(member, rung, false)}>Mark complete</Button></div>}
              </li>;
            })}</ol>
          </li>;
        })}</ul>}
    </section>

    <p className="mt-3 text-xs leading-5 text-muted-foreground">The daily worker dispatches configured outreach and creates staff tasks as each rung becomes due. Closing a staff follow-up records its outcome; it does not send another message.</p>

    <Sheet open={!!editing} onOpenChange={(open) => { if (!open && !saving) { setEditing(null); setDraft(null); } }}>
      <SheetContent side="right" className="[--sheet-max-w:560px]">
        <SheetHeader><SheetTitle>{editing ? `Day ${editing.day} · ${editing.name}` : "Configure ladder step"}</SheetTitle><SheetDescription>Choose what the member receives and what your team should do.</SheetDescription></SheetHeader>
        {draft && <SheetBody className="space-y-5">
          <label className="flex items-start justify-between gap-4 border-b border-[var(--border)] pb-4 text-sm"><span><span className="block font-medium text-foreground">Step is active</span><span className="mt-1 block text-xs text-muted-foreground">Inactive steps are skipped by the daily ladder.</span></span><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} className="mt-1 size-4 accent-[var(--brand)]" /></label>
          {fields.map(([field, label]) => <label key={field} className="block space-y-1.5"><span className="text-xs font-medium text-foreground">{label}</span>{field === "email_body" ? <textarea value={draft[field] ?? ""} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} rows={5} className="w-full resize-y border border-[var(--border)] bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-brand" /> : <Input value={draft[field] ?? ""} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} />}</label>)}
          <div className="border border-info/25 bg-info-bg p-3 text-xs leading-5 text-foreground">Changes apply to future ladder dispatches. A rung already sent will not be sent again during the same inactivity period.</div>
        </SheetBody>}
        <SheetFooter><Button variant="secondary" disabled={saving} onClick={() => { setEditing(null); setDraft(null); }}>Cancel</Button><Button loading={saving} disabled={!draft} onClick={() => void saveRung()}>Save step</Button></SheetFooter>
      </SheetContent>
    </Sheet>
  </>;
}
