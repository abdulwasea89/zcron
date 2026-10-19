"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Input, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

type Severity = "silent" | "severe" | "moderate" | null;
type AttendanceDrop = {
  member_id: string;
  name: string | null;
  status: string;
  score: number;
  band: string;
  trend: {
    eligible: boolean;
    baseline_weekly: number;
    recent_weekly: number;
    drop_ratio: number | null;
    is_drop: boolean;
    severity: Severity;
    recent_visits: number;
    baseline_visits: number;
    days_since_last_visit: number | null;
  };
  reasons: { code: string; label: string; weight: number }[];
  days_since_last_visit: number | null;
  recent_weekly: number;
  baseline_weekly: number;
};
type SeverityFilter = "all" | Exclude<Severity, null>;

const FILTERS: { key: SeverityFilter; label: string }[] = [
  { key: "all", label: "All declines" },
  { key: "silent", label: "No visits" },
  { key: "severe", label: "Severe" },
  { key: "moderate", label: "Moderate" },
];

function safeError(error: unknown) {
  return error instanceof ApiError ? error.message : "Could not load attendance trends.";
}

function visitsPerWeek(value: number) {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} / week`;
}

function severityLabel(severity: Severity) {
  if (severity === "silent") return "No visits";
  if (severity === "severe") return "Severe drop";
  return "Moderate drop";
}

function severityTone(severity: Severity): "danger" | "warning" {
  return severity === "silent" || severity === "severe" ? "danger" : "warning";
}

function AttendanceBar({ baseline, recent }: { baseline: number; recent: number }) {
  const recentWidth = Math.max(0, Math.min(100, (recent / Math.max(baseline, 1)) * 100));
  return (
    <div className="mt-2 space-y-1.5" role="img" aria-label={`${recent} recent visits per week compared with ${baseline} baseline visits per week`}>
      <div className="h-1.5 overflow-hidden bg-foreground/[0.07]"><div className="h-full bg-foreground/35" style={{ width: "100%" }} /></div>
      <div className="h-1.5 overflow-hidden bg-foreground/[0.07]"><div className="h-full bg-warning" style={{ width: `${recentWidth}%` }} /></div>
      <div className="flex justify-between text-[10px] text-muted-foreground"><span>Baseline</span><span>Recent</span></div>
    </div>
  );
}

function Metric({ label, count, tone }: { label: string; count: number; tone?: "danger" | "warning" }) {
  return (
    <div className="border border-[var(--border)] bg-card px-4 py-4 sm:px-5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : "text-foreground"}`}>{count}</p>
    </div>
  );
}

