"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

type Milestone = { milestone: string; sent: number; responded: number; response_rate: number | null; nps_score: number | null };
type Summary = { responded: number; response_rate: number | null; nps_score: number | null; promoters: number; passives: number; detractors: number; by_milestone: Milestone[] };
type Response = { id: string; member_id: string; member_name: string | null; milestone: string; score: number; comment: string | null; cluster_tag: string | null; sent_at: string; responded_at: string | null };
type Cluster = { theme: string; total: number; detractors: number; passives: number; promoters: number; examples: string[] };

function percent(value: number | null) { return value == null ? "—" : `${value}%`; }
function nps(value: number | null) { return value == null ? "—" : `${value > 0 ? "+" : ""}${value}`; }

export function NpsFeedbackPanel() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [responses, setResponses] = useState<Response[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => Promise.all([
    api.get<Summary>("/nps/summary"),
    api.get<Response[]>("/nps/responses?limit=20"),
    api.get<Cluster[]>("/nps/clusters"),
  ]), []);

  const refresh = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [totals, recent, themes] = await load();
      setSummary(totals);
      setResponses(recent);
      setClusters(themes);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load member feedback.");
    } finally {
      setLoading(false);
    }
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    load().then(([totals, recent, themes]) => {
      if (cancelled) return;
      setSummary(totals);
      setResponses(recent);
      setClusters(themes);
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof ApiError ? cause.message : "Could not load member feedback.");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [load]);

  if (loading) return <div className="flex justify-center border border-[var(--border)] bg-card p-10"><Spinner label="Loading member feedback…" /></div>;
  if (error) return <div role="alert" className="border border-[var(--border)] bg-card p-5"><Alert tone="danger">{error}</Alert><Button variant="secondary" className="mt-3" onClick={() => void refresh()}>Try again</Button></div>;

  const metrics = [
    ["NPS score", nps(summary?.nps_score ?? null)],
    ["Response rate", percent(summary?.response_rate ?? null)],
    ["Responses", summary?.responded ?? 0],
    ["Promoters", summary?.promoters ?? 0],
  ];

  return <div className="space-y-6">
    <section className="border border-[var(--border)] bg-card">
      <header className="border-b border-[var(--border)] px-4 py-3 sm:px-5"><h2 className="text-sm font-semibold text-foreground">Member feedback</h2><p className="mt-1 text-xs text-muted-foreground">Survey results at days 7, 30, and 90, plus recurring complaint themes.</p></header>
      <div className="grid grid-cols-2 gap-px bg-[var(--border)] sm:grid-cols-4">{metrics.map(([label, value]) => <div key={String(label)} className="bg-card px-4 py-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{value}</p></div>)}</div>
      <div className="grid gap-6 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div><h3 className="text-sm font-semibold text-foreground">By milestone</h3>{summary?.by_milestone.length ? <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs"><thead className="text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="py-2 pr-3 font-medium">Survey</th><th className="py-2 pr-3 font-medium">Replies</th><th className="py-2 pr-3 font-medium">Response rate</th><th className="py-2 font-medium">NPS</th></tr></thead><tbody className="divide-y divide-[var(--border)]">{summary.by_milestone.map((item) => <tr key={item.milestone}><td className="py-2.5 pr-3 capitalize text-foreground">{item.milestone.replaceAll("_", " ")}</td><td className="py-2.5 pr-3 tabular-nums text-foreground">{item.responded}/{item.sent}</td><td className="py-2.5 pr-3 tabular-nums text-foreground">{percent(item.response_rate)}</td><td className="py-2.5 tabular-nums text-foreground">{nps(item.nps_score)}</td></tr>)}</tbody></table></div> : <p className="mt-3 text-sm text-muted-foreground">No surveys sent yet.</p>}</div>
        <div><h3 className="text-sm font-semibold text-foreground">Complaint themes</h3>{clusters.length ? <ul className="mt-3 divide-y divide-[var(--border)] border-y border-[var(--border)]">{clusters.map((cluster) => <li key={cluster.theme} className="py-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-medium capitalize text-foreground">{cluster.theme.replaceAll("_", " ")}</p><span className="text-xs text-muted-foreground">{cluster.total} response{cluster.total === 1 ? "" : "s"} · {cluster.detractors} detractors</span></div>{cluster.examples[0] && <p className="mt-1 text-xs leading-5 text-muted-foreground">“{cluster.examples[0]}”</p>}</li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No recurring complaint themes yet.</p>}</div>
      </div>
    </section>
    <section className="border border-[var(--border)] bg-card">
      <header className="border-b border-[var(--border)] px-4 py-3 sm:px-5"><h2 className="text-sm font-semibold text-foreground">Recent responses</h2><p className="mt-1 text-xs text-muted-foreground">Latest member ratings and optional comments.</p></header>
      {responses.length ? <ul className="divide-y divide-[var(--border)]">{responses.map((item) => <li key={item.id} className="flex flex-col gap-2 px-4 py-3 sm:px-5"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-medium text-foreground">{item.member_name || "Member"}</span><Badge tone={item.score <= 6 ? "danger" : item.score <= 8 ? "warning" : "success"}>{item.score}/10</Badge><span className="text-xs capitalize text-muted-foreground">Day {item.milestone.replace("day_", "")}{item.cluster_tag ? ` · ${item.cluster_tag.replaceAll("_", " ")}` : ""}</span><time className="ml-auto text-xs text-muted-foreground">{item.responded_at ? new Date(item.responded_at).toLocaleDateString() : "—"}</time></div>{item.comment && <p className="text-sm leading-6 text-muted-foreground">{item.comment}</p>}</li>)}</ul> : <p className="px-4 py-5 text-sm text-muted-foreground sm:px-5">No member feedback responses yet.</p>}
    </section>
  </div>;
}
