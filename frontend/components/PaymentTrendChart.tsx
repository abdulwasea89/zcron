"use client";

import { useId, useState } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { CircleDollarSign } from "lucide-react";
import { ChartContainer } from "@/components/ui/chart";
import { Button } from "@/components/ui";
import { DashboardEmptyState } from "@/components/DashboardUI";

export type PaymentTrendPoint = { date: string; label: string; axisLabel: string; count: number };

function PaymentTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: PaymentTrendPoint; value: number }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return <div className="dash-chart-tooltip"><strong>{point.label}</strong><p className="dash-meta">{point.count} {point.count === 1 ? "payment" : "payments"}</p></div>;
}

export function PaymentTrendChart({ data, actionHref, actionLabel }: { data: PaymentTrendPoint[]; actionHref: string; actionLabel: string }) {
  const gradientId = `payment-fill-${useId().replace(/:/g, "")}`;
  const [days, setDays] = useState(14);
  const visible = data.slice(-days);
  const total = visible.reduce((sum, day) => sum + day.count, 0);
  return <div>
    <div className="dash-section-heading">
      <span className="dash-meta">Successful payments · daily count</span>
      <div className="dash-chart-range" role="group" aria-label="Payment date range">
        {[7,14].map(range => <Button key={range} variant="ghost" className="dash-button dash-ghost" aria-pressed={days === range} onClick={() => setDays(range)}>{range} days</Button>)}
      </div>
    </div>
    {total === 0 ? <DashboardEmptyState icon={<CircleDollarSign />} title="No payments yet" href={actionHref} action={actionLabel}>
      Record a payment to see your daily activity here. No successful payments in the last {days} days.
    </DashboardEmptyState> : <div className="dash-chart" role="img" aria-label={`Successful payments over the last ${days} days: ${visible.map(day => `${day.label}, ${day.count}`).join("; ")}`}>
      <ChartContainer config={{ count: { label: "Payments", color: "var(--brand)" } }} className="aspect-auto h-full w-full">
        <AreaChart data={visible} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
          <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--color-count)" stopOpacity={0.24} /><stop offset="100%" stopColor="var(--color-count)" stopOpacity={0.01} /></linearGradient></defs>
          <CartesianGrid vertical={false} stroke="var(--dash-line)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={12} minTickGap={30} tick={{ fill: "var(--dash-secondary)", fontSize: 12 }} />
          <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "var(--dash-secondary)", fontSize: 12 }} />
          <Tooltip cursor={false} content={<PaymentTooltip />} />
          <Area type="monotone" dataKey="count" stroke="var(--color-count)" strokeWidth={2} fill={`url(#${gradientId})`} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
        </AreaChart>
      </ChartContainer>
    </div>}
    <div className="dash-chart-footer"><span>{total.toLocaleString("en-US")} successful {total === 1 ? "payment" : "payments"}</span><span>{visible[0]?.label} – {visible[visible.length-1]?.label}</span></div>
  </div>;
}
