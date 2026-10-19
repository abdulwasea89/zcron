"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { ListToolbar } from "@/components/ListToolbar";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useRealtimeEvent } from "@/components/Realtime";
import { Alert, Avatar, Badge, Button, EmptyState, Input, Spinner } from "@/components/ui";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { enqueueOfflineMutation } from "@/lib/offline-mutations";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { money, roleLabel, titleCase } from "@/lib/format";
import type { CashMemberItem, CashPaymentOut, PlanOut, ReconciliationOut } from "@/lib/types";

function localDate() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

type CashHistoryItem = {
  id: string;
  member_name: string | null;
  plan_name: string | null;
  amount: number;
  currency: string;
  method: string;
  status: string;
  paid_at: string | null;
};

export default function CashPage() {
  const [history, setHistory] = useState<CashHistoryItem[] | null>(null);
  const [error, setError] = useState("");
  const [methodFilter, setMethodFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [showPayment, setShowPayment] = useState(false);
  const [showReconcile, setShowReconcile] = useState(false);

  async function loadHistory() {
    try {
      setHistory(await api.get<CashHistoryItem[]>("/cash/history"));
      setError("");
    } catch (caught) {
      setError((caught as ApiError).message);
      setHistory([]);
    }
  }

  useEffect(() => { queueMicrotask(() => void loadHistory()); }, []);
  useRealtimeEvent(["payment.recorded"], () => void loadHistory());
  useEffect(() => {
    const handleSynced = (event: Event) => {
      if ((event as CustomEvent<{ path?: string }>).detail?.path === "/cash/log") void loadHistory();
    };
    window.addEventListener("acron:offline-mutation-synced", handleSynced);
    return () => window.removeEventListener("acron:offline-mutation-synced", handleSynced);
  }, []);

  const all = history ?? [];
  const filtered = all.filter((item) =>
    (methodFilter === "all" || item.method === methodFilter) &&
    `${item.member_name || "Walk-in"} ${item.plan_name || ""} ${item.method} ${item.amount}`
      .toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <>
      <PageHeader title="Cash & offline payments" subtitle="Record payments and reconcile the drawer."
        action={<div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowReconcile(true)}>Close drawer</Button>
          <Button onClick={() => setShowPayment(true)}>+ New payment</Button>
        </div>}
      />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}

      <Sheet open={showPayment} onOpenChange={setShowPayment}>
        <SheetContent className="w-full min-w-0 overflow-hidden [--sheet-max-w:560px]">
          <SheetHeader><SheetTitle>Log a payment</SheetTitle><SheetDescription>Record an offline payment and activate the member.</SheetDescription></SheetHeader>
          <SheetBody className="p-0"><LogPayment onSaved={() => void loadHistory()} /></SheetBody>
        </SheetContent>
      </Sheet>
      <Sheet open={showReconcile} onOpenChange={setShowReconcile}>
        <SheetContent>
          <SheetHeader><SheetTitle>Close the drawer</SheetTitle><SheetDescription>Reconcile each business day before handover.</SheetDescription></SheetHeader>
          <SheetBody className="p-0"><Reconcile /></SheetBody>
        </SheetContent>
      </Sheet>

      <ListToolbar
        tabs={[
          { value: "all", label: "All", count: all.length },
          { value: "cash", label: "Cash", count: all.filter((item) => item.method === "cash").length },
          { value: "bank_transfer", label: "Bank transfer", count: all.filter((item) => item.method === "bank_transfer").length },
          { value: "mobile_wallet", label: "Mobile wallet", count: all.filter((item) => item.method === "mobile_wallet").length },
        ]}
        value={methodFilter} onChange={setMethodFilter} search={search} onSearch={setSearch} searchPlaceholder="Search payments…"
      />

      <div className="mt-3 overflow-x-auto">
        {history === null ? <Spinner label="Loading payments…" /> :
          filtered.length === 0 ? <EmptyState title={all.length === 0 ? "No offline payments yet" : "No matching payments"} hint={all.length === 0 ? "Record a payment to see it here." : "Try another method or search term."} /> :
          <table className={TABLE + " min-w-[720px]"}>
            <thead><tr className={THEAD_ROW}>
              <th className={TH + " " + CELL_FIRST}>Member</th>
              <th className={TH + " " + CELL}>Plan</th>
              <th className={TH + " " + CELL}>Amount</th>
              <th className={TH + " " + CELL}>Method</th>
              <th className={TH + " " + CELL}>Status</th>
              <th className={TH + " " + CELL_LAST}>Date</th>
            </tr></thead>
            <tbody>{filtered.map((item) => <tr key={item.id} className={TR}>
              <td className={TD + " " + CELL_FIRST + " py-3 text-[13px] font-medium"}>{item.member_name || "Walk-in"}</td>
              <td className={TD + " " + CELL + " py-3 text-[12px]"}>{item.plan_name || "—"}</td>
              <td className={TD + " " + CELL + " py-3 text-[13px] font-medium tabular-nums"}>{money(item.amount, item.currency)}</td>
              <td className={TD + " " + CELL + " py-3 text-[12px]"}>{titleCase(item.method)}</td>
              <td className={TD + " " + CELL + " py-3"}><Badge tone={item.status === "succeeded" ? "success" : "warning"} size="sm">{titleCase(item.status)}</Badge></td>
              <td className={TD + " " + CELL_LAST + " py-3 text-[12px] text-muted-foreground"}>{item.paid_at ? new Date(item.paid_at).toLocaleDateString() : "—"}</td>
            </tr>)}</tbody>
          </table>}
      </div>
    </>
  );
}

