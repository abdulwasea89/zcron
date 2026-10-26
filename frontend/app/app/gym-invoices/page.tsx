"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, statusTone } from "@/lib/format";
import { useModuleGate } from "@/hooks/useModuleGate";

type Member = { member_id: string; full_name: string; display_name: string | null; email: string; role: string };
type Invoice = {
  id: string; invoice_number: string; member_id: string; member_name: string | null; member_email: string | null;
  description: string; issue_date: string; due_date: string; status: string; subtotal: string; tax_amount: string;
  total: string; paid_amount: string; balance_due: string; currency: string; notes: string | null; email_accepted: boolean;
};
const dateAfterWeek = () => { const value = new Date(); value.setDate(value.getDate() + 7); return value.toISOString().slice(0, 10); };

export default function GymInvoicesPage() {
  const { ready } = useModuleGate("gym_invoices");
  const [members, setMembers] = useState<Member[]>([]);
  const [invoices, setInvoices] = useState<Invoice[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [memberId, setMemberId] = useState("");
  const [description, setDescription] = useState("");
  const [subtotal, setSubtotal] = useState("");
  const [tax, setTax] = useState("0.00");
  const [dueDate, setDueDate] = useState(dateAfterWeek);
  const [paying, setPaying] = useState<Invoice | null>(null);
  const [paymentAmount, setPaymentAmount] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");

  async function load() {
    setError("");
    try {
      const [rows, roster] = await Promise.all([api.get<Invoice[]>("/gym-invoices"), api.get<Member[]>("/members?role=member")]);
      setInvoices(rows);
      setMembers(roster.filter((member) => member.role === "member"));
    } catch (exception) { setError((exception as ApiError).message); setInvoices([]); }
  }
  useEffect(() => { queueMicrotask(() => void load()); }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy("create");
    try {
      await api.post("/gym-invoices", { member_id: memberId, description, subtotal, tax_amount: tax || "0.00", due_date: dueDate });
      setDescription(""); setSubtotal(""); setTax("0.00"); await load();
    } catch (exception) { toast.error((exception as ApiError).message); }
    finally { setBusy(""); }
  }
  async function act(invoice: Invoice, action: "send" | "void") {
    setBusy(invoice.id);
    try { await api.post(`/gym-invoices/${invoice.id}/${action}`); await load(); }
    catch (exception) { toast.error((exception as ApiError).message); }
    finally { setBusy(""); }
  }
  async function recordPayment(event: React.FormEvent) {
    event.preventDefault(); if (!paying) return; setBusy(paying.id);
    try {
      await api.post(`/gym-invoices/${paying.id}/payments`, { amount: paymentAmount || null, method: paymentMethod }, { "Idempotency-Key": crypto.randomUUID() });
      setPaying(null); setPaymentAmount(""); await load();
    } catch (exception) { toast.error((exception as ApiError).message); }
    finally { setBusy(""); }
  }

  if (!ready) return <Spinner label="Loading invoices…" />;

  return <main className="mx-auto max-w-6xl space-y-5 p-5 md:p-8">
    <PageHeader title="Member invoices" subtitle="Create charges, send due dates, and track collected balances." />
    {error && <Alert>{error}</Alert>}
    <form onSubmit={create} className="grid gap-3 border border-border p-4 md:grid-cols-12" aria-label="Create member invoice">
      <label className="text-xs text-muted-foreground md:col-span-3">Member<select required value={memberId} onChange={(event) => setMemberId(event.target.value)} className="mt-1 block h-10 w-full border border-border bg-background px-3 text-sm text-foreground"><option value="">Choose member</option>{members.map((member) => <option key={member.member_id} value={member.member_id}>{member.display_name || member.full_name} · {member.email}</option>)}</select></label>
      <Input label="Description" value={description} onChange={(event) => setDescription(event.target.value)} required maxLength={240} className="md:col-span-3" />
      <Input label="Subtotal" type="number" min="0.01" step="0.01" value={subtotal} onChange={(event) => setSubtotal(event.target.value)} required className="md:col-span-2" />
      <Input label="Tax" type="number" min="0" step="0.01" value={tax} onChange={(event) => setTax(event.target.value)} className="md:col-span-1" />
      <Input label="Due date" type="date" min={new Date().toISOString().slice(0, 10)} value={dueDate} onChange={(event) => setDueDate(event.target.value)} required className="md:col-span-2" />
      <div className="flex items-end md:col-span-1"><Button type="submit" disabled={!members.length || busy !== ""} loading={busy === "create"}>Create</Button></div>
    </form>
    {invoices === null ? <Spinner label="Loading invoices…" /> : <div className="overflow-x-auto border border-border"><table className="w-full text-left text-sm"><thead className="border-b border-border bg-muted/30 text-xs text-muted-foreground"><tr>{["Invoice", "Member", "Due", "Total", "Paid", "Balance", "Status", ""].map((label) => <th key={label} className="px-3 py-3 font-medium">{label}</th>)}</tr></thead><tbody className="divide-y divide-border">
      {invoices.map((invoice) => <tr key={invoice.id}><td className="px-3 py-3"><div className="font-medium">{invoice.invoice_number}</div><div className="text-xs text-muted-foreground">{invoice.description}</div></td><td className="px-3 py-3">{invoice.member_name || invoice.member_email}</td><td className="px-3 py-3 tabular-nums">{invoice.due_date}</td><td className="px-3 py-3 tabular-nums">{money(Number(invoice.total), invoice.currency)}</td><td className="px-3 py-3 tabular-nums">{money(Number(invoice.paid_amount), invoice.currency)}</td><td className="px-3 py-3 tabular-nums font-medium">{money(Number(invoice.balance_due), invoice.currency)}</td><td className="px-3 py-3"><Badge tone={statusTone(invoice.status)}>{invoice.status}</Badge></td><td className="px-3 py-3 text-right">
        {invoice.status === "draft" && <Button variant="secondary" disabled={busy !== ""} loading={busy === invoice.id} onClick={() => void act(invoice, "send")}>Send</Button>}
        {["sent", "partial", "overdue"].includes(invoice.status) && <Button variant="secondary" disabled={busy !== ""} onClick={() => { setPaying(invoice); setPaymentAmount(""); }}>Record payment</Button>}
        {["draft", "sent"].includes(invoice.status) && Number(invoice.paid_amount) === 0 && <Button className="ml-1" variant="ghost" disabled={busy !== ""} onClick={() => void act(invoice, "void")}>Void</Button>}
      </td></tr>)}
      {invoices.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-muted-foreground">No member invoices yet. Create one above to track an amount owed.</td></tr>}
    </tbody></table></div>}
    {paying && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaying(null); }}><form onSubmit={recordPayment} className="w-full max-w-md space-y-4 border border-border bg-background p-5" role="dialog" aria-modal="true" aria-labelledby="payment-title"><div><h2 id="payment-title" className="text-base font-semibold">Record invoice payment</h2><p className="mt-1 text-sm text-muted-foreground">Balance due: {money(Number(paying.balance_due), paying.currency)}</p></div><Input label="Amount (leave blank to settle balance)" type="number" min="0.01" max={paying.balance_due} step="0.01" value={paymentAmount} onChange={(event) => setPaymentAmount(event.target.value)} /><label className="block text-xs text-muted-foreground">Method<select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)} className="mt-1 block h-10 w-full border border-border bg-background px-3 text-sm text-foreground"><option value="cash">Cash</option><option value="bank_transfer">Bank transfer</option><option value="mobile_wallet">Mobile wallet</option></select></label><div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setPaying(null)}>Cancel</Button><Button type="submit" disabled={busy !== ""} loading={busy === paying.id}>Record payment</Button></div></form></div>}
  </main>;
}
