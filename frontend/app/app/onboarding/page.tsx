"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Button, Input, Spinner } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ApiError, api } from "@/lib/api";

type Milestone = {
  day: number; code: string; title: string; member_action: string | null;
  staff_action: string | null; status: "pending" | "completed" | "skipped" | "locked";
  completed_at: string | null; notes: string | null;
};
type Journey = {
  id: string; member_id: string; member_name: string | null;
  status: "active" | "paused" | "completed" | "opted_out";
  started_at: string; completed_at: string | null; current_day: number; total_days: number;
  visits_total: number; visits_last_7d: number; classes_attended: number; at_risk: boolean;
  milestones: Milestone[];
};
type Summary = { total: number; active: number; completed: number; paused: number; at_risk: number };
type Filter = "all" | "active" | "at_risk" | "paused" | "completed";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Everyone" }, { key: "active", label: "In progress" },
  { key: "at_risk", label: "Needs follow-up" }, { key: "paused", label: "Paused" },
  { key: "completed", label: "Completed" },
];
const EMPTY_SUMMARY: Summary = { total: 0, active: 0, completed: 0, paused: 0, at_risk: 0 };
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";
const errorMessage = (error: unknown) => error instanceof ApiError ? error.message : "Could not load onboarding journeys.";

function Metric({ label, value, warning = false }: { label: string; value: number; warning?: boolean }) {
  return <div className="border border-[var(--border)] bg-card px-4 py-4 sm:px-5"><p className="text-xs font-medium text-muted-foreground">{label}</p><p className={`mt-1 text-2xl font-semibold tabular-nums ${warning ? "text-warning" : "text-foreground"}`}>{value}</p></div>;
}

function JourneyBadge({ journey }: { journey: Journey }) {
  const needsFollowup = journey.at_risk && journey.status === "active";
  const badgeTone = needsFollowup || journey.status === "paused" ? "warning" : journey.status === "completed" ? "success" : journey.status === "opted_out" ? "neutral" : "info";
  return <Badge tone={badgeTone}>{needsFollowup ? "Needs follow-up" : journey.status.replace("_", " ")}</Badge>;
}

