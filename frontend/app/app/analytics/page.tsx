"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import { OperatingReportCard } from "@/components/OperatingReportCard";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Card, CardHeader, Spinner, StatCard } from "@/components/ui";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { api, ApiError } from "@/lib/api";
import { money, titleCase } from "@/lib/format";
import type { RevenueAnalytics } from "@/lib/types";

/* ─── Helpers ─── */

const METHOD_LABELS: Record<string, string> = {
  card: "Card",
  cash: "Cash",
  bank_transfer: "Bank transfer",
  mobile_wallet: "Mobile wallet",
};

const STATUS_LABELS: Record<string, string> = {
  active: "Active",
  grace: "Grace",
  expired: "Expired",
  cancelled: "Cancelled",
  frozen: "Frozen",
  pending_payment: "Pending payment",
  pending_approval: "Pending approval",
  pending_activation: "Pending activation",
  banned: "Banned",
};

const STATUS_COLORS: Record<string, string> = {
  active: "var(--success)",
  grace: "var(--warning)",
  expired: "var(--danger)",
  cancelled: "var(--muted-foreground)",
  frozen: "var(--chart-3)",
  pending_payment: "var(--info)",
  pending_approval: "var(--warning)",
  pending_activation: "var(--info)",
  banned: "var(--danger)",
};

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

const ICONS = {
  revenue: "M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  members: "M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z",
  churn: "M22 10.5h-6m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z",
  average: "M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z",
} as const;

function Tile({ label, value, icon, accent }: { label: string; value: string; icon: string; accent?: boolean }) {
  return (
    <StatCard
      joined
      accent={accent}
      label={label}
      value={value}
      icon={<Icon d={icon} className="h-4 w-4" />}
      className="h-full"
    />
  );
}

