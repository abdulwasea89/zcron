"use client";

import { useEffect, useState } from "react";
import { Alert, Card, CardHeader, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";

type StaffMetric = {
  user_id: string;
  name: string;
  completed_tasks: number;
  lead_responses: number;
  shift_hours: number;
  cash_by_currency: Record<string, string>;
};

export function StaffPerformanceCard() {
  const [staff, setStaff] = useState<StaffMetric[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      void api.get<{ staff: StaffMetric[] }>("/staff/performance?days=30")
        .then((report) => { if (active) setStaff(report.staff); })
        .catch((cause) => { if (active) setError((cause as ApiError).message || "Could not load staff activity."); });
    });
    return () => { active = false; };
  }, []);

  return <Card className="mb-5">
    <CardHeader title="Team activity · last 30 days" subtitle="Recorded work only; counts are not staff quality ratings." />
    <div className="p-4">
      {error ? <Alert>{error}</Alert> : staff === null ? <Spinner label="Loading team activity…" /> : staff.length === 0 ? <p className="text-sm text-muted-foreground">No active staff to report.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[650px] text-left text-xs">
            <thead><tr className="border-b border-border text-muted-foreground"><th className="py-2 pr-3 font-medium">Staff</th><th className="px-3 py-2 font-medium">Lead responses</th><th className="px-3 py-2 font-medium">Tasks completed</th><th className="px-3 py-2 font-medium">Shift hours</th><th className="px-3 py-2 font-medium">Cash logged</th></tr></thead>
            <tbody>{staff.map((person) => <tr key={person.user_id} className="border-b border-border last:border-0"><th scope="row" className="py-3 pr-3 font-medium text-foreground">{person.name}</th><td className="px-3 py-3 tabular-nums">{person.lead_responses}</td><td className="px-3 py-3 tabular-nums">{person.completed_tasks}</td><td className="px-3 py-3 tabular-nums">{person.shift_hours.toFixed(2)}</td><td className="px-3 py-3">{Object.entries(person.cash_by_currency).map(([currency, amount]) => money(Number(amount), currency)).join(" · ") || "—"}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  </Card>;
}