export default function AttendanceRetentionPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AttendanceDrop[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<SeverityFilter>("all");
  const [query, setQuery] = useState("");

  const fetchRows = useCallback(() => api.get<AttendanceDrop[]>("/retention/drops?limit=500"), []);

  const refresh = useCallback(async () => {
    setError("");
    setLoading(true);
    try { setRows(await fetchRows()); }
    catch (cause) { setError(safeError(cause)); }
    finally { setLoading(false); }
  }, [fetchRows]);

  useEffect(() => {
    let cancelled = false;
    fetchRows().then((result) => { if (!cancelled) setRows(result); })
      .catch((cause: unknown) => { if (!cancelled) setError(safeError(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [fetchRows]);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return rows.filter((row) => {
      const matchesSeverity = filter === "all" || row.trend.severity === filter;
      const matchesName = !needle || (row.name ?? "Member").toLocaleLowerCase().includes(needle);
      return matchesSeverity && matchesName;
    });
  }, [filter, query, rows]);

  const silentCount = rows.filter((row) => row.trend.severity === "silent").length;
  const severeCount = rows.filter((row) => row.trend.severity === "severe").length;
  const moderateCount = rows.filter((row) => row.trend.severity === "moderate").length;

  return (
    <>
      <PageHeader title="Attendance trends" subtitle="Spot when a member’s visits fall below their own usual routine." />

      <section aria-label="Attendance drop overview" className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Members with a drop" count={rows.length} />
        <Metric label="No visits in 14 days" count={silentCount} tone={silentCount ? "danger" : undefined} />
        <Metric label="Severe drop" count={severeCount} tone={severeCount ? "danger" : undefined} />
        <Metric label="Moderate drop" count={moderateCount} tone={moderateCount ? "warning" : undefined} />
      </section>

      <div className="mb-5 border border-info/25 bg-info-bg px-4 py-3 text-sm leading-6 text-foreground">
        Each alert compares the member’s recent 14 days with their own previous 56-day attendance. A drop means their current weekly pace is half or less of their established routine. Members need at least 21 days of tenure and an average of one baseline visit per week to qualify.
      </div>

      <section className="border border-[var(--border)] bg-card">
        <div className="flex flex-col gap-4 border-b border-[var(--border)] p-4 sm:p-5">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div><h2 className="text-sm font-semibold text-foreground">Members to check in with</h2><p className="mt-1 text-xs text-muted-foreground">Sorted from the largest attendance decline to the smallest.</p></div>
            <label className="w-full sm:max-w-xs"><span className="sr-only">Search members</span><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search member name" /></label>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Filter attendance declines">
            {FILTERS.map((item) => {
              const count = item.key === "all" ? rows.length : rows.filter((row) => row.trend.severity === item.key).length;
              return <button key={item.key} type="button" aria-pressed={filter === item.key} onClick={() => setFilter(item.key)} className={`min-h-9 shrink-0 border px-3 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${filter === item.key ? "border-brand bg-brand text-brand-foreground" : "border-[var(--border)] text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground"}`}>
                {item.label}<span className="ml-1.5 tabular-nums opacity-75">{count}</span>
              </button>;
            })}
          </div>
        </div>

        {loading ? <div className="flex justify-center p-10"><Spinner label="Loading attendance trends…" /></div>
          : error ? <div className="p-6" role="alert"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-3" onClick={() => void refresh()}>Try again</Button></div>
          : visible.length === 0 ? <div className="p-10 text-center"><h3 className="text-sm font-semibold text-foreground">{rows.length ? "No matching members" : "No attendance drops detected"}</h3><p className="mx-auto mt-1 max-w-md text-sm leading-6 text-muted-foreground">{rows.length ? "Try another filter or search term." : "Eligible members whose attendance falls to half or less of their personal baseline will appear here."}</p></div>
          : <>
            <div className="hidden grid-cols-[minmax(150px,1.25fr)_minmax(170px,1.25fr)_minmax(130px,1fr)_minmax(130px,0.8fr)_minmax(120px,0.8fr)] gap-4 px-5 py-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground md:grid"><span>Member</span><span>Visits per week</span><span>Attendance change</span><span>Last visit</span><span>Signal</span></div>
            <ul className="divide-y divide-[var(--border)]">
              {visible.map((row) => {
                const dropPercent = row.trend.drop_ratio == null ? null : Math.max(0, Math.round((1 - row.trend.drop_ratio) * 100));
                const daysSince = row.trend.days_since_last_visit;
                const lastVisit = daysSince == null ? "No recorded visit" : daysSince === 0 ? "Today" : `${daysSince} days ago`;
                const memberHref = `/app/members?member=${encodeURIComponent(row.member_id)}`;
                return <li key={row.member_id}>
                  <div className="grid gap-4 px-4 py-4 sm:px-5 md:grid-cols-[minmax(150px,1.25fr)_minmax(170px,1.25fr)_minmax(130px,1fr)_minmax(130px,0.8fr)_minmax(120px,0.8fr)] md:items-center">
                    <div className="min-w-0"><button type="button" onClick={() => router.push(memberHref)} className="block max-w-full truncate text-left text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">{row.name || "Member"}</button><span className="mt-1 block text-xs capitalize text-muted-foreground">{row.status.replaceAll("_", " ")}</span></div>
                    <div className="grid grid-cols-2 gap-3 md:block">
                      <div><span className="text-[10px] uppercase tracking-wider text-muted-foreground md:hidden">Usual pace</span><p className="mt-0.5 text-sm font-medium tabular-nums text-foreground">{visitsPerWeek(row.trend.baseline_weekly)}</p></div>
                      <div><span className="text-[10px] uppercase tracking-wider text-muted-foreground md:hidden">Recent pace</span><p className="mt-0.5 text-sm font-medium tabular-nums text-warning">{visitsPerWeek(row.trend.recent_weekly)}</p></div>
                      <AttendanceBar baseline={row.trend.baseline_weekly} recent={row.trend.recent_weekly} />
                    </div>
                    <div><span className="text-[10px] uppercase tracking-wider text-muted-foreground md:hidden">Change</span><p className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">{dropPercent == null ? "—" : `↓ ${dropPercent}%`}</p><p className="text-xs text-muted-foreground">{row.trend.baseline_visits} baseline · {row.trend.recent_visits} recent visits</p></div>
                    <div><span className="text-[10px] uppercase tracking-wider text-muted-foreground md:hidden">Last visit</span><p className="mt-0.5 text-sm text-foreground">{lastVisit}</p></div>
                    <div className="flex items-center justify-between gap-3 md:block"><Badge tone={severityTone(row.trend.severity)}>{severityLabel(row.trend.severity)}</Badge><Button variant="ghost" className="px-2 text-xs md:mt-2" onClick={() => router.push(memberHref)}>Open member</Button></div>
                  </div>
                </li>;
              })}
            </ul>
          </>}
      </section>
      <p className="mt-3 text-xs leading-5 text-muted-foreground">Attendance trends are an early outreach signal, not a prediction that a member will cancel. Counts reflect check-ins recorded in Acron.</p>
    </>
  );
}