export default function OnboardingPage() {
  const [journeys, setJourneys] = useState<Journey[]>([]);
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Journey | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetchData = useCallback(async () => {
    const [nextSummary, nextJourneys] = await Promise.all([
        api.get<Summary>("/onboarding/summary"), api.get<Journey[]>("/onboarding/members"),
    ]);
    return { summary: nextSummary, journeys: nextJourneys };
  }, []);

  const refresh = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const result = await fetchData();
      setSummary(result.summary);
      setJourneys(result.journeys);
    } catch (cause) { setError(errorMessage(cause)); }
    finally { setLoading(false); }
  }, [fetchData]);

  useEffect(() => {
    let cancelled = false;
    fetchData().then((result) => {
      if (!cancelled) { setSummary(result.summary); setJourneys(result.journeys); }
    }).catch((cause: unknown) => {
      if (!cancelled) setError(errorMessage(cause));
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchData]);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    api.get<Journey>(`/onboarding/members/${selectedId}`)
      .then((value) => { if (!cancelled) setDetail(value); })
      .catch((cause: unknown) => { if (!cancelled) toast.error(errorMessage(cause)); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return journeys.filter((journey) => {
      const matchesFilter = filter === "all" || (filter === "at_risk"
        ? journey.at_risk && journey.status === "active" : journey.status === filter);
      return matchesFilter && (!needle || (journey.member_name ?? "").toLowerCase().includes(needle));
    });
  }, [filter, journeys, query]);

  const updateJourney = async (path: string, body: object, success: string) => {
    if (!detail) return;
    setBusy(true);
    try {
      setDetail(await api.post<Journey>(path, body));
      toast.success(success);
      await refresh();
    } catch (cause) { toast.error(errorMessage(cause)); }
    finally { setBusy(false); }
  };

  return <div className="onboarding-page">
    <PageHeader title="Member onboarding" subtitle="Help every new member build a routine in their first 90 days." />

    <section aria-label="Journey overview" className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Metric label="In progress" value={summary.active} />
      <Metric label="Needs a check-in" value={summary.at_risk} warning={summary.at_risk > 0} />
      <Metric label="Completed" value={summary.completed} />
      <Metric label="All journeys" value={summary.total} />
    </section>

    <section className="border border-[var(--border)] bg-card">
      <div className="flex flex-col gap-4 border-b border-[var(--border)] p-4 sm:p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div><h2 className="text-sm font-semibold text-foreground">New member journeys</h2><p className="mt-1 text-xs text-muted-foreground">Progress updates as member visits and check-ins are recorded.</p></div>
          <label className="w-full sm:max-w-xs"><span className="sr-only">Search members</span><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search member name" /></label>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Filter journeys">
          {FILTERS.map((item) => <button key={item.key} type="button" role="tab" aria-selected={filter === item.key} onClick={() => setFilter(item.key)} className={`min-h-9 shrink-0 border px-3 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${filter === item.key ? "border-brand bg-brand text-brand-foreground" : "border-[var(--border)] text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground"}`}>
            {item.label}{item.key === "at_risk" && summary.at_risk > 0 ? ` · ${summary.at_risk}` : ""}
          </button>)}
        </div>
      </div>

      {loading ? <div className="flex justify-center p-10"><Spinner label="Loading journeys…" /></div>
        : error ? <div className="p-6" role="alert"><p className="text-sm text-danger">{error}</p><Button variant="secondary" className="mt-3" onClick={() => void refresh()}>Try again</Button></div>
        : visible.length === 0 ? <div className="p-10 text-center"><h3 className="text-sm font-semibold text-foreground">{journeys.length ? "No matching journeys" : "No journeys yet"}</h3><p className="mx-auto mt-1 max-w-md text-sm leading-6 text-muted-foreground">{journeys.length ? "Try another filter or search term." : "A journey starts when a member’s membership becomes active. New members appear here automatically."}</p></div>
        : <>
          <div className="hidden grid-cols-[minmax(180px,1.5fr)_repeat(3,minmax(100px,1fr))_minmax(130px,1fr)] gap-4 px-5 py-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground md:grid"><span>Member</span><span>Journey</span><span>Visits</span><span>Started</span><span>Status</span></div>
          <ul className="divide-y divide-[var(--border)]">{visible.map((journey) => <li key={journey.id}><button type="button" onClick={() => { setDetail(null); setDetailLoading(true); setSelectedId(journey.member_id); }} className="grid w-full grid-cols-2 items-center gap-x-4 gap-y-3 px-4 py-4 text-left transition-colors hover:bg-foreground/[0.025] focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-brand sm:px-5 md:grid-cols-[minmax(180px,1.5fr)_repeat(3,minmax(100px,1fr))_minmax(130px,1fr)]">
            <span className="col-span-2 min-w-0 md:col-span-1"><span className="block truncate text-sm font-medium text-foreground">{journey.member_name || "Member"}</span><span className="mt-0.5 block text-xs text-muted-foreground">90-day member journey</span></span>
            <span className="text-xs text-muted-foreground"><span className="md:hidden">Day </span>{Math.min(journey.current_day, journey.total_days)} of {journey.total_days}</span>
            <span className="text-xs text-muted-foreground">{journey.visits_total} total · {journey.visits_last_7d} this week</span>
            <span className="text-xs text-muted-foreground">{dateLabel(journey.started_at)}</span><span><JourneyBadge journey={journey} /></span>
          </button></li>)}</ul>
        </>}
    </section>

    <Sheet open={Boolean(selectedId)} onOpenChange={(open) => { if (!open) { setSelectedId(null); setDetail(null); setDetailLoading(false); } }}>
      <SheetContent side="right" className="w-full sm:max-w-[520px]">
        <SheetHeader><SheetTitle>{detail?.member_name || "Member journey"}</SheetTitle><SheetDescription>{detail ? `Day ${Math.min(detail.current_day, detail.total_days)} of ${detail.total_days} · started ${dateLabel(detail.started_at)}` : "90-day onboarding progress"}</SheetDescription></SheetHeader>
        <SheetBody>
          {detailLoading || !detail ? <div className="flex justify-center py-10"><Spinner label="Loading milestones…" /></div> : <>
            <div className="mb-5 grid grid-cols-3 border border-[var(--border)]">
              <div className="p-3"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Visits</p><p className="mt-1 text-lg font-semibold">{detail.visits_total}</p></div>
              <div className="border-x border-[var(--border)] p-3"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">This week</p><p className="mt-1 text-lg font-semibold">{detail.visits_last_7d}</p></div>
              <div className="p-3"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">Classes</p><p className="mt-1 text-lg font-semibold">{detail.classes_attended}</p></div>
            </div>
            {detail.at_risk && detail.status === "active" ? <div className="mb-5 border border-warning/30 bg-warning-bg px-4 py-3 text-sm text-foreground">No visit in the past 7 days. Reach out to help them get back on track.</div> : null}
            <ol className="space-y-0">{detail.milestones.map((milestone, index) => {
              const done = milestone.status === "completed" || milestone.status === "skipped";
              const locked = milestone.status === "locked";
              return <li key={milestone.code} className="relative flex gap-3 pb-5 last:pb-0">
                {index < detail.milestones.length - 1 ? <span aria-hidden="true" className="absolute left-[11px] top-6 h-[calc(100%-8px)] w-px bg-[var(--border)]" /> : null}
                <span className={`relative z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center border text-xs ${done ? "border-success bg-success text-white" : locked ? "border-[var(--border)] bg-card text-muted-foreground" : "border-brand bg-card text-brand"}`} aria-label={done ? "Completed" : locked ? "Locked" : "Available"}>{done ? "✓" : String(index + 1)}</span>
                <div className="min-w-0 flex-1 border-b border-[var(--border)] pb-4 last:border-b-0"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Day {milestone.day}</p><h3 className="mt-0.5 text-sm font-semibold text-foreground">{milestone.title}</h3></div>{milestone.completed_at ? <span className="text-xs text-muted-foreground">{dateLabel(milestone.completed_at)}</span> : null}</div>
                  {milestone.member_action ? <p className="mt-1 text-sm leading-5 text-muted-foreground">{milestone.member_action}</p> : null}
                  {milestone.staff_action ? <p className="mt-2 text-xs leading-5 text-muted-foreground"><span className="font-medium text-foreground">Staff:</span> {milestone.staff_action}</p> : null}
                  {milestone.notes ? <p className="mt-2 text-xs text-muted-foreground">Note: {milestone.notes}</p> : null}
                  {milestone.status === "pending" ? <Button variant="secondary" className="mt-3" disabled={busy} onClick={() => void updateJourney(`/onboarding/members/${detail.member_id}/milestones/complete`, { code: milestone.code }, "Milestone marked complete.")}>Mark complete</Button> : null}
                  {locked ? <p className="mt-2 text-xs text-muted-foreground">Available on day {milestone.day}</p> : null}
                </div>
              </li>;
            })}</ol>
          </>}
        </SheetBody>
        <SheetFooter className="justify-between"><span className="text-xs text-muted-foreground">{detail ? `Status: ${detail.status.replace("_", " ")}` : ""}</span>
          {detail && detail.status !== "completed" && detail.status !== "opted_out" ? <Button variant="secondary" disabled={busy} onClick={() => void updateJourney(`/onboarding/members/${detail.member_id}/status`, { pause: detail.status === "active" }, detail.status === "active" ? "Journey paused." : "Journey resumed.")}>{detail.status === "active" ? "Pause journey" : "Resume journey"}</Button> : null}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  </div>;
}
