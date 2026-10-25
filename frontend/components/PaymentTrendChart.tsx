"use client";

import { useId } from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { ChartContainer } from "@/components/ui/chart";

export type PaymentTrendPoint = {
  date: string;
  label: string;
  axisLabel: string;
  count: number;
};

function PaymentTooltip({ active, payload }: {
  active?: boolean;
  payload?: Array<{ payload: PaymentTrendPoint; value: number }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="border border-border bg-background px-3 py-2 text-[12px] shadow-sm">
      <p className="font-medium">{point.label}</p>
      <p className="mt-1 text-muted-foreground">{point.count} {point.count === 1 ? "payment" : "payments"}</p>
    </div>
  );
}

export function PaymentTrendChart({ data }: { data: PaymentTrendPoint[] }) {
  const gradientId = `payment-fill-${useId().replace(/:/g, "")}`;
  const total = data.reduce((sum, day) => sum + day.count, 0);

  return (
    <div>
      {total === 0 ? (
        <div className="flex h-[250px] flex-col items-center justify-center px-5 text-center">
          <p className="text-[13px] font-medium">No successful payments yet</p>
          <p className="mt-1 text-[12px] text-muted-foreground">Daily activity will appear here after a payment is recorded.</p>
        </div>
      ) : (
        <div className="px-4 pb-4 pt-6" role="img" aria-label={`Successful payments over the last 14 days: ${data.map((day) => `${day.label}, ${day.count}`).join("; ")}`}>
          <ChartContainer config={{ count: { label: "Payments", color: "var(--chart-1)" } }} className="aspect-auto h-[250px] w-full">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-count)" stopOpacity={0.34} />
                  <stop offset="100%" stopColor="var(--color-count)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="axisLabel" tickLine={false} axisLine={false} tickMargin={10} interval={0} />
              <YAxis hide allowDecimals={false} domain={[0, "auto"]} />
              <Tooltip cursor={false} content={<PaymentTooltip />} />
              <Area type="monotone" dataKey="count" stroke="var(--color-count)" strokeWidth={2} fill={`url(#${gradientId})`} fillOpacity={1} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false} />
            </AreaChart>
          </ChartContainer>
        </div>
      )}
      <div className="border-t border-border px-5 py-4">
        <p className="text-[13px] font-semibold">{total} successful {total === 1 ? "payment" : "payments"} in this period</p>
        <p className="mt-1 text-[12px] text-muted-foreground">{data[0]?.label} – {data[data.length - 1]?.label}</p>
      </div>
    </div>
  );
}
