"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

type Match = { trainer_member_id: string; name: string; assigned_clients: number; already_assigned: boolean };
type Member = { member_id: string; full_name: string | null; email: string };
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export function TrainerMatchingPanel({ members }: { members: Member[] }) {
  const [memberId, setMemberId] = useState("");
  const [weekday, setWeekday] = useState("0");
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("10:00");
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const assignment = useRef<{ target: string; key: string } | null>(null);

  async function find(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMatches(null);
    try {
      const query = new URLSearchParams({ member_id: memberId, weekday, start_time: start, end_time: end });
      setMatches(await api.get<Match[]>(`/staff/trainer-matches?${query}`));
    } catch (cause) { setError((cause as ApiError).message || "Could not find matching trainers."); }
    finally { setBusy(false); }
  }

  async function assign(match: Match) {
    setBusy(true); setError("");
    const target = `${memberId}:${match.trainer_member_id}`;
    if (assignment.current?.target !== target) assignment.current = { target, key: crypto.randomUUID() };
    try {
      await api.post(`/members/${memberId}/trainers`, { trainer_member_id: match.trainer_member_id }, { "Idempotency-Key": assignment.current.key });
      assignment.current = null;
      setMatches((rows) => rows?.map((row) => row.trainer_member_id === match.trainer_member_id ? { ...row, already_assigned: true, assigned_clients: row.assigned_clients + 1 } : row) ?? null);
    } catch (cause) { setError((cause as ApiError).message || "Could not assign this trainer."); }
    finally { setBusy(false); }
  }

  return <section className="mb-6 border border-border bg-background p-5">
    <h2 className="text-sm font-semibold">Match a member with a trainer</h2>
    <p className="mt-1 text-xs leading-5 text-muted-foreground">Find weekly availability in gym local time, ranked by fewer assigned clients. Assignment does not reserve an appointment. <Link href="/app/staff" className="underline underline-offset-4">Manage availability</Link></p>
    <form onSubmit={find} className="mt-4 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <label className="grid gap-1.5 text-xs text-muted-foreground">Member<select required disabled={busy} value={memberId} onChange={(event) => { setMemberId(event.target.value); setMatches(null); }} className="h-9 min-w-0 border border-border bg-background px-2 text-sm text-foreground"><option value="">Choose a member…</option>{members.map((member) => <option key={member.member_id} value={member.member_id}>{member.full_name || member.email}</option>)}</select></label>
      <label className="grid gap-1.5 text-xs text-muted-foreground">Weekday<select disabled={busy} value={weekday} onChange={(event) => { setWeekday(event.target.value); setMatches(null); }} className="h-9 border border-border bg-background px-2 text-sm text-foreground">{WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
      <Input label="From" type="time" required disabled={busy} value={start} onChange={(event) => { setStart(event.target.value); setMatches(null); }} />
      <Input label="Until" type="time" required disabled={busy} value={end} onChange={(event) => { setEnd(event.target.value); setMatches(null); }} />
      <Button type="submit" disabled={busy || !memberId} loading={busy}>Find trainers</Button>
    </form>
    {error && <div className="mt-4"><Alert>{error}</Alert></div>}
    {matches !== null && (matches.length ? <ul className="mt-4 divide-y divide-border border-t border-border">{matches.map((match) => <li key={match.trainer_member_id} className="flex items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{match.name}</p><p className="mt-1 text-xs text-muted-foreground">{match.assigned_clients} assigned clients · covers the requested weekly window</p></div><Button variant="secondary" disabled={busy || match.already_assigned} onClick={() => void assign(match)}>{match.already_assigned ? "Assigned" : "Assign trainer"}</Button></li>)}</ul> : <p className="mt-4 text-sm text-muted-foreground">No trainers have a saved availability window covering this time.</p>)}
  </section>;
}