/* ─── Member Combobox ─── */

function MemberCombobox({
  members,
  selected,
  loading,
  query,
  onQueryChange,
  error,
  onChange,
  onClear,
}: {
  members: CashMemberItem[];
  selected: CashMemberItem | null;
  loading: boolean;
  query: string;
  onQueryChange: (q: string) => void;
  error: string;
  onChange: (member: CashMemberItem) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const trimmed = query.trim();

  if (selected) {
    return (
      <div className="min-w-0 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
        <p className="mb-2 text-[10px] font-semibold text-muted-foreground">Member</p>
        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--foreground)]">{selected.full_name || selected.email}</p>
            <p className="truncate text-xs text-[var(--foreground-muted)]">{selected.email}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
            <Badge size="sm" tone={selected.member_status === "active" ? "success" : "warning"}>{selected.member_status}</Badge>
            {selected.role !== "member" && <Badge size="sm" tone="info">{roleLabel(selected.role)}</Badge>}
          </div>
          <button
            type="button"
            onClick={onClear}
            className="shrink-0 rounded-md p-1.5 text-[var(--muted)] transition-colors hover:bg-[var(--background)] hover:text-[var(--foreground)]"
            title="Change member"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <p className="mb-2 text-[10px] font-semibold text-muted-foreground">Member</p>
      <input
        ref={inputRef}
        type="text"
        required
        value={query}
        onChange={(e) => { onQueryChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="Search by name or email…"
        className="w-full rounded-md border border-foreground/20 bg-card px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none transition-colors hover:border-foreground/35 focus:border-brand focus:ring-2 focus:ring-brand/20"
      />
      {open && trimmed.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1.5 max-h-64 animate-pop-in overflow-y-auto rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10">
          {loading && (
            <p className="flex items-center gap-2 px-3.5 py-3 text-sm text-[var(--muted)]">
              <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--muted)]" aria-hidden="true" />
              Searching…
            </p>
          )}
          {!loading && error && (
            <p className="px-3.5 py-3 text-sm text-[var(--danger)]">Couldn&rsquo;t search members: {error}</p>
          )}
          {!loading && !error && members.length === 0 && (
            <p className="px-3.5 py-3 text-sm text-[var(--foreground-muted)]">Nobody in this gym matches &ldquo;{trimmed}&rdquo;</p>
          )}
          {!loading && !error && members.map((m) => (
            <button
              key={m.member_id}
              type="button"
              onClick={() => { onChange(m); setOpen(false); }}
              className="flex w-full items-center gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-[var(--background)]"
            >
              <Avatar name={m.full_name || m.email} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--foreground)]">{m.full_name || m.email}</p>
                <p className="truncate text-xs text-[var(--foreground-muted)]">{m.email}</p>
              </div>
              {m.role !== "member" && <Badge tone="info">{roleLabel(m.role)}</Badge>}
              <Badge tone={m.member_status === "active" ? "success" : "warning"}>{m.member_status}</Badge>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Payment Method Card ─── */

const METHOD_ICONS: Record<string, string> = {
  cash: "M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  bank_transfer: "M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z",
  mobile_wallet: "M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3",
};

const METHOD_LABELS: Record<string, string> = {
  cash: "Cash",
  bank_transfer: "Bank transfer",
  mobile_wallet: "Mobile wallet",
};

function MethodCard({ value, selected, onSelect }: { value: string; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex h-10 min-w-0 items-center justify-center gap-2 rounded-md border px-2 transition-colors duration-150 ${
        selected
          ? "border-brand/50 bg-brand/[0.08]"
          : "border-[var(--border)] bg-[var(--surface)] hover:border-foreground/25 hover:bg-foreground/[0.04]"
      }`}
    >
      <svg className={`h-4 w-4 shrink-0 ${selected ? "text-brand" : "text-muted-foreground"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d={METHOD_ICONS[value]} />
      </svg>
      <span className={`min-w-0 text-center text-[11px] font-medium leading-tight ${selected ? "text-brand" : "text-muted-foreground"}`}>
        {METHOD_LABELS[value]}
      </span>
    </button>
  );
}

/* ─── Plan Select ─── */

function PlanSelect({
  plans,
  value,
  onChange,
}: {
  plans: PlanOut[];
  value: string;
  onChange: (id: string) => void;
}) {
  const selected = plans.find((p) => p.id === value) ?? null;

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label="Membership plan" className="h-auto px-4 py-3">
        <SelectValue placeholder="Choose the plan this payment covers…">
          {selected && (
            <span className="flex items-center gap-2 min-w-0">
              <span className="truncate font-medium text-[var(--foreground)]">{selected.name}</span>
              {selected.featured && <Badge tone="info">Featured</Badge>}
              <span className="ml-auto shrink-0 pl-2 font-bold tabular-nums text-[var(--primary)]">
                {money(selected.price, selected.currency)}
              </span>
            </span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {plans.map((plan) => (
          <SelectItem key={plan.id} value={plan.id} label={plan.name} className="py-2.5">
            <span className="flex items-center gap-3">
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="truncate font-medium text-[var(--foreground)]">{plan.name}</span>
                  {plan.featured && <Badge tone="info">Featured</Badge>}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-xs text-[var(--foreground-muted)]">
                  <Badge tone="neutral">{titleCase(plan.billing_type)}</Badge>
                  {plan.public_description && <span className="truncate">{plan.public_description}</span>}
                </span>
              </span>
              <span className="shrink-0 font-bold tabular-nums text-[var(--foreground)]">
                {money(plan.price, plan.currency)}
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/* ─── Success Panel ─── */

function SuccessPanel({
  result,
  member,
  plan,
  method,
  onDismiss,
}: {
  result: CashPaymentOut;
  member: CashMemberItem | null;
  plan: PlanOut | null;
  method: string;
  onDismiss: () => void;
}) {
  return (
    <div className="animate-fade-in">
      <div className="rounded-2xl border border-[var(--success-border)] bg-[var(--success-bg)] p-5 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--success)]/10">
          <svg className="h-6 w-6 text-[var(--success)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-lg font-semibold text-[var(--foreground)]">Payment recorded</p>
        <p className="mt-1 text-sm text-[var(--foreground-muted)]">
          The receipt has been emailed to the member.
        </p>

        <p className="mt-4 font-heading text-3xl tracking-tight tabular-nums text-[var(--foreground)]">
          {money(result.amount, plan?.currency)}
        </p>

        <dl className="mt-5 space-y-2.5 border-t border-[var(--success-border)] pt-4 text-left text-sm">
          {member && (
            <ReceiptRow
              label="Member"
              value={
                <span className="flex items-center justify-end gap-2 min-w-0">
                  <Avatar name={member.full_name || member.email} size="sm" />
                  <span className="truncate">{member.full_name || member.email}</span>
                </span>
              }
            />
          )}
          {plan && <ReceiptRow label="Plan" value={plan.name} />}
          <ReceiptRow label="Method" value={METHOD_LABELS[method] ?? titleCase(method)} />
          <ReceiptRow
            label="Membership"
            value={<Badge tone="success">{titleCase(result.member_status)}</Badge>}
          />
          <ReceiptRow label="Receipt no." value={<span className="font-mono text-xs">{result.payment_id.slice(0, 12).toUpperCase()}</span>} />
        </dl>
      </div>

      <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={onDismiss}
          className="text-sm font-medium text-[var(--foreground-muted)] transition-colors hover:text-[var(--foreground)]"
        >
          Record another payment
        </button>
        {result.receipt_pdf_url && (
          <a
            href={`/api/download${result.receipt_pdf_url}`}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-brand-foreground shadow-sm transition-colors hover:bg-brand/90"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Download receipt
          </a>
        )}
      </div>
    </div>
  );
}

function ReceiptRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="shrink-0 text-[var(--foreground-muted)]">{label}</dt>
      <dd className="min-w-0 truncate text-right font-medium text-[var(--foreground)]">{value}</dd>
    </div>
  );
}

/* ─── LogPayment ─── */

function LogPayment({ onSaved }: { onSaved: () => void }) {
  const currentUser = useCurrentUser();
  const [plans, setPlans] = useState<PlanOut[] | null>(null);
  const [selected, setSelected] = useState<CashMemberItem | null>(null);
  const [memberId, setMemberId] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CashMemberItem[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [planId, setPlanId] = useState("");
  const [amount, setAmount] = useState("");
  const [promoCode, setPromoCode] = useState("");
  const [quote, setQuote] = useState<{ plan_price: number; joining_fee: number; discount_amount: number; tax_amount: number; total: number; currency: string } | null>(null);
  const [quoteError, setQuoteError] = useState("");
  const [method, setMethod] = useState("cash");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [queuedMessage, setQueuedMessage] = useState("");
  const [result, setResult] = useState<CashPaymentOut | null>(null);
  // The form resets on success, so keep what was paid for alongside the result.
  const [receipt, setReceipt] = useState<{ member: CashMemberItem | null; plan: PlanOut | null; method: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const selectedPlan = plans?.find((p) => p.id === planId) ?? null;

  useEffect(() => {
    if (!memberId || !planId) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const result = await api.post<typeof quote>("/cash/quote", { member_id: memberId, plan_id: planId, promo_code: promoCode.trim() || null });
        if (!cancelled) { setQuote(result); setAmount(String(result?.total ?? "")); setQuoteError(""); }
      } catch (e) {
        if (!cancelled) { setQuoteError((e as ApiError).message); setAmount(""); }
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [memberId, planId, promoCode]);

  useEffect(() => {
    async function load() {
      try {
        setPlans(await api.get<PlanOut[]>("/plans"));
      } catch (e) {
        setError((e as ApiError).message);
        setPlans([]);
      }
    }
    void load();
  }, []);

  // Debounced server-side member search (front-desk safe).
  useEffect(() => {
    const trimmed = query.trim();
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (!trimmed || cancelled) return;
      setSearchLoading(true);
      try {
        const rows = await api.get<CashMemberItem[]>(`/cash/members?q=${encodeURIComponent(trimmed)}`);
        if (!cancelled) { setResults(rows); setSearchError(""); }
      } catch (e) {
        if (!cancelled) setSearchError((e as ApiError).message);
      } finally {
        if (!cancelled) setSearchLoading(false);
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query]);

  function selectPlan(id: string) {
    setQuote(null);
    setAmount("");
    setPlanId(id);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const amt = Number(amount);
    if (!quote || !Number.isFinite(amt) || amt < 0) { setError("Wait for a valid payment quote."); return; }

    setError("");
    setResult(null);
    setLoading(true);
    const idempotencyKey = crypto.randomUUID();
    try {
      const payload = {
        member_id: memberId, plan_id: planId, amount: amt, method, note: note.trim() || null,
        promo_code: promoCode.trim() || null,
      };
      const out = await api.post<CashPaymentOut>("/cash/log", payload, { "Idempotency-Key": idempotencyKey });
      setResult(out);
      onSaved();
      setReceipt({ member: selected, plan: selectedPlan, method });
      setSelected(null); setMemberId(""); setQuery(""); setResults([]);
      setPlanId(""); setAmount(""); setNote(""); setPromoCode("");
    } catch (e) {
      const networkOrServerFailure = !(e instanceof ApiError) || e.status >= 500;
      if (networkOrServerFailure && currentUser?.org_id) {
        try {
          await enqueueOfflineMutation({
            organizationId: currentUser.org_id,
            path: "/cash/log",
            body: {
              member_id: memberId, plan_id: planId, amount: amt, method, note: note.trim() || null,
              promo_code: promoCode.trim() || null,
            },
            // Same key as the attempted request: a response lost after commit
            // replays the original result instead of recording a second payment.
            idempotencyKey,
          });
          setQueuedMessage("Connection failed. The payment is saved on this device and is not recorded yet. It will sync when the connection returns; check the payment history before retrying.");
          setSelected(null); setMemberId(""); setQuery(""); setResults([]);
          setPlanId(""); setAmount(""); setNote(""); setPromoCode(""); setQuote(null);
        } catch {
          setError("Connection failed and this payment could not be saved for sync. Keep the payment details and check the ledger before trying again.");
        }
      } else {
        setError((e as ApiError).message);
      }
    } finally {
      setLoading(false);
    }
  }

  const methods = ["cash", "bank_transfer", "mobile_wallet"];

  return (
    <div className="overflow-hidden">

      {plans === null ? (
        <Spinner label="Loading plans…" />
      ) : result ? (
        <div className="p-5 sm:p-6">
          <SuccessPanel
            result={result}
            member={receipt?.member ?? null}
            plan={receipt?.plan ?? null}
            method={receipt?.method ?? "cash"}
            onDismiss={() => { setResult(null); setReceipt(null); }}
          />
        </div>
      ) : (
        <form onSubmit={submit} className="grid min-w-0 gap-6 overflow-x-hidden p-5 sm:p-6">
          {error && <Alert onDismiss={() => setError("")}>{error}</Alert>}
          {queuedMessage && <Alert tone="warning" onDismiss={() => setQueuedMessage("")}>{queuedMessage}</Alert>}

          {/* Step 1: Find member */}
          <div>
            <MemberCombobox
              members={results}
              selected={selected}
              loading={searchLoading}
              query={query}
              onQueryChange={setQuery}
              error={searchError}
              onChange={(m) => { setSelected(m); setMemberId(m.member_id); setQuote(null); setAmount(""); }}
              onClear={() => { setSelected(null); setMemberId(""); setQuery(""); setResults([]); setQuote(null); setAmount(""); }}
            />
          </div>

          {/* Step 2: Pick plan */}
          <div>
            <p className="mb-2 text-[10px] font-semibold text-muted-foreground">Membership plan</p>
            {plans.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--background)] p-4 text-center">
                <p className="text-sm font-medium text-[var(--foreground)]">No membership plans yet</p>
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                  A payment has to be applied to a plan. Create one before logging cash.
                </p>
                <Link
                  href="/app/plans"
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--primary)] hover:underline"
                >
                  Create a plan
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                  </svg>
                </Link>
              </div>
            ) : (
              <PlanSelect plans={plans} value={planId} onChange={selectPlan} />
            )}
          </div>

          {/* Step 3: Server-calculated amount + Method */}
          <Input label="Promo code (optional)" value={promoCode} onChange={(e) => { setPromoCode(e.target.value.toUpperCase()); setQuote(null); setAmount(""); }} placeholder="WELCOME10" />
          {quoteError && <Alert onDismiss={() => setQuoteError("")}>{quoteError}</Alert>}
          {quote && <div className="grid gap-1 border border-[var(--border)] p-3 text-xs text-muted-foreground">
            <div>Plan price: {money(quote.plan_price, quote.currency)}</div>
            {quote.joining_fee > 0 && <div>Joining fee: {money(quote.joining_fee, quote.currency)}</div>}
            {quote.discount_amount > 0 && <div>Promo discount: −{money(quote.discount_amount, quote.currency)}</div>}
            {quote.tax_amount > 0 && <div>Tax: {money(quote.tax_amount, quote.currency)}</div>}
            <strong className="text-foreground">Due now: {money(quote.total, quote.currency)}</strong>
          </div>}
          <div className="grid min-w-0 gap-5">
            <Input
              label="Amount due"
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              required
              value={amount}
              readOnly
              placeholder="0.00"
              hint="Calculated from the plan, first-time joining fee, promotion, and tax."
              className="tabular-nums"
            />
            <div className="min-w-0">
              <p className="mb-2 text-[10px] font-semibold text-muted-foreground">Method</p>
              <div className="grid grid-cols-3 gap-2">
                {methods.map((m) => (
                  <MethodCard key={m} value={m} selected={method === m} onSelect={() => setMethod(m)} />
                ))}
              </div>
            </div>
          </div>

          {/* Step 4: Note */}
          <Input
            label="Internal note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Reference number or handover detail"
            hint="Visible to your team, not the member."
          />

          {/* Submit */}
          <div className="flex flex-col-reverse gap-3 border-t border-[var(--border)] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex-1 text-xs leading-5 text-[var(--foreground-muted)]">
              The member is activated immediately. Confirm the amount before saving.
            </p>
            <Button
              type="submit"
              loading={loading}
              disabled={!memberId || !planId || !quote}
              className="w-full shrink-0 whitespace-nowrap px-8 sm:w-auto"
            >
              <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Record payment
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

/* ─── Reconcile ─── */

function Reconcile() {
  const [businessDate, setBusinessDate] = useState(localDate);
  const [counted, setCounted] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ReconciliationOut | null>(null);
  const [loading, setLoading] = useState(false);
  const hasDiscrepancy = result ? Math.abs(result.discrepancy) > 0.009 : false;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const countedTotal = Number(counted);
    if (!Number.isFinite(countedTotal) || countedTotal < 0) {
      setError("Enter the cash total counted in the drawer.");
      return;
    }

    setError("");
    setResult(null);
    setLoading(true);
    try {
      const output = await api.post<ReconciliationOut>("/cash/reconcile", {
        business_date: businessDate,
        counted_total: countedTotal,
        notes: notes.trim() || null,
      });
      setResult(output);
    } catch (caught) {
      setError((caught as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="overflow-hidden">
      <form onSubmit={submit} className="grid gap-5 p-5 sm:p-6">
        {error && <Alert onDismiss={() => setError("")}>{error}</Alert>}
        <div className="rounded-xl border border-[var(--warning-border)] bg-[var(--warning-bg)] p-3.5 text-sm text-[var(--warning)]">
          <p className="font-semibold">Count physical cash first</p>
          <p className="mt-1 text-xs leading-5 text-[var(--warning)]">We compare your count with cash payments recorded for this date and preserve any difference in the audit trail.</p>
        </div>
        <Input label="Business date" type="date" required value={businessDate} onChange={(e) => setBusinessDate(e.target.value)} />
        <Input label="Cash counted" type="number" min="0" step="0.01" inputMode="decimal" required value={counted} onChange={(e) => setCounted(e.target.value)} placeholder="0.00" hint="Enter the actual amount in the cash drawer." />
        <Input label="Reconciliation notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional handover or discrepancy context" />
        <Button type="submit" loading={loading} className="w-full">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
          </svg>
          Save reconciliation
        </Button>

        {result && (
          <section
            className={`animate-fade-in rounded-xl border p-4 ${hasDiscrepancy ? "border-[var(--danger-border)] bg-[var(--danger-bg)]" : "border-[var(--success-border)] bg-[var(--success-bg)]"}`}
            aria-live="polite"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className={`font-semibold ${hasDiscrepancy ? "text-[var(--danger)]" : "text-[var(--success)]"}`}>
                  {hasDiscrepancy ? "Discrepancy recorded" : "Drawer balanced"}
                </p>
                <p className={`mt-0.5 text-xs ${hasDiscrepancy ? "text-[var(--danger)]" : "text-[var(--success)]"}`}>
                  Business date: {result.business_date}
                </p>
              </div>
              <Badge tone={hasDiscrepancy ? "danger" : "success"}>
                {hasDiscrepancy ? "Review needed" : "Matched"}
              </Badge>
            </div>
            <dl className="mt-4 space-y-2.5 border-y border-current/10 py-3 text-sm">
              <AmountRow label="Recorded cash" value={money(result.system_total)} />
              <AmountRow label="Cash counted" value={money(result.counted_total)} />
              <AmountRow label="Difference" value={money(result.discrepancy)} emphasis />
            </dl>
            {result.alert_triggered && (
              <p className="mt-3 text-xs font-medium text-[var(--danger)]">
                Owner alerted: this is the third discrepancy recorded within 30 days.
              </p>
            )}
          </section>
        )}
      </form>
    </div>
  );
}

/* ─── Small helpers ─── */

function AmountRow({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className={emphasis ? "font-semibold text-[var(--foreground)]" : "text-[var(--foreground-muted)]"}>{label}</dt>
      <dd className={`tabular-nums ${emphasis ? "font-bold text-[var(--foreground)]" : "font-medium"}`}>{value}</dd>
    </div>
  );
}
