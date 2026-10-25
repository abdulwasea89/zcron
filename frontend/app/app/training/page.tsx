"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Button, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import type { ClientAssignment, TrainerSessionLog } from "@/lib/types";
import { toast } from "sonner";

type TrainerPackage = { id: string; member_id: string; member_name: string; trainer_member_id: string; trainer_name: string; name: string; total_sessions: number; used_sessions: number; remaining_sessions: number; expires_at: string | null; status: string };
type MemberOption = { member_id: string; full_name: string | null; email: string; member_status: string; role: string };
type TrainerOption = { member_id: string; name: string; role: string };

function localDateTime() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export default function TrainingPage() {
  const currentUser = useCurrentUser();
  const [clients, setClients] = useState<ClientAssignment[] | null>(null);
  const [logs, setLogs] = useState<TrainerSessionLog[] | null>(null);
  const [packages, setPackages] = useState<TrainerPackage[]>([]);
  const [members, setMembers] = useState<MemberOption[]>([]);
  const [trainers, setTrainers] = useState<TrainerOption[]>([]);
  const [packageMember, setPackageMember] = useState("");
  const [packageTrainer, setPackageTrainer] = useState("");
  const [packageName, setPackageName] = useState("Personal training");
  const [packageSessions, setPackageSessions] = useState("10");
  const [packageExpiry, setPackageExpiry] = useState("");
  const [clientId, setClientId] = useState("");
  const [performedAt, setPerformedAt] = useState(localDateTime);
  const [duration, setDuration] = useState("45");
  const [focus, setFocus] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [packageId, setPackageId] = useState("");
  const sessionRequest = useRef<{ body: string; key: string } | null>(null);
  const grantRequest = useRef<{ body: string; key: string } | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const [assigned, history, creditPackages] = await Promise.all([
        api.get<ClientAssignment[]>("/members/assigned-to-me"),
        api.get<TrainerSessionLog[]>("/staff/trainer-sessions?limit=100"),
        api.get<TrainerPackage[]>("/staff/trainer-packages"),
      ]);
      setClients(assigned.filter((client) => client.member_status === "active"));
      setLogs(history);
      setPackages(creditPackages);
    } catch (e) {
      setError((e as ApiError).message || "Could not load training records.");
      setClients([]);
      setLogs([]);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => {
    if (!currentUser || !["owner", "manager"].includes(currentUser.role)) return;
    queueMicrotask(() => {
      Promise.all([api.get<MemberOption[]>("/cash/members"), api.get<TrainerOption[]>("/staff/directory")])
        .then(([roster, team]) => {
          setMembers(roster.filter((member) => member.role === "member" && member.member_status === "active"));
          setTrainers(team.filter((person) => person.role === "trainer"));
        })
        .catch((e) => setError((e as ApiError).message || "Could not load package recipients."));
    });
  }, [currentUser]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        client_member_id: clientId,
        package_id: packageId || null,
        performed_at: new Date(performedAt).toISOString(),
        duration_minutes: Number(duration),
        focus,
        notes,
      };
      const body = JSON.stringify(payload);
      if (sessionRequest.current?.body !== body) sessionRequest.current = { body, key: crypto.randomUUID() };
      await api.post("/staff/trainer-sessions", payload, { "Idempotency-Key": sessionRequest.current.key });
      sessionRequest.current = null;
      setFocus("");
      setNotes("");
      setPackageId("");
      await load();
    } catch (e) {
      setError((e as ApiError).message || "Could not save this training session.");
    } finally {
      setSaving(false);
    }
  }

  async function grantPackage(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const payload = {
        member_id: packageMember, trainer_member_id: packageTrainer,
        name: packageName, total_sessions: Number(packageSessions),
        expires_at: packageExpiry ? new Date(packageExpiry).toISOString() : null,
      };
      const body = JSON.stringify(payload);
      if (grantRequest.current?.body !== body) grantRequest.current = { body, key: crypto.randomUUID() };
      await api.post("/staff/trainer-packages", payload, { "Idempotency-Key": grantRequest.current.key });
      grantRequest.current = null;
      await load();
      setPackageMember(""); setPackageTrainer(""); setPackageExpiry("");
    } catch (e) { setError((e as ApiError).message || "Could not grant training credits."); }
    finally { setSaving(false); }
  }

  async function cancelPackage(item: TrainerPackage) {
    if (!window.confirm(`Cancel the unused session credits in ${item.name} for ${item.member_name}? Existing training logs and payments will remain.`)) return;
    setSaving(true);
    try {
      await api.post(`/staff/trainer-packages/${item.id}/cancel`, {}, { "Idempotency-Key": crypto.randomUUID() });
      await load(); toast.success("Unused session credits cancelled.");
    } catch (e) { setError((e as ApiError).message || "Could not cancel this package."); }
    finally { setSaving(false); }
  }

  if (currentUser && !["trainer", "owner", "manager"].includes(currentUser.role)) {
    return <Alert>Training operations are available to gym owners, managers, and trainers.</Alert>;
  }

  return <>
    <PageHeader title="Trainer operations" subtitle="Manage personal-training credits and record completed sessions." />
    {error && <div className="mb-4"><Alert>{error}</Alert></div>}
    {currentUser && ["owner", "manager"].includes(currentUser.role) && <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)]">
      <section className="border border-border bg-background p-5">
        <h2 className="text-sm font-semibold">Grant session credits</h2>
        <p className="mt-1 text-xs text-muted-foreground">Grant a credit bundle and assign a trainer. Record any payment separately in Payments.</p>
        <form onSubmit={grantPackage} className="mt-5 grid gap-4">
          <label className="grid gap-1.5 text-xs text-muted-foreground">Member<select required value={packageMember} onChange={(event) => setPackageMember(event.target.value)} className="h-9 border border-border bg-background px-2 text-sm text-foreground"><option value="">Choose a member…</option>{members.map((member) => <option key={member.member_id} value={member.member_id}>{member.full_name || member.email}</option>)}</select></label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">Trainer<select required value={packageTrainer} onChange={(event) => setPackageTrainer(event.target.value)} className="h-9 border border-border bg-background px-2 text-sm text-foreground"><option value="">Choose a trainer…</option>{trainers.map((trainer) => <option key={trainer.member_id} value={trainer.member_id}>{trainer.name}</option>)}</select></label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">Package name<input required minLength={2} maxLength={100} value={packageName} onChange={(event) => setPackageName(event.target.value)} className="h-9 border border-border bg-background px-3 text-sm text-foreground" /></label>
          <div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-muted-foreground">Sessions<input required type="number" min="1" max="100" value={packageSessions} onChange={(event) => setPackageSessions(event.target.value)} className="h-9 border border-border bg-background px-3 text-sm text-foreground" /></label><label className="grid gap-1.5 text-xs text-muted-foreground">Expires (optional)<input type="datetime-local" value={packageExpiry} onChange={(event) => setPackageExpiry(event.target.value)} className="h-9 border border-border bg-background px-3 text-sm text-foreground" /></label></div>
          <Button type="submit" disabled={saving || !packageMember || !packageTrainer} loading={saving}>Grant credits</Button>
        </form>
      </section>
      <section className="border border-border bg-background">
        <div className="border-b border-border px-5 py-4"><h2 className="text-sm font-semibold">Session credit packages</h2><p className="mt-1 text-xs text-muted-foreground">Latest 500 credit bundles across assigned trainers.</p></div>
        {packages.length ? <ul className="divide-y divide-border">{packages.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"><div><p className="text-sm font-medium">{item.member_name} <span className="font-normal text-muted-foreground">· {item.name}</span></p><p className="mt-1 text-xs text-muted-foreground">{item.trainer_name} · {item.status}{item.expires_at ? ` · Expires ${new Date(/Z$|[+-]\d{2}:\d{2}$/.test(item.expires_at) ? item.expires_at : `${item.expires_at}Z`).toLocaleString()}` : ""}</p></div><div className="flex items-center gap-3"><span className="text-sm tabular-nums">{item.remaining_sessions} / {item.total_sessions} left</span>{item.status === "active" && <Button variant="secondary" disabled={saving} onClick={() => void cancelPackage(item)}>Cancel unused</Button>}</div></li>)}</ul> : <p className="p-5 text-sm text-muted-foreground">No packages granted yet.</p>}
      </section>
    </div>}
    <div className={currentUser?.role === "trainer" ? "grid gap-6 lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.2fr)]" : "grid gap-6"}>
      {currentUser?.role === "trainer" && <section className="border border-border bg-background p-5">
        <h2 className="text-sm font-semibold">Log a session</h2>
        <p className="mt-1 text-xs text-muted-foreground">Only you and authorized gym managers can view these notes.</p>
        {clients === null ? <div className="mt-5"><Spinner label="Loading assigned clients…" /></div> : clients.length === 0 ? (
          <p className="mt-5 text-sm text-muted-foreground">No active clients are assigned to you yet.</p>
        ) : <form onSubmit={submit} className="mt-5 grid gap-4">
          <label className="grid gap-1.5 text-xs text-muted-foreground">Client
            <select required value={clientId} onChange={(event) => { setClientId(event.target.value); setPackageId(""); }} className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground">
              <option value="">Choose an assigned client…</option>
              {clients.map((client) => <option key={client.member_id} value={client.member_id}>{client.member_name || client.member_email}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs text-muted-foreground">Session credit (optional)<select value={packageId} onChange={(event) => setPackageId(event.target.value)} className="h-9 border border-border bg-background px-2 text-sm text-foreground"><option value="">No package credit (notes only)</option>{packages.filter((item) => item.member_id === clientId && item.status === "active" && item.remaining_sessions > 0).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.remaining_sessions} remaining</option>)}</select></label>
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
      </section>}

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
              <time className="text-xs text-muted-foreground">{new Date(/Z$|[+-]\d{2}:\d{2}$/.test(log.performed_at) ? log.performed_at : `${log.performed_at}Z`).toLocaleString()}</time>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{log.duration_minutes} minutes{log.package_id ? " · 1 package credit used" : ""}</p>
            {log.notes && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-foreground/80">{log.notes}</p>}
          </li>)}
        </ul>}
      </section>
    </div>
  </>;
}
