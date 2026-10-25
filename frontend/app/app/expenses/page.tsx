"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, titleCase } from "@/lib/format";
import type { OrganizationOut } from "@/lib/types";

type Expense = {
  id: string; category: string; description: string; vendor: string | null;
  amount: string; currency: string; incurred_on: string; voided_at: string | null;
};
type ExpenseList = { items: Expense[]; totals_by_currency: Record<string, string> };
const categories = ["rent", "payroll", "utilities", "equipment", "marketing", "maintenance", "supplies", "other"];
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10);

export default function ExpensesPage() {
  const [data, setData] = useState<ExpenseList | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [form, setForm] = useState({ category: "rent", description: "", vendor: "", amount: "", currency: "USD", incurred_on: today() });

  const load = useCallback(async (from = "", to = "") => {
    try {
      const params = new URLSearchParams();
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
      const query = params.toString();
      const suffix = query ? `?${query}` : "";
      const [expenses, org] = await Promise.all([
        api.get<ExpenseList>(`/expenses${suffix}`), api.get<OrganizationOut>("/organizations/me"),
      ]);
      setData(expenses);
      setForm((current) => current.currency === "USD" ? { ...current, currency: org.default_currency || "USD" } : current);
      setError("");
    }
    catch (e) { setError((e as ApiError).message); setData({ items: [], totals_by_currency: {} }); }
  }, []);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      await api.post<Expense>("/expenses", { ...form, vendor: form.vendor || null }, { "Idempotency-Key": crypto.randomUUID() });
      setForm((current) => ({ ...current, description: "", vendor: "", amount: "" }));
      await load(dateFrom, dateTo);
    } catch (e) { setError((e as ApiError).message); }
    finally { setSaving(false); }
  }

  async function voidExpense(expense: Expense) {
    const reason = window.prompt("Why are you voiding this expense?");
    if (!reason?.trim()) return;
    try {
      await api.post(`/expenses/${expense.id}/void`, { reason }, { "Idempotency-Key": crypto.randomUUID() });
      await load(dateFrom, dateTo);
    } catch (e) { setError((e as ApiError).message); }
  }

  function exportCsv() {
    const params = new URLSearchParams();
    if (dateFrom) params.set("date_from", dateFrom);
    if (dateTo) params.set("date_to", dateTo);
    const query = params.toString();
    window.location.assign(`/api/download/expenses/export.csv${query ? `?${query}` : ""}`);
  }

  return <>
    <PageHeader title="Expenses" subtitle="Record and review gym operating costs. Totals stay separate by currency." />
    {error && <div className="mb-4"><Alert>{error}</Alert></div>}
    <section className="mb-5 rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold">Record an expense</h2>
      <form onSubmit={(event) => void create(event)} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="grid gap-1 text-xs text-muted-foreground">Category<select className="h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>{categories.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label>
        <label className="grid gap-1 text-xs text-muted-foreground">Description<Input required maxLength={300} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="grid gap-1 text-xs text-muted-foreground">Vendor (optional)<Input maxLength={160} value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} /></label>
        <label className="grid gap-1 text-xs text-muted-foreground">Amount<Input required type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
        <label className="grid gap-1 text-xs text-muted-foreground">Currency<Input required maxLength={3} minLength={3} value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} /></label>
        <label className="grid gap-1 text-xs text-muted-foreground">Date<Input required type="date" value={form.incurred_on} onChange={(e) => setForm({ ...form, incurred_on: e.target.value })} /></label>
        <div className="sm:col-span-2 lg:col-span-6"><Button type="submit" disabled={saving}>{saving ? "Saving…" : "Add expense"}</Button></div>
      </form>
    </section>
    <section className="mb-4 flex flex-wrap gap-2" aria-label="Expense totals">
      {data && Object.entries(data.totals_by_currency).map(([currency, amount]) => <div key={currency} className="rounded-lg border border-border px-4 py-3"><div className="text-xs text-muted-foreground">Recorded expenses · {currency}</div><div className="mt-1 text-lg font-semibold tabular-nums">{money(Number(amount), currency)}</div></div>)}
    </section>
    <form onSubmit={(event) => { event.preventDefault(); void load(dateFrom, dateTo); }} className="mb-3 flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-xs text-muted-foreground">From<Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label>
      <label className="grid gap-1 text-xs text-muted-foreground">To<Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label>
      <Button type="submit" variant="secondary">Apply dates</Button>
      <Button type="button" variant="secondary" onClick={exportCsv}>Download CSV</Button>
      {(dateFrom || dateTo) && <Button type="button" variant="ghost" onClick={() => { setDateFrom(""); setDateTo(""); void load("", ""); }}>Clear</Button>}
    </form>
    {data === null ? <Spinner label="Loading expenses…" /> : data.items.length === 0 ? <EmptyState title="No expenses recorded" hint="Add rent, utilities, equipment, and other operating costs above." /> :
      <div className="overflow-x-auto rounded-xl border border-border"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-b border-border text-xs text-muted-foreground"><tr><th className="px-4 py-3">Date</th><th className="px-4 py-3">Expense</th><th className="px-4 py-3">Category</th><th className="px-4 py-3 text-right">Amount</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Action</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id} className="border-b border-border last:border-0"><td className="px-4 py-3 text-muted-foreground">{item.incurred_on}</td><td className="px-4 py-3"><div className="font-medium">{item.description}</div><div className="text-xs text-muted-foreground">{item.vendor || "No vendor"}</div></td><td className="px-4 py-3">{titleCase(item.category)}</td><td className="px-4 py-3 text-right font-medium tabular-nums">{money(Number(item.amount), item.currency)}</td><td className="px-4 py-3">{item.voided_at ? <Badge tone="neutral" size="sm">Voided</Badge> : <Badge tone="success" size="sm">Recorded</Badge>}</td><td className="px-4 py-3">{!item.voided_at && <Button variant="ghost" onClick={() => void voidExpense(item)}>Void</Button>}</td></tr>)}</tbody></table><p className="px-4 py-3 text-xs text-muted-foreground">Showing the latest 1,000 records. Void entries are retained for audit and excluded from totals.</p></div>}
  </>;
}
