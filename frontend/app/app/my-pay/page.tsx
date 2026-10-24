"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, EmptyState, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fmtDate, money, titleCase } from "@/lib/format";
import type { MyPayStatement, OrganizationOut } from "@/lib/types";

const LINES: { label: string; key: keyof MyPayStatement }[] = [
  { label: "Fixed pay", key: "fixed" },
  { label: "Hourly pay", key: "hourly_amount" },
  { label: "Class pay", key: "class_amount" },
  { label: "Commission", key: "commission_amount" },
  { label: "Bonus", key: "bonus" },
  { label: "Deductions", key: "deductions" },
  { label: "Advance repayment", key: "advance_repayment" },
];

export default function MyPayPage() {
  const [statements, setStatements] = useState<MyPayStatement[] | null>(null);
  const [currency, setCurrency] = useState("USD");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<MyPayStatement[]>("/payroll/me"),
      api.get<OrganizationOut>("/organizations/me"),
    ]).then(([rows, org]) => {
      setStatements(rows);
      setCurrency(org.default_currency || "USD");
    }).catch((e) => {
      setError((e as ApiError).message);
      setStatements([]);
    });
  }, []);

  return (
    <>
      <PageHeader title="My pay" subtitle="Your finalized pay statements" />
      <p className="mb-5 border border-border bg-background px-4 py-3 text-xs leading-5 text-muted-foreground">
        Your gym records payouts here. Check the reference against your bank, wallet, or cash receipt.
      </p>
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {statements === null ? <Spinner label="Loading your pay statements…" /> : statements.length === 0 ? (
        <EmptyState title="No finalized pay statements" hint="Your statements will appear here after the gym finalizes payroll." />
      ) : <div className="divide-y divide-border border border-border bg-background">
        {statements.map((statement) => (
          <details key={statement.payroll_run_id} className="group px-4 py-4">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-5 gap-y-2 [&::-webkit-details-marker]:hidden">
              <span className="min-w-40 flex-1 text-sm font-medium">{fmtDate(statement.period_start)} – {fmtDate(statement.period_end)}</span>
              <Badge tone={statement.entry_paid_at ? "success" : "warning"}>{statement.entry_paid_at ? "Payout recorded" : "Awaiting payout"}</Badge>
              <span className="min-w-28 text-right text-sm font-semibold tabular-nums">{money(statement.net, currency)}</span>
              <span className="text-xs text-muted-foreground group-open:rotate-180" aria-hidden="true">⌄</span>
            </summary>
            <div className="mt-4 border-t border-border pt-3">
              <div className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                <span>{statement.hours_worked} hours</span>
                <span>{statement.classes_taught} classes</span>
                <span>{titleCase(statement.payout_method.replaceAll("_", " "))}</span>
                {statement.entry_paid_at && <span>Recorded {fmtDate(statement.entry_paid_at)}</span>}
                {statement.payout_reference && <span>Reference: {statement.payout_reference}</span>}
              </div>
              <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                {LINES.map(({ label, key }) => <div key={key} className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="m-0 tabular-nums">{money(statement[key] as number, currency)}</dd>
                </div>)}
                <div className="flex justify-between gap-3 border-t border-border pt-2 font-semibold sm:col-span-2">
                  <dt>Net pay</dt><dd className="m-0 tabular-nums">{money(statement.net, currency)}</dd>
                </div>
              </dl>
            </div>
          </details>
        ))}
      </div>}
    </>
  );
}