/** A label + value + share row with a thin bar, used in the breakdown panels. */
function BreakdownRow({
  color,
  label,
  value,
  pct,
}: {
  color: string;
  label: string;
  value: string;
  pct: number;
}) {
  return (
    <li className="px-5 py-3">
      <div className="flex items-center gap-2.5">
        <span className="h-2.5 w-2.5 shrink-0 rounded-[3px]" style={{ background: color }} aria-hidden="true" />
        <span className="flex-1 truncate text-[13px] text-foreground">{label}</span>
        <span className="text-[13px] font-medium tabular-nums text-foreground">{value}</span>
        <span className="w-9 text-right text-[12px] tabular-nums text-muted-foreground">{pct}%</span>
      </div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-foreground/[0.08]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(2, pct)}%`, background: color }} />
      </div>
    </li>
  );
}

function ChartEmpty({ tone, title, hint }: { tone: "revenue" | "members"; title: string; hint: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 border border-dashed border-foreground/15 px-6 py-16 text-center">
      <span className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-foreground/[0.05] text-muted-foreground">
        {tone === "revenue" ? (
          <Icon d={ICONS.revenue} className="h-5 w-5" />
        ) : (
          <Icon d={ICONS.members} className="h-5 w-5" />
        )}
      </span>
      <p className="text-[13px] font-medium text-foreground">{title}</p>
      <p className="max-w-xs text-[12px] text-muted-foreground">{hint}</p>
    </div>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState<RevenueAnalytics | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setData(await api.get<RevenueAnalytics>("/analytics/revenue"));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  const methodEntries = useMemo(
    () => Object.entries(data?.revenue_by_method ?? {}).filter(([, amount]) => amount > 0),
    [data],
  );
  const statusEntries = useMemo(
    () => Object.entries(data?.member_count_by_status ?? {}).filter(([, count]) => count > 0),
    [data],
  );

  const totalByMethod = methodEntries.reduce((sum, [, amount]) => sum + amount, 0);
  const totalMembers = statusEntries.reduce((sum, [, count]) => sum + count, 0);

  const revenueChartConfig = useMemo(() => {
    const colors = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)"];
    const config: ChartConfig = {};
    methodEntries.forEach(([method], i) => {
      config[method] = { label: METHOD_LABELS[method] || titleCase(method), color: colors[i % colors.length] };
    });
    return config;
  }, [methodEntries]);

  const revenueChartData = useMemo(
    () =>
      methodEntries.map(([method, amount]) => ({
        method: METHOD_LABELS[method] || titleCase(method),
        amount,
        fill: revenueChartConfig[method]?.color || "var(--muted)",
      })),
    [methodEntries, revenueChartConfig],
  );

  const statusChartConfig = useMemo(() => {
    const config: ChartConfig = {};
    statusEntries.forEach(([status]) => {
      config[status] = {
        label: STATUS_LABELS[status] || titleCase(status),
        color: STATUS_COLORS[status] || "var(--muted-foreground)",
      };
    });
    return config;
  }, [statusEntries]);

  const statusChartData = useMemo(
    () =>
      statusEntries.map(([status, count]) => ({
        status: STATUS_LABELS[status] || titleCase(status),
        count,
        fill: statusChartConfig[status]?.color || "var(--muted)",
      })),
    [statusEntries, statusChartConfig],
  );

  const avgPerMember = data && data.active_members > 0 ? data.total_revenue / data.active_members : 0;

  const kpis = data
    ? [
        { label: "Total revenue", value: money(data.total_revenue, data.currency), icon: ICONS.revenue, accent: true },
        { label: "Active members", value: String(data.active_members), icon: ICONS.members },
        { label: "Churned", value: String(data.churn_count), icon: ICONS.churn },
        { label: "Revenue / member", value: money(avgPerMember, data.currency), icon: ICONS.average },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Analytics"
        subtitle="Revenue and membership at a glance"
        action={data ? <Badge tone="neutral">{data.currency}</Badge> : null}
      />

      {error && <div className="mb-4"><Alert onDismiss={() => setError("")}>{error}</Alert></div>}

      {data === null ? (
        <Spinner label="Loading analytics…" />
      ) : (
        <div className="space-y-6">
          <OperatingReportCard />
          {/* KPI strip */}
          <div className="grid grid-cols-1 gap-px overflow-hidden border border-foreground/10 bg-[var(--border)] sm:grid-cols-2 lg:grid-cols-4">
            {kpis.map((k) => (
              <Tile key={k.label} label={k.label} value={k.value} icon={k.icon} accent={k.accent} />
            ))}
          </div>

          <Card>
            <CardHeader title="Operating expenses" subtitle="Recorded, non-voided expenses to date. Totals are shown separately by currency." />
            <div className="flex flex-wrap gap-3 p-5">
              {Object.entries(data.operating_expenses_by_currency).length === 0 ? (
                <p className="text-[13px] text-muted-foreground">No operating expenses recorded.</p>
              ) : Object.entries(data.operating_expenses_by_currency).map(([currency, amount]) => (
                <div key={currency} className="min-w-40 rounded-lg border border-border px-4 py-3">
                  <div className="text-xs text-muted-foreground">{currency}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">{money(Number(amount), currency)}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* Revenue */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2 lg:row-start-1">
              <CardHeader title="Revenue by method" subtitle="Gross revenue broken down by payment method." />
              <div className="p-5">
                {revenueChartData.length === 0 ? (
                  <ChartEmpty
                    tone="revenue"
                    title="No revenue yet"
                    hint="Revenue will appear here once payments start coming in."
                  />
                ) : (
                  <ChartContainer config={revenueChartConfig} className="aspect-auto h-[280px] w-full">
                    <BarChart data={revenueChartData} margin={{ top: 10, right: 12, left: 12, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="4 4" />
                      <XAxis dataKey="method" tickLine={false} axisLine={false} tickMargin={8} />
                      <YAxis
                        tickLine={false}
                        axisLine={false}
                        tickMargin={8}
                        tickFormatter={(v: number) => money(v, data.currency)}
                      />
                      <ChartTooltip
                        cursor={false}
                        content={<ChartTooltipContent formatter={(v) => money(v, data.currency)} />}
                      />
                      <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                        {revenueChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ChartContainer>
                )}
              </div>
            </Card>

            <Card className="lg:col-span-1 lg:col-start-3 lg:row-start-1">
              <CardHeader title="Revenue breakdown" subtitle="Share of each payment method." />
              {revenueChartData.length === 0 ? (
                <p className="px-5 py-8 text-center text-[13px] text-muted-foreground">No revenue recorded yet.</p>
              ) : (
                <ul className="divide-y divide-[var(--border)]">
                  {methodEntries.map(([method, amount]) => (
                    <BreakdownRow
                      key={method}
                      color={revenueChartConfig[method]?.color || "var(--muted)"}
                      label={METHOD_LABELS[method] || titleCase(method)}
                      value={money(amount, data.currency)}
                      pct={totalByMethod ? Math.round((amount / totalByMethod) * 100) : 0}
                    />
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {/* Members */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-2 lg:row-start-1">
              <CardHeader title="Members by status" subtitle="Current breakdown of all members." />
              <div className="p-5">
                {statusChartData.length === 0 ? (
                  <ChartEmpty
                    tone="members"
                    title="No members yet"
                    hint="Once members join, their status breakdown will show here."
                  />
                ) : (
                  <ChartContainer config={statusChartConfig} className="aspect-auto h-[280px] w-full">
                    <PieChart margin={{ top: 10, right: 12, left: 12, bottom: 0 }}>
                      <Pie
                        data={statusChartData}
                        dataKey="count"
                        nameKey="status"
                        cx="50%"
                        cy="50%"
                        innerRadius={68}
                        outerRadius={104}
                        strokeWidth={2}
                        stroke="var(--background)"
                      >
                        {statusChartData.map((entry, i) => (
                          <Cell key={i} fill={entry.fill} />
                        ))}
                        <Label
                          content={({ viewBox }) => {
                            if (viewBox && "cx" in viewBox) {
                              return (
                                <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                  <tspan x={viewBox.cx} y={(viewBox.cy ?? 0) - 6} className="fill-[var(--foreground)] text-[24px] font-semibold tabular-nums">
                                    {data.active_members}
                                  </tspan>
                                  <tspan x={viewBox.cx} y={(viewBox.cy ?? 0) + 16} className="fill-[var(--muted-foreground)] text-[10px] uppercase tracking-wide">
                                    Active
                                  </tspan>
                                </text>
                              );
                            }
                          }}
                        />
                      </Pie>
                      <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                      <ChartLegend content={<ChartLegendContent />} />
                    </PieChart>
                  </ChartContainer>
                )}
              </div>
            </Card>

            <Card className="lg:col-span-1 lg:col-start-3 lg:row-start-1">
              <CardHeader title="Member breakdown" subtitle="Count by membership status." />
              {statusChartData.length === 0 ? (
                <p className="px-5 py-8 text-center text-[13px] text-muted-foreground">No members recorded yet.</p>
              ) : (
                <ul className="divide-y divide-[var(--border)]">
                  {statusEntries.map(([status, count]) => (
                    <BreakdownRow
                      key={status}
                      color={statusChartConfig[status]?.color || "var(--muted)"}
                      label={STATUS_LABELS[status] || titleCase(status)}
                      value={String(count)}
                      pct={totalMembers ? Math.round((count / totalMembers) * 100) : 0}
                    />
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
