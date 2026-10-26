"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Alert, Badge, Button, Input } from "@/components/ui";
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useRealtimeEvent } from "@/components/Realtime";
import { api, ApiError } from "@/lib/api";
import { titleCase } from "@/lib/format";

type Case = { id: string; member_id: string; member_name: string; next_action: string; assignee_member_id: string | null; due_at: string | null; done: boolean; outcome: string | null };
type Person = { member_id: string; full_name?: string | null; email?: string; name?: string; role: string };
const OUTCOMES = ["payment_received", "returned", "plan_changed", "paused", "declined", "unreachable", "completed", "cancelled"];

function localDue(value: string | null) {
  if (!value) return "";
  const date = new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

export function RetentionCasesPanel({ focusMemberId = "" }: { focusMemberId?: string }) {
  const [rows, setRows] = useState<Case[]>([]);
  const [members, setMembers] = useState<Person[]>([]);
  const [staff, setStaff] = useState<Person[]>([]);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [open, setOpen] = useState(Boolean(focusMemberId));
  const [memberId, setMemberId] = useState(focusMemberId);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [focusLoaded, setFocusLoaded] = useState(!focusMemberId);
  const requestKey = useRef<{ body: string; key: string } | null>(null);
  const [assignee, setAssignee] = useState("");
  const [action, setAction] = useState("Contact the member and agree on a next step.");
  const [due, setDue] = useState("");
  const [outcome, setOutcome] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get<Case[]>(`/retention/cases?include_closed=${includeClosed}`), [includeClosed]);
  useEffect(() => {
    let active = true;
    void Promise.all([load(), focusMemberId ? api.get<Case | null>(`/retention/cases/${focusMemberId}`) : Promise.resolve(null)])
      .then(([items, focused]) => {
        if (!active) return;
        setRows(items);
        if (focused) {
          setCaseId(focused.id); setMemberId(focused.member_id); setAssignee(focused.assignee_member_id ?? "");
          setAction(focused.next_action); setDue(localDue(focused.due_at));
        }
        setFocusLoaded(true);
      })
      .catch((cause) => { if (active) setError((cause as ApiError).message || "Could not load retention cases."); });
    return () => { active = false; };
  }, [load, focusMemberId]);
  useEffect(() => {
    Promise.all([api.get<Person[]>("/cash/members"), api.get<Person[]>("/staff/directory")])
      .then(([people, team]) => { setMembers(people.filter((person) => person.role === "member")); setStaff(team); })
      .catch((cause) => setError((cause as ApiError).message || "Could not load people."));
  }, []);
  useRealtimeEvent(["task.changed"], () => {
    void load().then(setRows).catch((cause) => setError((cause as ApiError).message || "Could not load retention cases."));
  });
  function edit(row?: Case) {
    setMemberId(row?.member_id ?? ""); setCaseId(row && !row.done ? row.id : null); setAssignee(row?.assignee_member_id ?? "");
    setAction(row?.next_action ?? "Contact the member and agree on a next step.");
    setDue(localDue(row?.due_at ?? null));
    setOutcome(""); setError(""); setOpen(true);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const payload = { case_id: caseId, next_action: action, assignee_member_id: assignee || null, due_at: due ? new Date(due).toISOString() : null, outcome: outcome || null };
      const body = JSON.stringify({ memberId, ...payload });
      if (requestKey.current?.body !== body) requestKey.current = { body, key: crypto.randomUUID() };
      await api.put(`/retention/cases/${memberId}`, payload, { "Idempotency-Key": requestKey.current.key });
      requestKey.current = null;
      setOpen(false); setRows(await load()); toast.success(outcome ? "Retention outcome recorded." : "Retention case saved to the task queue.");
    } catch (cause) { setError((cause as ApiError).message || "Could not save this case."); }
    finally { setBusy(false); }
  }
  return <section className="border border-border bg-card">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-4">
      <div><h2 className="text-sm font-semibold">Retention cases</h2><p className="mt-1 text-xs text-muted-foreground">One open case per member · assigned follow-ups appear in staff tasks · latest 500 records</p></div>
      <div className="flex items-center gap-3"><label className="text-xs"><input type="checkbox" checked={includeClosed} onChange={(event) => setIncludeClosed(event.target.checked)} /> Include closed</label><Button variant="secondary" onClick={() => edit()}>Open case</Button></div>
    </header>
    {error && <div className="p-4"><Alert>{error}</Alert></div>}
    {rows.length ? <ul className="divide-y divide-border">{rows.map((row) => <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
      <div className="min-w-0"><p className="text-sm font-medium">{row.member_name}</p><p className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">{row.next_action}</p><p className="mt-1 text-xs text-muted-foreground">{staff.find((person) => person.member_id === row.assignee_member_id)?.name ?? "Unassigned"}{row.due_at ? ` · Due ${new Date(/Z$|[+-]\d{2}:\d{2}$/.test(row.due_at) ? row.due_at : `${row.due_at}Z`).toLocaleString()}` : ""}</p></div>
      <div className="flex items-center gap-2"><Badge tone={row.done ? "neutral" : "warning"}>{row.done ? titleCase(row.outcome ?? "completed") : "Open"}</Badge><Button variant="secondary" onClick={() => edit(row)}>{row.done ? "Start another case" : "Manage"}</Button></div>
    </li>)}</ul> : <p className="p-5 text-sm text-muted-foreground">No cases in this view.</p>}
    <Sheet open={open} onOpenChange={setOpen}><SheetContent><SheetHeader><SheetTitle>Retention case</SheetTitle><SheetDescription>Assign the next action or close an existing case with an outcome.</SheetDescription></SheetHeader>
      <form onSubmit={save} className="flex min-h-0 flex-1 flex-col"><SheetBody className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <label className="block text-xs text-muted-foreground">Member<select required value={memberId} onChange={(event) => { setMemberId(event.target.value); setCaseId(null); }} className="mt-1.5 h-10 w-full border border-input bg-background px-2 text-sm text-foreground"><option value="">Choose member</option>{members.map((person) => <option key={person.member_id} value={person.member_id}>{person.full_name || person.email}</option>)}</select></label>
        <label className="block text-xs text-muted-foreground">Assigned staff<select value={assignee} onChange={(event) => setAssignee(event.target.value)} className="mt-1.5 h-10 w-full border border-input bg-background px-2 text-sm text-foreground"><option value="">Unassigned</option>{staff.map((person) => <option key={person.member_id} value={person.member_id}>{person.name}</option>)}</select></label>
        <label className="block text-xs text-muted-foreground">Next action / outcome notes<textarea required maxLength={1000} rows={4} value={action} onChange={(event) => setAction(event.target.value)} className="mt-1.5 w-full border border-input bg-background p-3 text-sm text-foreground" /></label>
        <Input label="Follow-up due (optional, defaults to tomorrow)" type="datetime-local" value={due} onChange={(event) => setDue(event.target.value)} />
        <label className="block text-xs text-muted-foreground">Outcome<select value={outcome} onChange={(event) => setOutcome(event.target.value)} className="mt-1.5 h-10 w-full border border-input bg-background px-2 text-sm text-foreground"><option value="">Keep case open</option>{OUTCOMES.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
        <p className="text-xs leading-5 text-muted-foreground">A recorded membership payment automatically closes the open case as “Payment received”. Other outcomes are recorded by staff. Closed cases remain in the history.</p>
      </SheetBody><SheetFooter><Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" disabled={busy || !memberId || !focusLoaded}>Save case</Button></SheetFooter></form>
    </SheetContent></Sheet>
  </section>;
}
