"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Card, CardHeader, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, titleCase } from "@/lib/format";

type Totals = { gross_receipts: string; taxes_collected: string; refunds: string; operating_expenses: string; net_collections: string; operating_cash_surplus: string; legacy_refund_payments: number; expense_categories: Record<string, string>; monthly_expenses: Record<string, string> };
type Report = { by_currency: Record<string, Totals>; basis: string };

export function OperatingReportCard() {
  const [from, setFrom] = useState(() => new Date().toISOString().slice(0, 7) + "-01");
  const [through, setThrough] = useState(() => new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load(start: string, end: string) {
    setBusy(true); setError("");
    try { setReport(await api.get<Report>(`/finance/operating-report?date_from=${start}&date_to=${end}`)); }
    catch (cause) { setError((cause as ApiError).message || "Could not load the operating report."); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10);
    queueMicrotask(() => void load(today.slice(0, 7) + "-01", today));
  }, []);
  function submit(event: FormEvent) { event.preventDefault(); void load(from, through); }
  return <Card><CardHeader title="Income and operating expenses" subtitle="Recorded receipts, refunds, expense categories, and monthly spending by currency" />
    <div className="space-y-5 p-5">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <Input label="From" type="date" required value={from} onChange={(event) => setFrom(event.target.value)} />
        <Input label="Through" type="date" required min={from} value={through} onChange={(event) => setThrough(event.target.value)} />
        <Button type="submit" variant="secondary" disabled={busy}>Update report</Button>
      </form>
      {error && <Alert>{error}</Alert>}
      {busy && <p role="status" className="text-sm text-muted-foreground">Loading operating totals…</p>}
      {!busy && report && Object.entries(report.by_currency).map(([currency, totals]) => <section key={currency} aria-label={`${currency} operating totals`} className="space-y-4 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">{currency}</h3>
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[
          ["Gross receipts", totals.gross_receipts], ["Recorded refunds", totals.refunds],
          ["Recorded expenses", totals.operating_expenses], ["Recorded operating balance", totals.operating_cash_surplus],
        ].map(([label, amount]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{money(Number(amount), currency)}</dd></div>)}</dl>
        <p className="text-xs text-muted-foreground">Collected tax included above: {money(Number(totals.taxes_collected), currency)}. {totals.legacy_refund_payments > 0 ? `${totals.legacy_refund_payments} historical refund record(s) use the last known refund date.` : ""}</p>
        <div className="grid gap-5 sm:grid-cols-2">
          <div><h4 className="mb-2 text-xs font-semibold">Expenses by category</h4><dl className="space-y-2 text-sm">{Object.entries(totals.expense_categories).map(([category, amount]) => <div key={category} className="flex justify-between gap-3"><dt>{titleCase(category)}</dt><dd className="tabular-nums">{money(Number(amount), currency)}</dd></div>)}</dl></div>
          <div><h4 className="mb-2 text-xs font-semibold">Monthly expenses</h4><dl className="space-y-2 text-sm">{Object.entries(totals.monthly_expenses).map(([month, amount]) => <div key={month} className="flex justify-between gap-3"><dt>{month}</dt><dd className="tabular-nums">{money(Number(amount), currency)}</dd></div>)}</dl></div>
        </div>
      </section>)}
      {!busy && report && Object.keys(report.by_currency).length === 0 && <p className="text-sm text-muted-foreground">No recorded activity in this date range.</p>}
      {report && <p className="text-xs leading-5 text-muted-foreground">{report.basis}</p>}
    </div></Card>;
}
