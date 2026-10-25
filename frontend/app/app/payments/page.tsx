"use client";

import { toast } from "sonner";
import { useEffect, useState } from "react";
import { useRealtimeEvent } from "@/components/Realtime";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ListToolbar } from "@/components/ListToolbar";
import { ListFilterSheet } from "@/components/ListFilterSheet";
import { FieldSelect, NONE } from "@/components/FieldSelect";
import { SelectItem } from "@/components/ui/select";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { api, ApiError } from "@/lib/api";
import { money, statusTone, titleCase } from "@/lib/format";
import type { PaymentOut } from "@/lib/types";

export default function PaymentsPage() {
  const [payments, setPayments] = useState<PaymentOut[] | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [method, setMethod] = useState("all");
  const [statusFilter, setStatusFilter] = useState(NONE);
  const [kindFilter, setKindFilter] = useState(NONE);
  const [refundFilter, setRefundFilter] = useState(NONE);
  const [exportFrom, setExportFrom] = useState(() => new Date().toISOString().slice(0, 7) + "-01");
  const [exportTo, setExportTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [refundFor, setRefundFor] = useState<PaymentOut | null>(null);

  async function load() {
    setError("");
    try {
      setPayments(await api.get<PaymentOut[]>("/payments"));
    } catch (e) {
      setError((e as ApiError).message);
      setPayments([]);
    }
  }

  useEffect(() => {
    queueMicrotask(() => void load());
  }, []);

  useRealtimeEvent(["payment.recorded"], () => void load());

  // Only member fees (routed through the gym's Connect account) are refundable
  // here. SaaS subscription charges go through the platform account and are
  // managed in billing settings, not refunded on this screen.
  const refundable = (p: PaymentOut) =>
    p.kind === "member_fee" &&
    p.status === "succeeded" &&
    p.method === "card" &&
    p.refunded_amount < p.amount;

  const all = payments ?? [];

  // Only show a method tab when that method actually appears in the ledger —
  // a gym that never takes mobile wallet shouldn't carry an empty tab.
  const tabs = [
    { value: "all", label: "All", count: all.length },
    ...Array.from(new Set(all.map((p) => p.stripe_payment_method_type || p.method))).map((m) => ({
      value: m,
      label: titleCase(m.replaceAll("_", " ")),
      count: all.filter((p) => (p.stripe_payment_method_type || p.method) === m).length,
    })),
  ];

  const q = search.trim().toLowerCase();
  const filtered = all.filter((p) => {
    if (method !== "all" && (p.stripe_payment_method_type || p.method) !== method) return false;
    if (statusFilter !== NONE && p.status !== statusFilter) return false;
    if (kindFilter !== NONE && p.kind !== kindFilter) return false;
    if (refundFilter === "refundable" && !refundable(p)) return false;
    if (refundFilter === "refunded" && p.refunded_amount <= 0) return false;
    if (refundFilter === "not_refunded" && p.refunded_amount > 0) return false;
    if (!q) return true;
    return (
      p.kind.toLowerCase().includes(q) ||
      p.method.toLowerCase().includes(q) ||
      (p.stripe_payment_method_type || "").toLowerCase().includes(q) ||
      p.status.toLowerCase().includes(q) ||
      (p.paid_at || p.created_at).slice(0, 10).includes(q) ||
      String(p.amount).includes(q)
    );
  });
  const activePaymentFilterCount = [statusFilter, kindFilter, refundFilter].filter((v) => v !== NONE).length;
  function clearPaymentFilters() { setStatusFilter(NONE); setKindFilter(NONE); setRefundFilter(NONE); }

  function exportFilteredPayments() {
    const columns = ["payment_id", "member_id", "plan_id", "kind", "method", "provider_method", "status", "amount", "tax_amount", "refunded_amount", "currency", "promo_code", "created_at", "paid_at"];
    const csvCell = (value: unknown) => {
      const text = String(value ?? "");
      const safe = /^[\s]*[=+@-]/.test(text) ? `'${text}` : text;
      return `"${safe.replaceAll('"', '""')}"`;
    };
    const rows = filtered.map((p) => [
      p.id, p.member_id, p.plan_id, p.kind, p.method, p.stripe_payment_method_type,
      p.status, p.amount, p.tax_amount, p.refunded_amount, p.currency, p.promo_code,
      p.created_at, p.paid_at,
    ]);
    const csv = [columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `gym-payments-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="All money events for this gym — refunds are web-only"
        action={<Button variant="secondary" disabled={filtered.length === 0} onClick={exportFilteredPayments}>Export filtered CSV</Button>}
      />

      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      {/* A refund is work you do against the ledger behind this sheet, so it rides
          in a sheet: the payments table stays in view while you fill it in. */}
      <section className="mb-5 flex flex-wrap items-end gap-3 border border-border p-4" aria-label="Accounting export">
        <Input type="date" label="Accounting export from" value={exportFrom} onChange={(event) => setExportFrom(event.target.value)} />
        <Input type="date" label="Through" value={exportTo} min={exportFrom} onChange={(event) => setExportTo(event.target.value)} />
        <Button variant="secondary" disabled={!exportFrom || !exportTo || exportTo < exportFrom} onClick={() => window.location.assign(`/api/download/finance/payments.csv?date_from=${exportFrom}&date_to=${exportTo}`)}>Download accounting CSV</Button>
        <p className="w-full text-xs text-muted-foreground">Uses the gym’s timezone. Refund columns show lifetime totals for each payment; this export is a current ledger snapshot.</p>
      </section>
      <Sheet open={!!refundFor} onOpenChange={(open) => { if (!open) setRefundFor(null); }}>
        <SheetContent>
          <SheetHeader className="flex items-start justify-between gap-4">
            <div>
              <SheetTitle>Process refund</SheetTitle>
              <SheetDescription>
                {refundFor ? `Up to ${money(refundFor.amount - refundFor.refunded_amount, refundFor.currency)} available` : ""}
              </SheetDescription>
            </div>
          </SheetHeader>
          {refundFor && (
            <RefundForm
              payment={refundFor}
              onClose={() => setRefundFor(null)}
              onDone={() => {
                setRefundFor(null);
                load();
              }}
            />
          )}
        </SheetContent>
      </Sheet>

      <ListToolbar
        tabs={tabs}
        value={method}
        onChange={setMethod}
        search={search}
        onSearch={(v) => setSearch(v)}
        searchPlaceholder="Search payments…"
      >
          <ListFilterSheet title="Filter payments" description="Narrow the ledger by transaction type and refund status." activeCount={activePaymentFilterCount} resultCount={filtered.length} onClear={clearPaymentFilters}>
            <FieldSelect label="Payment status" value={statusFilter} onChange={setStatusFilter}>
              <SelectItem value={NONE}>Any status</SelectItem>
              {Array.from(new Set(all.map((p) => p.status))).sort().map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Transaction type" value={kindFilter} onChange={setKindFilter}>
              <SelectItem value={NONE}>Any type</SelectItem>
              {Array.from(new Set(all.map((p) => p.kind))).sort().map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </FieldSelect>
            <FieldSelect label="Refund status" value={refundFilter} onChange={setRefundFilter}>
              <SelectItem value={NONE}>Any refund status</SelectItem><SelectItem value="refundable">Can be refunded</SelectItem><SelectItem value="refunded">Has refund</SelectItem><SelectItem value="not_refunded">No refund</SelectItem>
            </FieldSelect>
          </ListFilterSheet>
      </ListToolbar>

      {/* Table surface: hairline border, square corners, flat background. */}
      <div className="mt-3">
        {payments === null ? (
          <Spinner label="Loading payments..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No payments yet"
            hint={
              all.length === 0
                ? "Member and cash payments will appear here."
                : "No payments match the current filter."
            }
            icon={
              <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z" /></svg>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE}>
              <thead>
                <tr className={THEAD_ROW}>
                  <th className={`${TH} ${CELL_FIRST}`}>Date</th>
                  <th className={`${TH} ${CELL}`}>Kind</th>
                  <th className={`${TH} ${CELL}`}>Method</th>
                  <th className={`${TH} ${CELL}`}>Amount</th>
                  <th className={`${TH} ${CELL}`}>Refunded</th>
                  <th className={`${TH} ${CELL}`}>Status</th>
                  <th className={`${TH} ${CELL_LAST} text-right`}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} className={`${TR} transition-colors hover:bg-[var(--background)]`}>
                    <td className={`${TD} ${CELL_FIRST} py-2.5 whitespace-nowrap tabular-nums`}>{(p.paid_at || p.created_at).slice(0, 10)}</td>
                    <td className={`${TD} ${CELL} py-2.5 text-[var(--foreground-muted)]`}>{titleCase(p.kind)}</td>
                    <td className={`${TD} ${CELL} py-2.5`}>
                      <span className="inline-flex items-center gap-1.5">
                        {p.method === "card" && <svg className="h-4 w-4 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" /></svg>}
                        {p.method === "cash" && <svg className="h-4 w-4 text-[var(--muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                        {titleCase((p.stripe_payment_method_type || p.method).replaceAll("_", " "))}
                      </span>
                    </td>
                    <td className={`${TD} ${CELL} py-2.5 tabular-nums font-medium text-[var(--foreground)]`}>{money(p.amount, p.currency)}</td>
                    <td className={`${TD} ${CELL} py-2.5 tabular-nums text-[var(--foreground-muted)]`}>
                      {p.refunded_amount > 0 ? money(p.refunded_amount, p.currency) : "—"}
                    </td>
                    <td className={`${TD} ${CELL} py-2.5`}>
                      <Badge tone={statusTone(p.status)}>{titleCase(p.status)}</Badge>
                    </td>
                    <td className={`${TD} ${CELL_LAST} py-2.5 text-right`}>
                      <button type="button" className="mr-3 text-xs font-medium text-brand hover:underline" onClick={() => { void navigator.clipboard.writeText(p.id).then(() => toast.success("Payment ID copied.")).catch(() => toast.error("Could not copy payment ID.")); }}>Copy ID</button>
                      <a href={`/api/download/finance/payments/${encodeURIComponent(p.id)}/evidence.zip`} className="mr-3 text-xs font-medium text-brand hover:underline" aria-label={`Download evidence for payment ${p.id}`}>Evidence</a>
                      {refundable(p) && (
                        <Button variant="ghost" onClick={() => setRefundFor(p)}>
                          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" /></svg>
                          Refund
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function RefundForm({
  payment,
  onClose,
  onDone,
}: {
  payment: PaymentOut;
  onClose: () => void;
  onDone: () => void;
}) {
  const max = payment.amount - payment.refunded_amount;
  const [amount, setAmount] = useState(String(max));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/payments/refund", {
        payment_id: payment.id,
        amount: parseFloat(amount) || null,
        reason: reason || null,
      }, { "Idempotency-Key": crypto.randomUUID() });
      onDone();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    /* `flex` + the form filling the sheet: header and footer stay put, only the
       fields scroll. */
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
      <SheetBody className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <div className="grid grid-cols-2 gap-4">
          <Input label="Amount" type="number" min="0" step="0.01" max={String(max)} value={amount} onChange={(e) => setAmount(e.target.value)} />
          <Input label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Optional" />
        </div>
      </SheetBody>
      <SheetFooter>
        <SheetClose asChild>
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
        </SheetClose>
        <Button type="submit" variant="danger" loading={loading}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
          Refund
        </Button>
      </SheetFooter>
    </form>
  );
}
