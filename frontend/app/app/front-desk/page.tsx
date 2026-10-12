"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { ListToolbar } from "@/components/ListToolbar";
import { TABLE, THEAD_ROW, TH, TR, TD, CELL, CELL_FIRST, CELL_LAST } from "@/components/Table";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Input,
  Spinner,
} from "@/components/ui";
import { useRealtimeEvent } from "@/components/Realtime";
import { useModuleGate } from "@/hooks/useModuleGate";
import { api, ApiError } from "@/lib/api";
import { money, titleCase } from "@/lib/format";
import type { AttendanceMember, FrontDeskSummary, LockerOut, VisitorOut } from "@/lib/types";

/* ─── Front desk: walk-ins, day passes, guest log & lockers (#22) ───
   The desk's second surface after check-in: log a non-member (day pass takes
   payment into the ledger), check them out, and run the locker register. */

const KINDS = ["walk_in", "day_pass", "guest", "trial", "other"] as const;
const KIND_TONE: Record<string, "info" | "success" | "warning" | "neutral"> = {
  day_pass: "success",
  guest: "info",
  trial: "warning",
  walk_in: "neutral",
  other: "neutral",
};

function clock(iso: string): string {
  return new Date(iso + "Z").toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

const selectCls =
  "h-9 w-full cursor-pointer rounded-md border border-foreground/20 bg-card px-2.5 text-[13px] text-foreground focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20";

export default function FrontDeskPage() {
  const { ready } = useModuleGate("visitors");

  const [summary, setSummary] = useState<FrontDeskSummary | null>(null);
  const [visitors, setVisitors] = useState<VisitorOut[] | null>(null);
  const [lockers, setLockers] = useState<LockerOut[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [view, setView] = useState<"visitors" | "lockers">("visitors");
  const [search, setSearch] = useState("");
  const [showVisitorForm, setShowVisitorForm] = useState(false);

  // Add-visitor form
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [kind, setKind] = useState<(typeof KINDS)[number]>("walk_in");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [hostQuery, setHostQuery] = useState("");
  const [hostResults, setHostResults] = useState<AttendanceMember[]>([]);
  const [host, setHost] = useState<AttendanceMember | null>(null);

  // Add-locker form
  const [newLocker, setNewLocker] = useState("");
  // Per-locker holder input
  const [holders, setHolders] = useState<Record<string, string>>({});

  const loadVisitors = useCallback(async () => {
    try {
      setVisitors(await api.get<VisitorOut[]>("/front-desk/visitors"));
    } catch (e) {
      setError((e as ApiError).message);
      setVisitors([]);
    }
  }, []);
  const loadLockers = useCallback(async () => {
    try {
      setLockers(await api.get<LockerOut[]>("/front-desk/lockers"));
    } catch {
      setLockers([]);
    }
  }, []);
  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.get<FrontDeskSummary>("/front-desk/summary"));
    } catch {
      /* secondary */
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadVisitors();
      void loadLockers();
      void loadSummary();
    });
  }, [loadVisitors, loadLockers, loadSummary]);

  useRealtimeEvent(["visitor.changed"], () => {
    void loadVisitors();
    void loadLockers();
    void loadSummary();
  });

  // Debounced host search (uses the check-in member search; front desk can read it).
  useEffect(() => {
    const term = hostQuery.trim();
    if (!term) return;
    let cancelled = false;
    const id = setTimeout(async () => {
      try {
        const rows = await api.get<AttendanceMember[]>(`/attendance/members?q=${encodeURIComponent(term)}`);
        if (!cancelled) setHostResults(rows);
      } catch {
        if (!cancelled) setHostResults([]);
      }
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [hostQuery]);

  function onHostQueryChange(value: string) {
    setHost(null);
    setHostQuery(value);
    if (!value.trim()) setHostResults([]);
  }

  async function logVisitor(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy("log");
    setError("");
    try {
      await api.post(
        "/front-desk/visitors",
        {
          name: name.trim(),
          phone: phone.trim() || null,
          kind,
          amount: kind === "day_pass" ? parseFloat(amount) || 0 : 0,
          method: kind === "day_pass" && parseFloat(amount) > 0 ? method : null,
          host_member_id: kind === "guest" && host ? host.member_id : null,
        },
        { "Idempotency-Key": crypto.randomUUID() },
      );
      setName("");
      setPhone("");
      setAmount("");
      setHost(null);
      setHostQuery("");
      setShowVisitorForm(false);
      void loadVisitors();
      void loadSummary();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  async function checkOut(id: string) {
    setBusy(id);
    try {
      await api.post(`/front-desk/visitors/${id}/check-out`);
      void loadVisitors();
      void loadSummary();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  async function addLocker(e: React.FormEvent) {
    e.preventDefault();
    if (!newLocker.trim()) return;
    setBusy("locker");
    setError("");
    try {
      await api.post("/front-desk/lockers", { number: newLocker.trim() });
      setNewLocker("");
      void loadLockers();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  async function assignLocker(id: string) {
    const holder = (holders[id] ?? "").trim();
    if (!holder) return;
    setBusy(id);
    setError("");
    try {
      await api.post(`/front-desk/lockers/${id}/assign`, { holder_label: holder });
      setHolders((h) => ({ ...h, [id]: "" }));
      void loadLockers();
      void loadSummary();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  async function releaseLocker(id: string) {
    setBusy(id);
    try {
      await api.post(`/front-desk/lockers/${id}/release`);
      void loadLockers();
      void loadSummary();
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  }

  if (!ready) return <Spinner label="Loading front desk…" />;

  const showAmount = kind === "day_pass";
  const filteredVisitors = visitors?.filter((v) =>
    `${v.name} ${v.phone ?? ""} ${v.kind} ${v.host_name ?? ""}`.toLowerCase().includes(search.toLowerCase()),
  );
  const filteredLockers = lockers?.filter((l) =>
    `${l.number} ${l.holder_label ?? ""}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <>
      <PageHeader title="Walk-ins" subtitle="Log visitors, day passes and locker use."
        action={<Button onClick={() => setShowVisitorForm(true)}>+ Log visitor</Button>} />

      {error && (
        <div className="mb-4">
          <Alert onDismiss={() => setError("")}>{error}</Alert>
        </div>
      )}

      <Sheet open={showVisitorForm} onOpenChange={setShowVisitorForm}>
        <SheetContent><SheetHeader><SheetTitle>Log a visitor</SheetTitle><SheetDescription>Record a walk-in, guest or day pass.</SheetDescription></SheetHeader><SheetBody>
        {/* Log a visitor */}
        <div>
          <form onSubmit={logVisitor} className="space-y-3">
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" required />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Optional" />
              <label className="block">
                <span className="mb-1.5 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Type</span>
                <select className={selectCls} value={kind} onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}>
                  {KINDS.map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}
                </select>
              </label>
            </div>

            {showAmount && (
              <div className="grid grid-cols-2 gap-3">
                <Input label="Amount" type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
                <label className="block">
                  <span className="mb-1.5 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Method</span>
                  <select className={selectCls} value={method} onChange={(e) => setMethod(e.target.value)}>
                    <option value="cash">Cash</option>
                    <option value="card">Card</option>
                    <option value="bank_transfer">Bank transfer</option>
                    <option value="mobile_wallet">Mobile wallet</option>
                  </select>
                </label>
              </div>
            )}

            {kind === "guest" && (
              <div>
                <Input
                  label="Host member (optional)"
                  value={host ? (host.member_name || host.member_email) : hostQuery}
                  onChange={(e) => onHostQueryChange(e.target.value)}
                  placeholder="Search the member hosting them…"
                />
                {!host && hostResults.length > 0 && (
                  <ul className="mt-1 overflow-hidden rounded-md border border-foreground/10">
                    {hostResults.slice(0, 5).map((m) => (
                      <li key={m.member_id}>
                        <button
                          type="button"
                          onClick={() => { setHost(m); setHostResults([]); }}
                          className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-left text-[12px] hover:bg-foreground/[0.04]"
                        >
                          {m.member_name || m.member_email}
                          <span className="truncate text-[11px] text-muted-foreground">{m.member_email}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <Button type="submit" loading={busy === "log"} disabled={!name.trim()}>Log visitor</Button>
          </form>
        </div>
        </SheetBody></SheetContent>
      </Sheet>

      <ListToolbar tabs={[
        { value: "visitors", label: "Visitors", count: visitors?.length ?? summary?.visitors_today },
        { value: "lockers", label: "Lockers", count: lockers?.length ?? summary?.lockers_total },
      ]} value={view} onChange={setView} search={search} onSearch={setSearch} searchPlaceholder={view === "visitors" ? "Search visitors…" : "Search lockers…"} />

      <div className="mt-3">

        {view === "visitors" ? (
          visitors === null ? <Spinner label="Loading visitors…" /> :
          filteredVisitors?.length === 0 ?
            <EmptyState title={search ? "No matching visitors" : "No visitors yet"} hint={search ? "Try another name or type." : "Log a walk-in or day pass to see them here."} /> :
            <div className="overflow-x-auto"><table className={`${TABLE} min-w-[720px]`}>
              <thead><tr className={THEAD_ROW}>
                <th className={`${TH} ${CELL_FIRST}`}>Name</th><th className={`${TH} ${CELL}`}>Type</th><th className={`${TH} ${CELL}`}>Arrival</th><th className={`${TH} ${CELL}`}>Amount</th><th className={`${TH} ${CELL}`}>Status</th><th className={`${TH} ${CELL_LAST}`}>Action</th>
              </tr></thead>
              <tbody>{filteredVisitors?.map((v) => <tr key={v.id} className={TR}>
                <td className={`${TD} ${CELL_FIRST} py-3`}><p className="text-[13px] font-medium">{v.name}</p><p className="text-[11px] text-muted-foreground">{v.host_name ? `Guest of ${v.host_name}` : v.phone || ""}</p></td>
                <td className={`${TD} ${CELL} py-3`}><Badge tone={KIND_TONE[v.kind] ?? "neutral"} size="sm">{titleCase(v.kind)}</Badge></td>
                <td className={`${TD} ${CELL} py-3 text-[12px]`}>{clock(v.checked_in_at)}</td>
                <td className={`${TD} ${CELL} py-3 text-[12px] tabular-nums`}>{v.paid && v.amount > 0 ? money(v.amount) : "—"}</td>
                <td className={`${TD} ${CELL} py-3`}><Badge tone={v.checked_out_at ? "neutral" : "success"} size="sm">{v.checked_out_at ? "Out" : "Inside"}</Badge></td>
                <td className={`${TD} ${CELL_LAST} py-3`}>{!v.checked_out_at && <Button variant="secondary" disabled={busy === v.id} onClick={() => checkOut(v.id)}>Check out</Button>}</td>
              </tr>)}</tbody>
            </table></div>
        ) : (
          <>
            <form onSubmit={addLocker} className="mb-4 flex items-end gap-2">
              <Input label="Add locker" value={newLocker} onChange={(e) => setNewLocker(e.target.value)} placeholder="Number" className="w-32" />
              <Button type="submit" variant="secondary" loading={busy === "locker"} disabled={!newLocker.trim()}>Add locker</Button>
            </form>
            {lockers === null ? <Spinner label="Loading lockers…" /> : filteredLockers?.length === 0 ?
              <EmptyState title={search ? "No matching lockers" : "No lockers registered"} hint="Add a locker to start the register." /> :
              <div className="overflow-x-auto"><table className={`${TABLE} min-w-[620px]`}>
                <thead><tr className={THEAD_ROW}><th className={`${TH} ${CELL_FIRST}`}>Locker</th><th className={`${TH} ${CELL}`}>Holder</th><th className={`${TH} ${CELL}`}>Status</th><th className={`${TH} ${CELL_LAST}`}>Action</th></tr></thead>
                <tbody>{filteredLockers?.map((l) => <tr key={l.id} className={TR}>
                  <td className={`${TD} ${CELL_FIRST} py-3 text-[13px] font-medium`}>{l.number}</td>
                  <td className={`${TD} ${CELL} py-3`}>{l.status === "occupied" ? l.holder_label : <input value={holders[l.id] ?? ""} onChange={(e) => setHolders((h) => ({ ...h, [l.id]: e.target.value }))} placeholder="Holder name" className="h-8 w-full max-w-56 rounded-md border border-foreground/15 bg-card px-2 text-[12px]" />}</td>
                  <td className={`${TD} ${CELL} py-3`}><Badge tone={l.status === "occupied" ? "warning" : "neutral"} size="sm">{titleCase(l.status)}</Badge></td>
                  <td className={`${TD} ${CELL_LAST} py-3`}>{l.status === "occupied" ? <Button variant="secondary" disabled={busy === l.id} onClick={() => releaseLocker(l.id)}>Release</Button> : <Button variant="secondary" disabled={busy === l.id || !(holders[l.id] ?? "").trim()} onClick={() => assignLocker(l.id)}>Assign</Button>}</td>
                </tr>)}</tbody>
              </table></div>}
          </>
        )}
      </div>
    </>
  );
}
