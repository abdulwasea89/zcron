"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Button, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import type { ClientAssignment, TrainerSessionLog } from "@/lib/types";

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export default function TrainingPage() {
  const currentUser = useCurrentUser();
  const [clients, setClients] = useState<ClientAssignment[] | null>(null);
  const [logs, setLogs] = useState<TrainerSessionLog[] | null>(null);
  const [clientId, setClientId] = useState("");
  const [performedAt, setPerformedAt] = useState(localDateTime);
  const [duration, setDuration] = useState("45");
  const [focus, setFocus] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const [assigned, history] = await Promise.all([
        api.get<ClientAssignment[]>("/members/assigned-to-me"),
        api.get<TrainerSessionLog[]>("/staff/trainer-sessions?limit=100"),
      ]);
      setClients(assigned.filter((client) => client.member_status === "active"));
      setLogs(history);
    } catch (e) {
      setError((e as ApiError).message || "Could not load training records.");
      setClients([]);
      setLogs([]);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post("/staff/trainer-sessions", {
        client_member_id: clientId,
        performed_at: new Date(performedAt).toISOString(),
        duration_minutes: Number(duration),
        focus,
        notes,
      });
      setFocus("");
      setNotes("");
      await load();
    } catch (e) {
      setError((e as ApiError).message || "Could not save this training session.");
    } finally {
      setSaving(false);
    }
  }

  if (currentUser && currentUser.role !== "trainer") {
    return <Alert>Training logs are available to trainers.</Alert>;
  }

  return <>
    <PageHeader title="Training log" subtitle="Record completed sessions for your assigned clients." />
    {error && <div className="mb-4"><Alert>{error}</Alert></div>}
    <div className="grid gap-6 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)]">
      <section className="border border-border bg-background p-5">
        <h2 className="text-sm font-semibold">Log a session</h2>
        <p className="mt-1 text-xs text-muted-foreground">Only you and authorized gym managers can view these notes.</p>
        {clients === null ? <div className="mt-5"><Spinner label="Loading assigned clients…" /></div> : clients.length === 0 ? (
          <p className="mt-5 text-sm text-muted-foreground">No active clients are assigned to you yet.</p>
        ) : <form onSubmit={submit} className="mt-5 grid gap-4">
          <label className="grid gap-1.5 text-xs text-muted-foreground">Client
            <select required value={clientId} onChange={(event) => setClientId(event.target.value)} className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground">
              <option value="">Choose an assigned client…</option>
              {clients.map((client) => <option key={client.member_id} value={client.member_id}>{client.member_name || client.member_email}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="grid gap-1.5 text-xs text-muted-foreground">Session time
              <input required type="datetime-local" max={localDateTime()} value={performedAt} onChange={(event) => setPerformedAt(event.target.value)} className="h-9 min-w-0 rounded-md border border-border bg-background px-2 text-sm text-foreground" />
            </label>
            <label className="grid gap-1.5 text-xs text-muted-foreground">Minutes
              <input required type="number" min="1" max="300" value={duration} onChange={(event) => setDuration(event.target.value)} className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground" />
            </label>
          </div>
          <label className="grid gap-1.5 text-xs text-muted-foreground">Workout focus
            <input required minLength={2} maxLength={160} value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="Strength, mobility, conditioning…" className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground" />
          </label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">Session notes
            <textarea maxLength={4000} rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Exercises, progress, next session…" className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground" />
          </label>
          <Button type="submit" disabled={!clientId || saving} loading={saving}>Save session</Button>
        </form>}
      </section>

      <section className="border border-border bg-background">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div><h2 className="text-sm font-semibold">Recent sessions</h2><p className="mt-1 text-xs text-muted-foreground">Your latest 100 training records.</p></div>
          <span className="text-xs tabular-nums text-muted-foreground">{logs?.length ?? 0}</span>
        </div>
        {logs === null ? <div className="p-5"><Spinner label="Loading sessions…" /></div> : logs.length === 0 ? (
          <p className="p-5 text-sm text-muted-foreground">Your completed sessions will appear here.</p>
        ) : <ul className="m-0 list-none divide-y divide-border p-0">
          {logs.map((log) => <li key={log.id} className="px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <h3 className="text-sm font-medium">{log.client_name} <span className="font-normal text-muted-foreground">· {log.focus}</span></h3>
              <time className="text-xs text-muted-foreground">{new Date(log.performed_at).toLocaleString()}</time>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{log.duration_minutes} minutes</p>
            {log.notes && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground/80">{log.notes}</p>}
          </li>)}
        </ul>}
      </section>
    </div>
  </>;
}
